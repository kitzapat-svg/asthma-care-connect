import streamlit as st
import pandas as pd
from datetime import datetime
from utils.calculations import (
    calculate_predicted_pefr, 
    get_action_plan_zone, 
    plot_pefr_chart, 
    check_technique_status
)

def render_patient_view(target_hn, patients_db, visits_db):
    if target_hn in patients_db['hn'].values:
        # ดึงข้อมูลคนไข้
        pt_data = patients_db[patients_db['hn'] == target_hn].iloc[0]
        pt_visits = visits_db[visits_db['hn'] == target_hn]
        
        # คำนวณข้อมูลพื้นฐาน
        dob = pd.to_datetime(pt_data['dob'])
        age = (datetime.now() - dob).days // 365
        height = pt_data['height']
        predicted_pefr = calculate_predicted_pefr(age, height, pt_data['prefix'])
        ref_pefr = predicted_pefr if predicted_pefr > 0 else pt_data['best_pefr']

        # --- Helper Function สำหรับ Mask ชื่อ ---
        def mask_text(text):
            if pd.isna(text) or str(text).strip() == "": return "xxx"
            text = str(text)
            if len(text) <= 2: return text[0] + "xxx"
            return text[:2] + "xxx"

        masked_fname = mask_text(pt_data['first_name'])
        masked_lname = mask_text(pt_data['last_name'])
        display_name = f"{pt_data['prefix']}{masked_fname} {masked_lname}"

        # --- Header ---
        st.image("https://img.icons8.com/color/96/asthma.png", width=60)
        st.title(f"สวัสดี {display_name} 👋")
        
        with st.container(border=True):
            c1, c2 = st.columns(2)
            c1.markdown(f"**HN:** `{target_hn}`")
            c2.markdown(f"**อายุ:** {age} ปี")
            st.info(f"🎯 **เป้าหมาย PEFR ของคุณ:** {int(ref_pefr)} L/min")

        # ---------------------------------------------------------
        # 📅 ส่วนแสดงวันนัดถัดไป (เพิ่มใหม่)
        # ---------------------------------------------------------
        if not pt_visits.empty:
            # เรียงข้อมูลเอาล่าสุดขึ้นมา
            last_visit = pt_visits.sort_values(by="date").iloc[-1]
            next_appt = str(last_visit.get('next_appt', '-')).strip()
            
            # ถ้ามีวันนัด (ไม่ใช่ขีด หรือว่าง)
            if next_appt and next_appt not in ['-', '', 'nan', 'None']:
                try:
                    # พยายามแปลงรูปแบบวันที่ให้สวยงาม (ถ้าทำได้)
                    next_appt_dt = pd.to_datetime(next_appt)
                    formatted_date = next_appt_dt.strftime('%d/%m/%Y')
                    
                    # คำนวณอีกกี่วันถึงนัด
                    days_to_appt = (next_appt_dt - datetime.now()).days + 1
                    
                    if days_to_appt < 0:
                        msg_status = f"(เลยนัดมา {abs(days_to_appt)} วันแล้ว)"
                        icon = "⚠️"
                        color = "red"
                    elif days_to_appt == 0:
                        msg_status = "(วันนัดคือวันนี้!)"
                        icon = "🚨"
                        color = "red"
                    else:
                        msg_status = f"(อีก {days_to_appt} วัน)"
                        icon = "📅"
                        color = "blue"

                    st.info(f"{icon} **นัดครั้งถัดไป:** {formatted_date} {msg_status}")
                    
                except:
                    # ถ้าแปลงวันที่ไม่ได้ ให้แสดงข้อความเดิมไปเลย
                    st.info(f"📅 **นัดครั้งถัดไป:** {next_appt}")

        # ---------------------------------------------------------

        # --- ส่วนแสดงสถานะเทคนิคพ่นยา ---
        tech_status, _, tech_last_date = check_technique_status(pt_visits)
        
        with st.container(border=True):
            c_icon, c_text = st.columns([1, 4])
            with c_icon:
                if tech_status == "valid": st.markdown("# ✅")
                elif tech_status == "overdue": st.markdown("# ⚠️")
                else: st.markdown("# ⚪")
            
            with c_text:
                st.markdown("**สถานะการทบทวนเทคนิคพ่นยา**")
                if tech_status == "never":
                    st.warning("ยังไม่เคยได้รับการประเมินเทคนิค")
                elif tech_status == "overdue":
                    last_date_str = tech_last_date.strftime('%d/%m/%Y')
                    st.error(f"ครบกำหนดทบทวนแล้ว! (ล่าสุด: {last_date_str})")
                else: 
                    if isinstance(tech_last_date, pd.Timestamp):
                        tech_last_date = tech_last_date.to_pydatetime()
                    delta = datetime.now() - tech_last_date
                    days_passed = delta.days
                    if days_passed < 0: days_passed = 0
                    days_remaining = 365 - days_passed
                    
                    last_date_str = tech_last_date.strftime('%d/%m/%Y')
                    st.success(f"ใช้งานได้ปกติ (สอนล่าสุด: {last_date_str})")
                    
                    if days_remaining < 0: days_remaining = 0
                    progress_val = int((days_remaining / 365) * 100)
                    progress_val = max(0, min(100, progress_val))
                    
                    msg = f"ผ่านมาแล้ว {days_passed} วัน (เหลือเวลาอีก {days_remaining} วัน จะครบ 1 ปี)"
                    st.progress(progress_val, text=msg)

        # --- ส่วนแสดงผลการประเมินล่าสุด (Action Plan) ---
        if not pt_visits.empty:
            # (ใช้ตัวแปร last_visit จากข้างบนได้เลย)
            current_pefr = last_visit['pefr']
            visit_date_str = pd.to_datetime(last_visit['date']).strftime('%d/%m/%Y')
            
            zone_name, zone_color, advice = get_action_plan_zone(current_pefr, ref_pefr)
            
            st.divider()
            st.subheader("ผลการประเมินล่าสุด")
            st.metric("ค่า PEFR ล่าสุด", f"{current_pefr} L/min", f"{visit_date_str}")
            
            st.markdown(f"""
            <div style="padding: 20px; border-radius: 10px; background-color: {zone_color}20; border: 2px solid {zone_color};">
                <h3 style="color: {zone_color}; margin:0;">{zone_name}</h3>
                <p style="margin-top: 10px;"><strong>คำแนะนำ:</strong> {advice}</p>
            </div>
            """, unsafe_allow_html=True)
            
            st.subheader("แนวโน้มอาการ (Trends)")
            chart = plot_pefr_chart(pt_visits, ref_pefr)
            st.altair_chart(chart, use_container_width=True)
            
        else:
            st.warning("ยังไม่มีประวัติการตรวจ")

    else:
        st.error("❌ ไม่พบข้อมูลผู้ป่วยรายนี้")
