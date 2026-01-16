import streamlit as st
import pandas as pd
from datetime import datetime
from utils.gsheet_handler import save_patient_data, save_visit_data, update_patient_status
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
        # เตรียมข้อมูลคนไข้
        pt_data = patients_db[patients_db['hn'] == selected_hn].iloc[0]
        pt_visits = visits_db[visits_db['hn'] == selected_hn]
        
        # --- ส่วนจัดการสถานะ (Patient Status) ---
        current_status = pt_data.get('status', 'Active')
        if pd.isna(current_status) or str(current_status).strip() == "":
            current_status = "Active"

        status_color = "green"
        if current_status == "Discharge": status_color = "grey"
        elif current_status == "COPD": status_color = "orange"

        c_head, c_status = st.columns([3, 1])
        with c_head:
            st.title(f"{pt_data['prefix']}{pt_data['first_name']} {pt_data['last_name']}")
        with c_status:
            st.write("") 
            st.markdown(f"สถานะ: :{status_color}[**{current_status}**]")

        with st.expander("⚙️ แก้ไขสถานะคนไข้ (Discharge / COPD)"):
            new_status = st.radio(
                "เลือกสถานะใหม่:", 
                ["Active", "Discharge", "COPD"],
                horizontal=True,
                index=["Active", "Discharge", "COPD"].index(current_status)
            )
            
            if new_status != current_status:
                if st.button("บันทึกการเปลี่ยนสถานะ"):
                    with st.spinner("กำลังอัปเดต..."):
                        success = update_patient_status(selected_hn, new_status)
                        if success:
                            st.success(f"เปลี่ยนสถานะเป็น {new_status} เรียบร้อย!")
                            st.rerun()
                        else:
                            st.error("เกิดข้อผิดพลาดในการอัปเดต")

        dob = pd.to_datetime(pt_data['dob'])
        age = (datetime.now() - dob).days // 365
        height = pt_data.get('height', 0)
        predicted_pefr = calculate_predicted_pefr(age, height, pt_data['prefix'])
        ref_pefr = predicted_pefr if predicted_pefr > 0 else pt_data['best_pefr']
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("HN", pt_data['hn'])
        c2.metric("อายุ", f"{age} ปี")
        c3.metric("ส่วนสูง", f"{height} cm")
        c4.metric("Standard PEFR", f"{int(predicted_pefr)}")

        # --- Smart Form Variables ---
        controller_options = ["Seretide", "Budesonide", "Symbicort"]
        reliever_options = ["Salbutamol", "Berodual"]
        default_controllers = []
        default_relievers = []

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

            # Alert DRP
            last_drp = str(last_visit.get('drp', '')).strip()
            if last_drp and last_drp != "-" and last_drp.lower() != "nan":
                st.warning(f"⚠️ **DRP ครั้งล่าสุด:** {last_drp}")

            # Alert Tech
            tech_status, tech_days, tech_last_date = check_technique_status(pt_visits)
            st.write("") 
            if tech_status == "overdue":
                last_date_str = tech_last_date.strftime('%d/%m/%Y') if tech_last_date else "-"
                st.error(f"🚨 **Alert: ขาดทบทวนเทคนิคพ่นยา!** (เลยมา {tech_days} วัน)")
            elif tech_status == "never":
                st.error("🚨 **Alert: ยังไม่เคยสอนเทคนิคพ่นยา**")
            else:
                st.success(f"✅ **เทคนิคพ่นยา: ปกติ** (ครบกำหนดใน {tech_days} วัน)")

            # Parse Meds Logic
            def parse_meds(med_str, available_opts):
                if pd.isna(med_str) or str(med_str).strip() == "": return []
                items = [x.strip() for x in str(med_str).split(",")]
                return [x for x in items if x in available_opts]

            default_controllers = parse_meds(last_visit.get('controller'), controller_options)
            default_relievers = parse_meds(last_visit.get('reliever'), reliever_options)
        
        st.divider()
        st.subheader("📈 กราฟติดตามอาการ")
        if not pt_visits.empty:
            chart = plot_pefr_chart(pt_visits_sorted, ref_pefr)
            st.altair_chart(chart, use_container_width=True)

        with st.expander("ประวัติการรักษา"):
            if not pt_visits.empty:
                history_df = pt_visits.copy()
                history_df = history_df.sort_values(by="date", ascending=False)
                history_df['date'] = history_df['date'].dt.strftime('%d/%m/%Y')
                st.dataframe(history_df, use_container_width=True)
            else:
                st.info("ℹ️ ยังไม่มีประวัติการรักษา (New Case)")

        st.divider()
        st.subheader("📝 บันทึก Visit")
        
        # =================================================================
        # 🟢 ส่วนประเมินเทคนิคพ่นยา (อยู่นอก Form เพื่อให้ Interactive)
        # =================================================================
        inhaler_summary_text = "-" # ค่าเริ่มต้น
        tech_check_status = "ไม่"  # ค่าเริ่มต้น

        with st.container(border=True):
            st.markdown("##### 🎯 การประเมินเทคนิคพ่นยา (Optional)")
            
            # ใช้ key เพื่อให้ Session State จำสถานะการติ๊กได้
            is_teach_and_assess = st.checkbox("✅ ต้องการสอน/ประเมินเทคนิคพ่นยาในครั้งนี้", key="assess_toggle")

            if is_teach_and_assess:
                tech_check_status = "ทำ" # ถ้าติ๊ก checkbox นี้ ให้ถือว่าสอนแล้ว
                
                st.info("📝 **แบบประเมินเทคนิค MDI (Inhaler Device Technique)**")
                steps = [
                    "(1) เขย่าหลอดพ่นยาในแนวตั้ง 3-4 ครั้ง",
                    "(2) ถือหลอดพ่นยาในแนวตั้ง",
                    "(3) หายใจออกทางปากให้สุดเต็มที่",
                    "(4) ตั้งศีรษะให้ตรง",
                    "(5) ใช้ริมฝีปากอมปากหลอดพ่นยาให้สนิท",
                    "(6) หายใจเข้าทางปากช้าๆ ลึกๆ พร้อมกดที่พ่นยา 1 ครั้ง",
                    "(7) กลั้นลมหายใจประมาณ 10 วินาที",
                    "(8) ผ่อนลมหายใจออกทางปากหรือจมูกช้าๆ"
                ]
                
                checks = []
                # ใช้คอลัมน์เพื่อจัดเรียงให้สวยงาม
                cols_check = st.columns(2)
                for i, step in enumerate(steps):
                    with cols_check[i % 2]:
                        # ใช้ key unique เพื่อไม่ให้ error
                        checks.append(st.checkbox(step, value=True, key=f"step_{i}"))

                score = sum(checks)
                
                # Critical Fail Logic
                critical_fail = []
                if not checks[4]: critical_fail.append("ข้อ 5 (อมไม่สนิท)")
                if not checks[5]: critical_fail.append("ข้อ 6 (กดพร้อมสูด)")
                if not checks[6]: critical_fail.append("ข้อ 7 (กลั้นหายใจ)")

                inhaler_status = ""
                if critical_fail:
                    st.error(f"🚨 **Critical Fail:** {', '.join(critical_fail)}")
                    st.toast("⚠️ กรุณาสอนเทคนิคใหม่ทันที!", icon="📢")
                    inhaler_status = "Fail (Critical)"
                elif score == 8:
                    st.success("✅ เทคนิคถูกต้องสมบูรณ์ (Perfect)")
                    inhaler_status = "Pass"
                else:
                    st.warning(f"⚠️ ยังไม่สมบูรณ์ (ขาด {8-score} ข้อ)")
                    inhaler_status = "Needs Improvement"
                
                st.markdown("---")
                st.write("**คำแนะนำเพิ่มเติม:**")
                c_adv1, c_adv2 = st.columns(2)
                adv_rinse = c_adv1.checkbox("แนะนำบ้วนปาก", key="adv_rinse")
                adv_clean = c_adv2.checkbox("แนะนำล้างอุปกรณ์", key="adv_clean")

                # สร้าง String สรุปผล (เตรียมส่งเข้า Form)
                failed_indices = [i+1 for i, x in enumerate(checks) if not x]
                fail_str = ",".join(map(str, failed_indices)) if failed_indices else "None"
                inhaler_summary_text = f"Score: {score}/8 ({inhaler_status}) | Fail: {fail_str}"
                if adv_rinse: inhaler_summary_text += " | Adv:Rinse"
                if adv_clean: inhaler_summary_text += " | Adv:Clean"

        # =================================================================
        # 🟡 ส่วนฟอร์มบันทึกข้อมูลหลัก
        # =================================================================
        with st.form("new_visit", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            v_date = col_a.date_input("วันที่", value=datetime.today())
            v_is_new = col_a.checkbox("🆕 เป็นผู้ป่วยรายใหม่ (New Case)") 
            with col_b:
                v_pefr = st.number_input("PEFR (L/min)", 0, 900, step=10)
                v_no_pefr = st.checkbox("ไม่ได้เป่า Peak Flow (N/A)")
            
            v_control = st.radio("Control", ["Controlled", "Partly Controlled", "Uncontrolled"], horizontal=True)
            
            c_med1, c_med2 = st.columns(2)
            v_cont = c_med1.multiselect("Controller", controller_options, default=default_controllers)
            v_rel = c_med2.multiselect("Reliever", reliever_options, default=default_relievers)
            
            if default_controllers or default_relievers:
                st.caption("✨ ระบบดึงรายการยาจากครั้งล่าสุดมาให้แล้ว")

            c_adh, c_chk = st.columns(2)
            v_adh = c_adh.slider("ความร่วมมือ (%)", 0, 100, 100)
            v_relative_pickup = c_adh.checkbox("ญาติรับยาแทน")
            
            # (ไม่ต้องมี Checkbox สอนเทคนิคตรงนี้แล้ว เพราะย้ายไปข้างบน)

            v_drp = st.text_area("DRP")
            v_adv = st.text_area("Advice")
            v_note = st.text_input("หมายเหตุ")
            v_next = st.date_input("นัดถัดไป")
            
            if st.form_submit_button("💾 บันทึกข้อมูล"):
                actual_pefr = 0 if v_no_pefr else v_pefr
                actual_adherence = 0 if v_relative_pickup else v_adh
                final_note = f"[ญาติรับแทน] {v_note}" if v_relative_pickup else v_note
                
                # ✅ รับค่าจากตัวแปรด้านบนมาใช้บันทึก
                new_data = {
                    "hn": selected_hn, "date": str(v_date), "pefr": actual_pefr,
                    "control_level": v_control, 
                    "controller": ", ".join(v_cont),
                    "reliever": ", ".join(v_rel), 
                    "adherence": actual_adherence,
                    "drp": v_drp, "advice": v_adv, 
                    "technique_check": tech_check_status, # ค่า "ทำ/ไม่" จากด้านบน
                    "next_appt": str(v_next), "note": final_note, 
                    "is_new_case": "TRUE" if v_is_new else "FALSE",
                    "inhaler_eval": inhaler_summary_text # ค่าคะแนนจากด้านบน
                }
                save_visit_data(new_data)
                
                # Reset Checkbox นอกฟอร์มให้หายไปเมื่อบันทึกเสร็จ
                st.session_state['assess_toggle'] = False 
                
                st.success("บันทึกสำเร็จ")
                st.rerun()

        # 📇 DIGITAL ASTHMA CARD
        st.divider()
        st.subheader("📇 Digital Asthma Card")
        link = f"{base_url}/?hn={selected_hn}"
        with st.container(border=True):
            c_qr, c_info = st.columns([1, 2.5])
            with c_qr:
                st.image(generate_qr(link), use_container_width=True)
                st.caption("📱 สแกนเพื่อดูประวัติ")
            with c_info:
                st.markdown(f"### {pt_data['prefix']}{pt_data['first_name']} {pt_data['last_name']}")
                st.markdown(f"**HN:** `{selected_hn}`")
                c_age, c_height = st.columns(2)
                c_age.markdown(f"**อายุ:** {age} ปี")
                c_height.markdown(f"**ส่วนสูง:** {height} cm")
                st.info(f"🎯 **Predicted PEFR:** {int(predicted_pefr)} L/min")
                st.link_button("🔗 เปิดหน้าคนไข้ (Patient View)", link, type="primary", use_container_width=True)
        
        with st.expander("🔗 คัดลอกลิงก์โดยตรง"):
            st.text_input("Direct Link", value=link, label_visibility="collapsed")
