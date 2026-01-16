import streamlit as st
import pandas as pd
from datetime import datetime

# Import ฟังก์ชันจาก Utils
from utils.gsheet_handler import load_data_fast, load_data_staff
from utils.calculations import (
    calculate_predicted_pefr, 
    get_action_plan_zone, 
    plot_pefr_chart, 
    check_technique_status  # ✅ Import ฟังก์ชันตรวจสอบเทคนิคพ่นยา
)

# Import หน้าจอของ Staff
from views.staff_action import render_register_patient, render_search_patient
from views.staff_dashboard import render_dashboard

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Asthma Care Connect",
    page_icon="🫁",
    layout="centered"
)

# --- AUTHENTICATION (Mock) ---
def check_password():
    """Returns `True` if the user had the correct password."""
    def password_entered():
        if st.session_state["password"] == st.secrets.get("password", "admin123"):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password.
        st.sidebar.text_input(
            "🔑 รหัสผ่านเจ้าหน้าที่", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # Password incorrect, show input + error.
        st.sidebar.text_input(
            "🔑 รหัสผ่านเจ้าหน้าที่", type="password", on_change=password_entered, key="password"
        )
        st.sidebar.error("😕 รหัสผ่านไม่ถูกต้อง")
        return False
    else:
        # Password correct.
        return True

# ==========================================
# 🏥 PATIENT VIEW (มุมมองคนไข้ - เข้าผ่าน QR/Link)
# ==========================================
if "hn" in st.query_params:
    target_hn = st.query_params["hn"]
    
    # โหลดข้อมูลแบบ Fast (Cache นานหน่อย)
    patients_db = load_data_fast("patients")
    visits_db = load_data_fast("visits")
    
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

        # --- ส่วนแสดงผล ---
        st.image("https://img.icons8.com/color/96/asthma.png", width=60)
        st.title(f"สวัสดี คุณ{pt_data['first_name']} 👋")
        
        # Card ข้อมูลส่วนตัว
        with st.container(border=True):
            c1, c2 = st.columns(2)
            c1.markdown(f"**HN:** `{target_hn}`")
            c2.markdown(f"**อายุ:** {age} ปี")
            st.info(f"🎯 **เป้าหมาย PEFR ของคุณ:** {int(ref_pefr)} L/min")

        # ---------------------------------------------------------
        # ✅ ส่วนแสดงสถานะเทคนิคพ่นยา (ใหม่)
        # ---------------------------------------------------------
        tech_status, tech_days, tech_last_date = check_technique_status(pt_visits)

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
                    st.caption(f"เลยกำหนดมา {tech_days} วัน กรุณาให้เภสัชกรประเมินใหม่")
                
                else: # valid
                    last_date_str = tech_last_date.strftime('%d/%m/%Y')
                    st.success(f"ล่าสุดเมื่อ: {last_date_str}")
                    # Progress Bar นับถอยหลัง 1 ปี (365 วัน)
                    days_left = 365 - tech_days
                    progress_val = max(0, min(100, int((days_left)/365*100)))
                    st.progress(progress_val, text=f"อีก {days_left} วัน จะครบ 1 ปี")
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
            
            # กราฟ
            st.subheader("แนวโน้มอาการ (Trends)")
            chart = plot_pefr_chart(pt_visits, ref_pefr)
            st.altair_chart(chart, use_container_width=True)
            
        else:
            st.warning("ยังไม่มีประวัติการตรวจ")

    else:
        st.error("❌ ไม่พบข้อมูลผู้ป่วยรายนี้")

# ==========================================
# 👩‍⚕️ STAFF VIEW (มุมมองเจ้าหน้าที่)
# ==========================================
else:
    st.sidebar.image("https://img.icons8.com/fluency/96/doctor-male.png", width=80)
    st.sidebar.title("🔐 สำหรับเจ้าหน้าที่")
    
    if check_password():
        st.sidebar.success(f"สถานะ: เจ้าหน้าที่ (Logged In)")
        
        # ปุ่ม Logout
        if st.sidebar.button("🔓 ออกจากระบบ"):
            st.session_state["password_correct"] = False
            st.rerun()
            
        st.sidebar.divider()
        
        # Load Data (Real-time)
        patients_db = load_data_staff("patients")
        visits_db = load_data_staff("visits")
        
        # Menu Navigation
        mode = st.sidebar.radio(
            "เมนูหลัก", 
            ["🔍 ค้นหา/บันทึกอาการ", "➕ ลงทะเบียนผู้ป่วยใหม่", "📊 Dashboard ภาพรวม"]
        )
        
        if mode == "🔍 ค้นหา/บันทึกอาการ":
            # ส่ง base_url เพื่อใช้สร้าง QR Code
            # (บน Cloud อาจต้องใส่ URL จริง, บน Local ใช้ localhost)
            base_url = "https://asthma-care.streamlit.app" 
            render_search_patient(patients_db, visits_db, base_url)
            
        elif mode == "➕ ลงทะเบียนผู้ป่วยใหม่":
            render_register_patient(patients_db)
            
        elif mode == "📊 Dashboard ภาพรวม":
            # ส่ง patients_db เข้าไปด้วย เพื่อใช้แสดงรายชื่อใน Daily Log
            render_dashboard(visits_db, patients_db)
            
    else:
        st.title("🏥 Asthma Care Connect")
        st.info("👈 กรุณากรอกรหัสผ่านที่แถบด้านซ้ายเพื่อเข้าสู่ระบบ")
