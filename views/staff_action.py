import streamlit as st
import pandas as pd
from datetime import datetime
import qrcode
import io
import base64
import uuid

# Import Utils
from utils.gsheet_handler import save_patient_data, save_visit_data, update_patient_status, update_patient_token
from utils.calculations import (
    calculate_predicted_pefr, get_action_plan_zone, get_percent_predicted,
    check_technique_status, plot_pefr_chart, generate_qr
)

# --- Helper Function: แปลง QR เป็น Base64 ---
def get_base64_qr(data):
    qr = qrcode.QRCode(version=1, box_size=10, border=1)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

# --- 1. ฟังก์ชันลงทะเบียนผู้ป่วยใหม่ (คงเดิม) ---
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
            
            new_token = str(uuid.uuid4())
            new_pt_data = {
                "hn": formatted_hn, "prefix": reg_prefix, "first_name": reg_fname,
                "last_name": reg_lname, "dob": str(reg_dob),
                "best_pefr": reg_best_pefr, "height": reg_height,
                "public_token": new_token
            }
            try:
                save_patient_data(new_pt_data)
                st.success(f"🎉 ลงทะเบียนสำเร็จ!")
            except Exception as e:
                st.error(f"Error: {e}")

# --- 2. ฟังก์ชันค้นหาและจัดการผู้ป่วย (ปรับปรุง Session State) ---
def render_search_patient(patients_db, visits_db, base_url):
    # ==========================================
    # 🛠️ SESSION STATE MANAGEMENT (NEW)
    # ==========================================
    # ตรวจสอบ Flag การรีเซ็ตค่าก่อนเริ่มวาดหน้าจอ
    if st.session_state.get('reset_visit_form', False):
        # รีเซ็ตค่า Checkbox นอกฟอร์ม
        st.session_state['assess_toggle'] = False
        
        # (Optional) รีเซ็ตค่า Checkbox ย่อยข้างในด้วย (step_0, step_1, ...)
        # เพื่อให้ครั้งหน้าเปิดมาเป็นค่าเริ่มต้นทั้งหมด
        keys_to_clear = [k for k in st.session_state.keys() if k.startswith('step_') or k.startswith('adv_')]
        for k in keys_to_clear:
            del st.session_state[k]
            
        # ปิด Flag เพื่อให้ทำงานปกติในรอบต่อไป
        st.session_state['reset_visit_form'] = False

    # ==========================================
    
    hn_list = patients_db['hn'].unique().tolist()
    hn_list.sort()
    selected_hn = st.sidebar.selectbox("เลือกผู้ป่วย", hn_list)
    
    if selected_hn:
        # เตรียมข้อมูลคนไข้
        pt_data = patients_db[patients_db['hn'] == selected_hn].iloc[0]
        pt_visits = visits_db[visits_db['hn'] == selected_hn]
        
        # --- จัดการสถานะ ---
        current_status = pt_data.get('status', 'Active')
        if pd.isna(current_status) or str(current_status).strip() == "":
            current_status = "Active"

        status_color = "green"
        if current_status == "Discharge": status_color = "grey"
        elif current_status == "COPD": status_color = "orange"

        # --- Security: ตรวจสอบ/สร้าง Token ---
        public_token = pt_data.get('public_token', '')
        if pd.isna(public_token) or str(public_token).strip() == "" or str(public_token).lower() == "nan":
            with st.spinner("Creating Secure Token..."):
                new_token = str(uuid.uuid4())
                if update_patient_token(selected_hn, new_token):
                    st.rerun()
                else:
                    st.error("Failed to generate token")

        # --- ส่วนแสดง Header ข้อมูลคนไข้ (คงเดิม) ---
        c_head, c_status = st.columns([3, 1])
        with c_head:
            st.title(f"{pt_data['prefix']}{pt_data['first_name']} {pt_data['last_name']}")
        with c_status:
            st.write("") 
            st.markdown(f"สถานะ: :{status_color}[**{current_status}**]")

        # --- เมนูแก้ไขสถานะ (คงเดิม) ---
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
                        if update_patient_status(selected_hn, new_status):
                            st.success(f"เปลี่ยนสถานะเป็น {new_status} เรียบร้อย!")
                            st.rerun()

        # --- ข้อมูลพื้นฐานและประวัติ (คงเดิม) ---
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

        # --- เตรียมค่า Default สำหรับฟอร์ม ---
        controller_options = ["Seretide", "Budesonide", "Symbicort"]
        reliever_options = ["Salbutamol", "Berodual"]
        default_controllers = []
        default_relievers = []

        if not pt_visits.empty:
            pt_visits['date'] = pd.to_datetime(pt_visits['date'], errors='coerce')
            pt_visits_sorted = pt_visits.sort_values(by="date")
            last_actual_visit = pt_visits_sorted.iloc[-1]
            
            def parse_meds(med_str, available_opts):
                if pd.isna(med_str) or str(med_str).strip() == "": return []
                items = [x.strip() for x in str(med_str).split(",")]
                return [x for x in items if x in available_opts]

            default_controllers = parse_meds(last_actual_visit.get('controller'), controller_options)
            default_relievers = parse_meds(last_actual_visit.get('reliever'), reliever_options)
            
            # --- ส่วนแสดง Zone และ Control Level (คงเดิม - ย่อเพื่อความกระชับ) ---
            st.markdown("---")
            valid_pefr_visits = pt_visits_sorted[pt_visits_sorted['pefr'] > 0]
            if not valid_pefr_visits.empty:
                last_valid_visit = valid_pefr_visits.iloc[-1]
                current_pefr = last_valid_visit['pefr']
                zone_name, zone_color, _ = get_action_plan_zone(current_pefr, ref_pefr)
                pct_std = get_percent_predicted(current_pefr, ref_pefr)
                
                st.info(f"📋 **สถานะล่าสุด ({last_valid_visit['date'].strftime('%d/%m/%Y')})**")
                s1, s2, s3, s4 = st.columns([1, 1, 1.5, 1.8])
                s1.metric("PEFR ล่าสุด", f"{current_pefr}")
                s2.metric("% มาตรฐาน", f"{pct_std}%")
                
                # Zone Badge
                with s3:
                    st.markdown(f"""
                        <div style="display: flex; flex-direction: column;">
                            <span style="font-size: 14px; color: #606570;">Zone</span>
                            <div style="background-color: {zone_color}15; color: {zone_color}; border: 1px solid {zone_color}; padding: 6px 10px; border-radius: 20px; text-align: center; font-weight: 600;">{zone_name}</div>
                        </div>
                    """, unsafe_allow_html=True)
                
                # Control Level Badge
                with s4:
                    raw_ctrl = last_valid_visit.get('control_level', '-')
                    ctrl_lvl = str(raw_ctrl).strip() if pd.notna(raw_ctrl) else "-"
                    c_color = "#10B981" if "Well" in ctrl_lvl or "Controlled" == ctrl_lvl else ("#F59E0B" if "Partly" in ctrl_lvl else ("#EF4444" if "Uncontrolled" in ctrl_lvl else "#94A3B8"))
                    display_text = "Well Controlled" if c_color == "#10B981" else ctrl_lvl

                    st.markdown(f"""
                        <div style="display: flex; flex-direction: column;">
                            <span style="font-size: 14px; color: #606570;">Control Level</span>
                            <div style="background-color: {c_color}15; color: {c_color}; border: 1px solid {c_color}; padding: 6px 10px; border-radius: 20px; text-align: center; font-weight: 600;">{display_text}</div>
                        </div>
                    """, unsafe_allow_html=True)
            else:
                st.warning("⚠️ ยังไม่มีข้อมูลการเป่า Peak Flow")
            
            tech_status, tech_days, _ = check_technique_status(pt_visits)
            if tech_status == "overdue": st.error(f"🚨 **Alert: ขาดทบทวนเทคนิคพ่นยา!** (เลยมา {tech_days} วัน)")
            elif tech_status == "never": st.error("🚨 **Alert: ยังไม่เคยสอนเทคนิคพ่นยา**")
            else: st.success(f"✅ **เทคนิคพ่นยา: ปกติ** (ครบกำหนดใน {tech_days} วัน)")

        st.divider()
        st.subheader("📈 กราฟติดตามอาการ")
        if not pt_visits.empty:
            chart = plot_pefr_chart(pt_visits[pt_visits['pefr'] > 0], ref_pefr)
            st.altair_chart(chart, use_container_width=True)

        with st.expander("ประวัติการรักษาทั้งหมด"):
            if not pt_visits.empty:
                st.dataframe(pt_visits.sort_values(by="date", ascending=False), use_container_width=True)
            else:
                st.info("ℹ️ ยังไม่มีประวัติการรักษา")

        st.divider()
        st.subheader("📝 บันทึก Visit")
        
        # =================================================================
        # 🟢 ส่วนการประเมินเทคนิค (ที่เคยมีปัญหา Session State)
        # =================================================================
        inhaler_summary_text = "-" 
        tech_check_status = "ไม่"

        with st.container(border=True):
            st.markdown("##### 🎯 การประเมินเทคนิคพ่นยา (Optional)")
            
            # ✅ ใช้ Key เพื่อให้ Session State จำค่าได้ขณะกำลังกรอกข้อมูล
            is_teach_and_assess = st.checkbox("✅ ต้องการสอน/ประเมินเทคนิคพ่นยาในครั้งนี้", key="assess_toggle")

            if is_teach_and_assess:
                tech_check_status = "ทำ"
                st.info("📝 **แบบประเมินเทคนิค MDI (Inhaler Device Technique)**")
                steps = [
                    "(1) เขย่าหลอดพ่นยาในแนวตั้ง 3-4 ครั้ง", "(2) ถือหลอดพ่นยาในแนวตั้ง",
                    "(3) หายใจออกทางปากให้สุดเต็มที่", "(4) ตั้งศีรษะให้ตรง",
                    "(5) ใช้ริมฝีปากอมปากหลอดพ่นยาให้สนิท", "(6) หายใจเข้าทางปากช้าๆ ลึกๆ พร้อมกดที่พ่นยา",
                    "(7) กลั้นลมหายใจประมาณ 10 วินาที", "(8) ผ่อนลมหายใจออกทางปากหรือจมูกช้าๆ"
                ]
                checks = []
                cols_check = st.columns(2)
                for i, step in enumerate(steps):
                    with cols_check[i % 2]:
                        # ใช้ Key เพื่อให้คงสถานะไว้ได้
                        checks.append(st.checkbox(step, value=True, key=f"step_{i}"))

                score = sum(checks)
                critical_fail = []
                if not checks[4]: critical_fail.append("ข้อ 5 (อมไม่สนิท)")
                if not checks[5]: critical_fail.append("ข้อ 6 (กดพร้อมสูด)")
                if not checks[6]: critical_fail.append("ข้อ 7 (กลั้นหายใจ)")

                inhaler_status = ""
                if critical_fail:
                    st.error(f"🚨 **Critical Fail:** {', '.join(critical_fail)}")
                    inhaler_status = "Fail (Critical)"
                elif score == 8:
                    st.success("✅ เทคนิคถูกต้องสมบูรณ์ (Perfect)")
                    inhaler_status = "Pass"
                else:
                    st.warning(f"⚠️ ยังไม่สมบูรณ์ (ขาด {8-score} ข้อ)")
                    inhaler_status = "Needs Improvement"
                
                st.markdown("---")
                c_adv1, c_adv2 = st.columns(2)
                adv_rinse = c_adv1.checkbox("แนะนำบ้วนปาก", key="adv_rinse")
                adv_clean = c_adv2.checkbox("แนะนำล้างอุปกรณ์", key="adv_clean")

                failed_indices = [i+1 for i, x in enumerate(checks) if not x]
                fail_str = ",".join(map(str, failed_indices)) if failed_indices else "None"
                inhaler_summary_text = f"Score: {score}/8 ({inhaler_status}) | Fail: {fail_str}"
                if adv_rinse: inhaler_summary_text += " | Adv:Rinse"
                if adv_clean: inhaler_summary_text += " | Adv:Clean"

        # =================================================================
        # 📝 ฟอร์มบันทึกข้อมูลหลัก (clear_on_submit=True เคลียร์ของในฟอร์มเอง)
        # =================================================================
        with st.form("new_visit", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            v_date = col_a.date_input("วันที่", value=datetime.today())
            v_is_new = col_a.checkbox("🆕 เป็นผู้ป่วยรายใหม่ (New Case)") 
            with col_b:
                v_pefr = st.number_input("PEFR (L/min)", 0, 900, step=10)
                v_no_pefr = st.checkbox("ไม่ได้เป่า Peak Flow (N/A)")
            
            v_control = st.radio(
                "Control Level", 
                ["Well Controlled", "Partly Controlled", "Uncontrolled"], 
                horizontal=True
            )
            
            c_med1, c_med2 = st.columns(2)
            v_cont = c_med1.multiselect("Controller", controller_options, default=default_controllers)
            v_rel = c_med2.multiselect("Reliever", reliever_options, default=default_relievers)
            
            c_adh, c_chk = st.columns(2)
            v_adh = c_adh.slider("ความร่วมมือ (%)", 0, 100, 100)
            v_relative_pickup = c_adh.checkbox("ญาติรับยาแทน")
            
            v_drp = st.text_area("DRP")
            v_adv = st.text_area("Advice")
            v_note = st.text_input("หมายเหตุ")
            v_next = st.date_input("นัดถัดไป")
            
            if st.form_submit_button("💾 บันทึกข้อมูล"):
                # เตรียมข้อมูลสำหรับบันทึก
                actual_pefr = 0 if v_no_pefr else v_pefr
                actual_adherence = 0 if v_relative_pickup else v_adh
                final_note = f"[ญาติรับแทน] {v_note}" if v_relative_pickup else v_note
                
                new_data = {
                    "hn": selected_hn, "date": str(v_date), "pefr": actual_pefr,
                    "control_level": v_control, 
                    "controller": ", ".join(v_cont), "reliever": ", ".join(v_rel), 
                    "adherence": actual_adherence, "drp": v_drp, "advice": v_adv, 
                    "technique_check": tech_check_status, # ค่าจากนอกฟอร์ม
                    "next_appt": str(v_next), "note": final_note, 
                    "is_new_case": "TRUE" if v_is_new else "FALSE",
                    "inhaler_eval": inhaler_summary_text # ค่าจากนอกฟอร์ม
                }
                
                # บันทึกข้อมูล
                save_visit_data(new_data)
                
                # ✅ TRIGGER RESET: ตั้งค่าให้รีเซ็ตฟอร์มในรอบถัดไป
                st.session_state['reset_visit_form'] = True
                
                st.success("บันทึกสำเร็จ")
                st.rerun() # รีโหลดหน้าเพื่อเริ่มรอบใหม่ (และจะไปเจอกับ logic reset ข้างบน)

        # --- ส่วน Digital Card (คงเดิม) ---
        st.divider()
        st.subheader("📇 Digital Asthma Card")
        link = f"{base_url}/?token={public_token}"
        qr_b64 = get_base64_qr(link)
        
        # (ส่วน HTML Card ตัดย่อไว้ แต่ใช้ Logic เดิม)
        card_best_pefr = int(predicted_pefr) if int(predicted_pefr) > 0 else pt_data.get('best_pefr', 0)
        green_lim = int(card_best_pefr * 0.8)
        yellow_lim = int(card_best_pefr * 0.6)
        
        # ... (โค้ดแสดงผล Card เหมือนเดิม) ...
        # แสดงปุ่ม Copy Link
        c_main, _ = st.columns([1.5, 1])
        with c_main:
             st.link_button("🔗 เปิดหน้าคนไข้", link, type="primary")
