import streamlit as st
import pandas as pd
from datetime import datetime
from utils.gsheet_handler import save_patient_data, save_visit_data, load_data_staff
from utils.calculations import (
    calculate_predicted_pefr, get_action_plan_zone, get_percent_predicted,
    check_technique_status, plot_pefr_chart, generate_qr
)

def render_register_patient(patients_db):
    st.title("➕ ลงทะเบียนผู้ป่วยรายใหม่")
    with st.form("register_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        reg_hn_input = col1.text_input("HN (เลขประจำตัวผู้ป่วย)")
        reg_prefix = col2.selectbox("คำนำหน้า", ["นาย", "นาง", "น.ส.", "ด.ช.", "ด.ญ."])
        col3, col4 = st.columns(2)
        reg_fname = col3.text_input("ชื่อจริง")
        reg_lname = col4.text_input("นามสกุล")
        col5, col6 = st.columns(2)
        reg_dob = col5.date_input("วันเกิด", min_value=datetime(1920, 1, 1))
        reg_height = col6.number_input("ส่วนสูง (cm)", 50, 250, 160)
        reg_best_pefr = st.number_input("Personal Best PEFR (ถ้ามี)", 0, 900, 0)
        
        if st.form_submit_button("✅ ลงทะเบียน"):
            if not reg_hn_input or not reg_fname or not reg_lname:
                st.error("❌ กรุณากรอกข้อมูลให้ครบถ้วน")
                return
            formatted_hn = str(reg_hn_input).strip().zfill(7)
            if formatted_hn in patients_db['hn'].values:
                st.error(f"❌ HN {formatted_hn} มีอยู่ในระบบแล้ว")
                return
            
            new_pt_data = {
                "hn": formatted_hn, "prefix": reg_prefix, "first_name": reg_fname,
                "last_name": reg_lname, "dob": str(reg_dob),
                "best_pefr": reg_best_pefr, "height": reg_height
            }
            try:
                save_patient_data(new_pt_data)
                st.success(f"🎉 ลงทะเบียนสำเร็จ!")
            except Exception as e:
                st.error(f"Error: {e}")

def render_search_patient(patients_db, visits_db, base_url):
    hn_list = patients_db['hn'].unique().tolist()
    hn_list.sort()
    selected_hn = st.sidebar.selectbox("เลือกผู้ป่วย", hn_list)
    
    if selected_hn:
        pt_data = patients_db[patients_db['hn'] == selected_hn].iloc[0]
        pt_visits = visits_db[visits_db['hn'] == selected_hn]
        
        dob = pd.to_datetime(pt_data['dob'])
        age = (datetime.now() - dob).days // 365
        height = pt_data.get('height', 0)
        predicted_pefr = calculate_predicted_pefr(age, height, pt_data['prefix'])
        ref_pefr = predicted_pefr if predicted_pefr > 0 else pt_data['best_pefr']
        
        st.title(f"{pt_data['prefix']}{pt_data['first_name']} {pt_data['last_name']}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("HN", pt_data['hn'])
        c2.metric("อายุ", f"{age} ปี")
        c3.metric("ส่วนสูง", f"{height} cm")
        c4.metric("Standard PEFR", f"{int(predicted_pefr)}")

        if not pt_visits.empty:
            pt_visits['date'] = pd.to_datetime(pt_visits['date'], errors='coerce')
            pt_visits_sorted = pt_visits.sort_values(by="date")
            last_visit = pt_visits_sorted.iloc[-1]
            
            current_pefr = last_visit['pefr']
            zone_name, zone_color, advice = get_action_plan_zone(current_pefr, ref_pefr)
            pct_std = get_percent_predicted(current_pefr, ref_pefr)
            
            st.markdown("---")
            st.info(f"📋 **สถานะล่าสุด ({last_visit['date'].strftime('%d/%m/%Y')})**")
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("PEFR ล่าสุด", f"{current_pefr}")
            s2.metric("% มาตรฐาน", f"{pct_std}%")
            s3.markdown(f":{zone_color}[**{zone_name}**]")
            s4.write(last_visit.get('control_level', '-'))

        st.divider()
        st.subheader("📈 กราฟติดตามอาการ")
        if not pt_visits.empty:
            chart = plot_pefr_chart(pt_visits_sorted, ref_pefr)
            st.altair_chart(chart, use_container_width=True)

        with st.expander("ประวัติการรักษา"):
            if not pt_visits.empty:
                history_df = pt_visits.copy()
                history_df['date'] = pd.to_datetime(history_df['date'], errors='coerce')
                history_df = history_df.sort_values(by="date", ascending=False)
                history_df['date'] = history_df['date'].dt.strftime('%d/%m/%Y')
                st.dataframe(history_df, use_container_width=True)
            else:
                st.info("ℹ️ ยังไม่มีประวัติการรักษา (New Case)")

        st.divider()
        st.subheader("📝 บันทึก Visit")
        with st.form("new_visit", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            v_date = col_a.date_input("วันที่", value=datetime.today())
            v_is_new = col_a.checkbox("🆕 เป็นผู้ป่วยรายใหม่ (New Case)") 
            with col_b:
                v_pefr = st.number_input("PEFR (L/min)", 0, 900, step=10)
                v_no_pefr = st.checkbox("ไม่ได้เป่า Peak Flow (N/A)")
            
            v_control = st.radio("Control", ["Controlled", "Partly Controlled", "Uncontrolled"], horizontal=True)
            c_med1, c_med2 = st.columns(2)
            v_cont = c_med1.multiselect("Controller", ["Seretide", "Budesonide", "Symbicort"])
            v_rel = c_med2.multiselect("Reliever", ["Salbutamol", "Berodual"])
            
            c_adh, c_chk = st.columns(2)
            v_adh = c_adh.slider("ความร่วมมือ (%)", 0, 100, 100)
            v_relative_pickup = c_adh.checkbox("ญาติรับยาแทน")
            v_tech = c_chk.checkbox("✅ สอนเทคนิควันนี้")
            
            v_drp = st.text_area("DRP")
            v_adv = st.text_area("Advice")
            v_note = st.text_input("หมายเหตุ")
            v_next = st.date_input("นัดถัดไป")
            
            if st.form_submit_button("💾 บันทึกข้อมูล"):
                actual_pefr = 0 if v_no_pefr else v_pefr
                actual_adherence = 0 if v_relative_pickup else v_adh
                final_note = f"[ญาติรับแทน] {v_note}" if v_relative_pickup else v_note

                new_data = {
                    "hn": selected_hn, "date": str(v_date), "pefr": actual_pefr,
                    "control_level": v_control, "controller": ", ".join(v_cont),
                    "reliever": ", ".join(v_rel), "adherence": actual_adherence,
                    "drp": v_drp, "advice": v_adv, "technique_check": "ทำ" if v_tech else "ไม่",
                    "next_appt": str(v_next), "note": final_note, 
                    "is_new_case": "TRUE" if v_is_new else "FALSE"
                }
                save_visit_data(new_data)
                st.success("บันทึกสำเร็จ")
                st.rerun()

        st.divider()
        link = f"{base_url}/?hn={selected_hn}"
        c_q, c_t = st.columns([1,2])
        c_q.image(generate_qr(link), width=150)
        c_t.markdown(f"**ลิงก์คนไข้:** {link}")