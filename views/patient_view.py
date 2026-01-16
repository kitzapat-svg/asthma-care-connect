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

        # --- Header ---
        st.image("https://img.icons8.com/color/96/asthma.png", width=60)
        st.title(f"สวัสดี คุณ{pt_data['first_name']} 👋")
        
        with st.container(border=True):
            c1, c2 = st.columns(2)
            c1.markdown(f"**HN:** `{target_hn}`")
            c2.markdown(f"**อายุ:** {age} ปี")
            st.info(f"🎯 **เป้าหมาย PEFR ของคุณ:** {int(ref_pefr)} L/min")

        # ---------------------------------------------------------
        # ✅ ส่วนแสดงสถานะเทคนิคพ่นยา (Recalculate Days Locally)
        # ---------------------------------------------------------
        tech_status, _, tech_last_date = check_technique_status(pt_visits)
        # หมายเหตุ: เราไม่ใช้ tech_days จากฟังก์ชันแล้ว เพื่อป้องกันความผิดพลาด
        # เราจะคำนวณ days_passed ใหม่เองข้างล่าง

        with st.container(border=True):
            c_icon, c_text = st.columns([1, 4])
            
            with c_icon:
                if tech_status == "valid":
                    st.markdown("# ✅")
                elif tech_status == "overdue":
                    st.markdown("# ⚠️")
                else:
                    st.markdown("# ⚪")
            
            with c_text:
                st.markdown("**สถานะการทบทวนเทคนิคพ่นยา**")
                
                if tech_status == "never":
                    st.warning("ยังไม่เคยได้รับการประเมินเทคนิค (แจ้งเจ้าหน้าที่เมื่อมาตรวจ)")
                
                elif tech_status == "overdue":
                    last_date_str = tech_last_date.strftime('%d/%m/%Y')
                    st.error(f"ครบกำหนดทบทวนแล้ว! (ล่าสุด: {last_date_str})")
                    st.caption(f"กรุณาให้เภสัชกรประเมินเทคนิคใหม่")
                
                else: # valid (ปกติ)
                    # ✅ คำนวณวันใหม่ตรงนี้ (ใช้ วันปัจจุบัน - วันที่สอนจริง)
                    # แปลง tech_last_date เป็น datetime ถ้าจำเป็น
                    if isinstance(tech_last_date, pd.Timestamp):
                        tech_last_date = tech_last_date.to_pydatetime()
                    
                    # คำนวณหา "ผ่านมาแล้วกี่วัน" (Days Passed)
                    delta = datetime.now() - tech_last_date
                    days_passed = delta.days
                    if days_passed < 0: days_passed = 0 # กันพลาดกรณีวันที่ในอนาคต
                    
                    # คำนวณหา "เหลืออีกกี่วัน" (Days Remaining)
                    days_remaining = 365 - days_passed
                    
                    last_date_str = tech_last_date.strftime('%d/%m/%Y')
                    st.success(f"ใช้งานได้ปกติ (สอนล่าสุด: {last_date_str})")
                    
                    # Progress Bar: 
                    # ให้หลอดเต็ม (100%) = เพิ่งสอน (เวลาเหลือเยอะ)
                    # หลอดหมด (0%) = ใกล้ครบปี (เวลาเหลือน้อย)
                    if days_remaining < 0: days_remaining = 0
                    progress_val = int((days_remaining / 365) * 100)
                    progress_val = max(0, min(100, progress_val))
                    
                    # ข้อความ
                    msg = f"ผ่านมาแล้ว {days_passed} วัน (เหลือเวลาอีก {days_remaining} วัน จะครบ 1 ปี)"
                    st.progress(progress_val, text=msg)

        # ---------------------------------------------------------

        # สถานะล่าสุด (Action Plan)
        if not pt_visits.empty:
            pt_visits['date'] = pd.to_datetime(pt_visits['date'])
            last_visit = pt_visits.sort_values(by="date").iloc[-1]
            current_pefr = last_visit['pefr']
            
            zone_name, zone_color, advice = get_action_plan_zone(current_pefr, ref_pefr)
            
            st.divider()
            st.subheader("ผลการประเมินล่าสุด")
            st.metric("ค่า PEFR ล่าสุด", f"{current_pefr} L/min", f"{last_visit['date'].strftime('%d/%m/%Y')}")
            
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
