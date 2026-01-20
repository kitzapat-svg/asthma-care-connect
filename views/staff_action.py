import streamlit as st
import pandas as pd
from datetime import datetime
import qrcode
import io
import base64

# Import Utils
from utils.gsheet_handler import save_patient_data, save_visit_data, update_patient_status
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

# --- 1. ฟังก์ชันลงทะเบียนผู้ป่วยใหม่ ---
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

# --- 2. ฟังก์ชันค้นหาและจัดการผู้ป่วย (รวม Digital Card) ---
def render_search_patient(patients_db, visits_db, base_url):
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
                        if update_patient_status(selected_hn, new_status):
                            st.success(f"เปลี่ยนสถานะเป็น {new_status} เรียบร้อย!")
                            st.rerun()

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
            last_actual_visit = pt_visits_sorted.iloc[-1]
            
            def parse_meds(med_str, available_opts):
                if pd.isna(med_str) or str(med_str).strip() == "": return []
                items = [x.strip() for x in str(med_str).split(",")]
                return [x for x in items if x in available_opts]

            default_controllers = parse_meds(last_actual_visit.get('controller'), controller_options)
            default_relievers = parse_meds(last_actual_visit.get('reliever'), reliever_options)

# ------------------------------------------------------------------
            # ✅ ส่วนแสดงสถานะล่าสุด
            # ------------------------------------------------------------------
            st.markdown("---")
            valid_pefr_visits = pt_visits_sorted[pt_visits_sorted['pefr'] > 0]
            
            if not valid_pefr_visits.empty:
                last_valid_visit = valid_pefr_visits.iloc[-1]
                current_pefr = last_valid_visit['pefr']
                visit_date_str = last_valid_visit['date'].strftime('%d/%m/%Y')
                
                zone_name, zone_color, advice = get_action_plan_zone(current_pefr, ref_pefr)
                pct_std = get_percent_predicted(current_pefr, ref_pefr)
                
                st.info(f"📋 **สถานะล่าสุด ({visit_date_str})**")
                
                # แจ้งเตือนถ้าข้อมูลไม่ตรงกับวันล่าสุดจริง (กรณีญาติรับยา)
                if last_actual_visit['date'] != last_valid_visit['date']:
                    last_actual_str = last_actual_visit['date'].strftime('%d/%m/%Y')
                    st.caption(f"ℹ️ (ล่าสุดเมื่อ {last_actual_str} ไม่ได้เป่า Peak Flow ระบบจึงแสดงผลจากครั้งก่อนหน้า)")
                
                # 🔥 ปรับสัดส่วนคอลัมน์ใหม่ (ลด Zone ลงนิด เพิ่ม Control Level)
                s1, s2, s3, s4 = st.columns([1, 1, 1.5, 1.8])
                
                s1.metric("PEFR ล่าสุด", f"{current_pefr}")
                s2.metric("% มาตรฐาน", f"{pct_std}%")
                
                # --- ช่อง Zone ---
                with s3:
                    short_zone_name = zone_name
                    st.markdown(f"""
                        <div style="display: flex; flex-direction: column; justify-content: flex-start;">
                            <span style="font-size: 14px; color: #606570; margin-bottom: 4px;">Zone</span>
                            <div style="
                                background-color: {zone_color}15;
                                color: {zone_color};
                                border: 1px solid {zone_color};
                                padding: 6px 10px;
                                border-radius: 20px; 
                                text-align: center;
                                font-weight: 600;
                                font-size: 15px;
                                line-height: 1.2;
                                white-space: nowrap;
                                overflow: hidden;
                                text-overflow: ellipsis;
                            ">
                                {short_zone_name}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                
# --- ช่อง Control Level (ปรับ Logic รองรับชื่อใหม่) ---
                with s4:
                    raw_ctrl = last_valid_visit.get('control_level', '-')
                    
                    # 1. Cleaning
                    if pd.isna(raw_ctrl) or str(raw_ctrl).strip() in ['', 'nan', 'None']:
                        ctrl_lvl = "-"
                    else:
                        ctrl_lvl = str(raw_ctrl).strip()

                    # 2. Logic สีป้าย (Updated for "Well Controlled")
                    if "Uncontrolled" in ctrl_lvl:
                        c_color = "#EF4444"  # แดง
                        display_text = ctrl_lvl
                    elif "Partly" in ctrl_lvl:
                        c_color = "#F59E0B"  # ส้ม
                        display_text = ctrl_lvl
                    elif "Well" in ctrl_lvl or "Controlled" == ctrl_lvl: 
                        # ✅ รองรับทั้ง "Well Controlled" (ใหม่) และ "Controlled" (เก่า)
                        c_color = "#10B981"  # เขียว
                        display_text = "Well Controlled" # บังคับโชว์ชื่อใหม่ให้สวยงาม
                    else:
                        c_color = "#94A3B8"  # เทา
                        display_text = "รอประเมิน" if ctrl_lvl == "-" else ctrl_lvl

                    # 3. HTML Badge
                    st.markdown(f"""
                        <div style="display: flex; flex-direction: column; justify-content: flex-start;">
                            <span style="font-size: 14px; color: #606570; margin-bottom: 4px;">Control Level</span>
                            <div style="
                                background-color: {c_color}15;
                                color: {c_color};
                                border: 1px solid {c_color};
                                padding: 6px 10px;
                                border-radius: 20px; 
                                text-align: center;
                                font-weight: 600;
                                font-size: 14px;
                                white-space: nowrap;
                                overflow: hidden;
                                text-overflow: ellipsis;
                            ">
                                {display_text}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

            else:
                st.warning("⚠️ ยังไม่มีข้อมูลการเป่า Peak Flow (มีแต่ประวัติรับยา)")
            
            last_drp = str(last_actual_visit.get('drp', '')).strip()
            if last_drp and last_drp != "-" and last_drp.lower() != "nan":
                st.warning(f"⚠️ **DRP ครั้งล่าสุด:** {last_drp}")

            tech_status, tech_days, tech_last_date = check_technique_status(pt_visits)
            st.write("") 
            if tech_status == "overdue":
                st.error(f"🚨 **Alert: ขาดทบทวนเทคนิคพ่นยา!** (เลยมา {tech_days} วัน)")
            elif tech_status == "never":
                st.error("🚨 **Alert: ยังไม่เคยสอนเทคนิคพ่นยา**")
            else:
                st.success(f"✅ **เทคนิคพ่นยา: ปกติ** (ครบกำหนดใน {tech_days} วัน)")

        st.divider()
        st.subheader("📈 กราฟติดตามอาการ")
        if not pt_visits.empty:
            valid_pefr_visits_all = pt_visits_sorted[pt_visits_sorted['pefr'] > 0]
            if not valid_pefr_visits_all.empty:
                chart = plot_pefr_chart(valid_pefr_visits_all, ref_pefr)
                st.altair_chart(chart, use_container_width=True)
            else:
                st.caption("ไม่มีข้อมูลกราฟ")

        with st.expander("ประวัติการรักษาทั้งหมด"):
            if not pt_visits.empty:
                history_df = pt_visits.copy()
                history_df = history_df.sort_values(by="date", ascending=False)
                history_df['date'] = history_df['date'].dt.strftime('%d/%m/%Y')
                st.dataframe(history_df, use_container_width=True)
            else:
                st.info("ℹ️ ยังไม่มีประวัติการรักษา (New Case)")

        st.divider()
        st.subheader("📝 บันทึก Visit")
        
        inhaler_summary_text = "-" 
        tech_check_status = "ไม่"

        with st.container(border=True):
            st.markdown("##### 🎯 การประเมินเทคนิคพ่นยา (Optional)")
            is_teach_and_assess = st.checkbox("✅ ต้องการสอน/ประเมินเทคนิคพ่นยาในครั้งนี้", key="assess_toggle")

            if is_teach_and_assess:
                tech_check_status = "ทำ"
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
                cols_check = st.columns(2)
                for i, step in enumerate(steps):
                    with cols_check[i % 2]:
                        checks.append(st.checkbox(step, value=True, key=f"step_{i}"))

                score = sum(checks)
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

                failed_indices = [i+1 for i, x in enumerate(checks) if not x]
                fail_str = ",".join(map(str, failed_indices)) if failed_indices else "None"
                inhaler_summary_text = f"Score: {score}/8 ({inhaler_status}) | Fail: {fail_str}"
                if adv_rinse: inhaler_summary_text += " | Adv:Rinse"
                if adv_clean: inhaler_summary_text += " | Adv:Clean"

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
            
            if default_controllers or default_relievers:
                st.caption("✨ ระบบดึงรายการยาจากครั้งล่าสุดมาให้แล้ว")

            c_adh, c_chk = st.columns(2)
            v_adh = c_adh.slider("ความร่วมมือ (%)", 0, 100, 100)
            v_relative_pickup = c_adh.checkbox("ญาติรับยาแทน")
            
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
                    "control_level": v_control, 
                    "controller": ", ".join(v_cont),
                    "reliever": ", ".join(v_rel), 
                    "adherence": actual_adherence,
                    "drp": v_drp, "advice": v_adv, 
                    "technique_check": tech_check_status,
                    "next_appt": str(v_next), "note": final_note, 
                    "is_new_case": "TRUE" if v_is_new else "FALSE",
                    "inhaler_eval": inhaler_summary_text
                }
                save_visit_data(new_data)
                st.session_state['assess_toggle'] = False 
                st.success("บันทึกสำเร็จ")
                st.rerun()

        # ==============================================================================
        # 📇 DIGITAL ASTHMA CARD (แก้ไขให้แสดงผลเป็นรูปภาพ ไม่ใช่โค้ด)
        # ==============================================================================
        st.divider()
        st.subheader("📇 Digital Asthma Card")
        link = f"{base_url}/?hn={selected_hn}"
        
        # 1. เตรียมข้อมูลสำหรับบัตร
        card_best_pefr = int(predicted_pefr)
        if card_best_pefr == 0:
            card_best_pefr = pt_data.get('best_pefr', 0)

        if card_best_pefr > 0:
            green_lim = int(card_best_pefr * 0.8)
            yellow_lim = int(card_best_pefr * 0.6)
            txt_g = f"> {green_lim}"
            txt_y = f"{yellow_lim} - {green_lim}"
            txt_r = f"< {yellow_lim}"
        else:
            txt_g, txt_y, txt_r = "-", "-", "-"

        # 2. สร้าง QR Code Base64
        qr_b64 = get_base64_qr(link)

        # 3. HTML/CSS
        card_html = f"""
        <style>
            .asthma-card {{
                position: relative;
                width: 100%;
                max-width: 420px;
                padding-top: 63%; /* Aspect Ratio 1.58:1 */
                background: linear-gradient(135deg, #ffffff 0%, #f1f5f9 100%);
                border-radius: 16px;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
                border: 1px solid #cbd5e1;
                overflow: hidden;
                font-family: 'Kanit', sans-serif;
                color: #334155;
            }}
            .card-content {{
                position: absolute;
                top: 0; left: 0; bottom: 0; right: 0;
                padding: 16px 20px;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
            }}
            .card-header {{
                display: flex; justify-content: space-between; align-items: flex-start;
                margin-bottom: 5px;
            }}
            .card-chip {{
                width: 42px; height: 28px;
                background: linear-gradient(135deg, #e2e8f0 0%, #94a3b8 100%);
                border-radius: 6px; border: 1px solid #64748b; opacity: 0.8;
            }}
            .card-logo {{
                font-size: 10px; font-weight: bold; color: #94a3b8; letter-spacing: 1px; text-transform: uppercase;
            }}
            .card-body {{
                display: flex; justify-content: space-between; align-items: center; flex: 1;
            }}
            .info-col {{ 
                flex: 1; padding-right: 10px; display: flex; flex-direction: column; justify-content: center;
            }}
            .pt-name {{ 
                font-size: 18px; font-weight: 600; color: #1e293b; line-height: 1.3; margin-bottom: 6px;
                display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
            }}
            .pt-meta {{ font-size: 12px; color: #64748B; }}
            .pt-meta b {{ color: #0f172a; font-size: 14px; font-weight: 600; }}
            .qr-box {{
                background: white; padding: 4px; border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08); border: 1px solid #e2e8f0;
                display: flex; align-items: center; justify-content: center; flex-shrink: 0;
            }}
            .zone-container {{ display: flex; gap: 6px; margin-top: auto; }}
            .zone-box {{ 
                flex: 1; padding: 6px 2px; border-radius: 8px; text-align: center; 
                display: flex; flex-direction: column; justify-content: center; 
            }}
            .z-green {{ background: #DCFCE7; border: 1px solid #86EFAC; color: #166534; }}
            .z-yellow {{ background: #FEF9C3; border: 1px solid #FDE047; color: #854D0E; }}
            .z-red {{ background: #FEE2E2; border: 1px solid #FCA5A5; color: #991B1B; }}
            .z-lbl {{ font-size: 8px; font-weight: 700; text-transform: uppercase; margin-bottom: 2px; opacity: 0.9; }}
            .z-val {{ font-size: 11px; font-weight: 800; letter-spacing: 0.5px; }}
        </style>
        
        <div class="asthma-card">
            <div class="card-content">
                <div class="card-header">
                    <div class="card-chip"></div>
                    <div class="card-logo">Asthma Care Card</div>
                </div>
                <div class="card-body">
                    <div class="info-col">
                        <div class="pt-name">{pt_data['prefix']}{pt_data['first_name']} {pt_data['last_name']}</div>
                        <div class="pt-meta">
                            HN: {selected_hn} <br> 
                            Ref. PEFR: <b>{card_best_pefr}</b>
                        </div>
                    </div>
                    <div class="qr-box">
                        <img src="data:image/png;base64,{qr_b64}" width="65" height="65" style="display:block; border-radius: 4px;">
                    </div>
                </div>
                <div class="zone-container">
                    <div class="zone-box z-green">
                        <span class="z-lbl">Normal</span>
                        <span class="z-val">{txt_g}</span>
                    </div>
                    <div class="zone-box z-yellow">
                        <span class="z-lbl">Caution</span>
                        <span class="z-val">{txt_y}</span>
                    </div>
                    <div class="zone-box z-red">
                        <span class="z-lbl">Danger</span>
                        <span class="z-val">{txt_r}</span>
                    </div>
                </div>
            </div>
        </div>
        """
        
        # แสดงผล
        c_main, c_dummy = st.columns([1.5, 1])
        with c_main:
            # 🚨 จุดสำคัญ: ต้องใช้ st.markdown(..., unsafe_allow_html=True) เท่านั้น!
            st.markdown(card_html, unsafe_allow_html=True)
            
            st.write("")
            col_b1, col_b2 = st.columns(2)
            col_b1.link_button("🔗 เปิดหน้าคนไข้", link, use_container_width=True)
            with col_b2.popover("🔗 Copy Link"):
                st.code(link)