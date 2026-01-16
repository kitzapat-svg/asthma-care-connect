import streamlit as st
import pandas as pd
from datetime import datetime

# Import Utils
from utils.gsheet_handler import load_data_fast, load_data_staff

# Import Views (รวม patient_view ที่เพิ่งสร้าง)
from views.staff_action import render_register_patient, render_search_patient
from views.staff_dashboard import render_dashboard
from views.patient_view import render_patient_view  # <--- ✅ Import ตรงนี้

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Asthma Care Connect",
    page_icon="🫁",
    layout="centered"
)

# --- AUTHENTICATION (Mock) ---
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets.get("password", "admin123"):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.sidebar.text_input("🔑 รหัสผ่านเจ้าหน้าที่", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.sidebar.text_input("🔑 รหัสผ่านเจ้าหน้าที่", type="password", on_change=password_entered, key="password")
        st.sidebar.error("😕 รหัสผ่านไม่ถูกต้อง")
        return False
    else:
        return True

# ==========================================
# 🏥 PATIENT VIEW (มุมมองคนไข้)
# ==========================================
if "hn" in st.query_params:
    target_hn = st.query_params["hn"]
    
    # โหลดข้อมูล
    patients_db = load_data_fast("patients")
    visits_db = load_data_fast("visits")
    
    # ✅ เรียกใช้ฟังก์ชันจาก views/patient_view.py แทนการเขียนโค้ดยาวๆ
    render_patient_view(target_hn, patients_db, visits_db)

# ==========================================
# 👩‍⚕️ STAFF VIEW (มุมมองเจ้าหน้าที่)
# ==========================================
else:
    st.sidebar.image("https://img.icons8.com/fluency/96/doctor-male.png", width=80)
    st.sidebar.title("🔐 สำหรับเจ้าหน้าที่")
    
    if check_password():
        st.sidebar.success(f"สถานะ: เจ้าหน้าที่ (Logged In)")
        
        if st.sidebar.button("🔓 ออกจากระบบ"):
            st.session_state["password_correct"] = False
            st.rerun()
            
        st.sidebar.divider()
        
        patients_db = load_data_staff("patients")
        visits_db = load_data_staff("visits")
        
        mode = st.sidebar.radio(
            "เมนูหลัก", 
            ["🔍 ค้นหา/บันทึกอาการ", "➕ ลงทะเบียนผู้ป่วยใหม่", "📊 Dashboard ภาพรวม"]
        )
        
        if mode == "🔍 ค้นหา/บันทึกอาการ":
            base_url = "https://asthma-care.streamlit.app" 
            render_search_patient(patients_db, visits_db, base_url)
            
        elif mode == "➕ ลงทะเบียนผู้ป่วยใหม่":
            render_register_patient(patients_db)
            
        elif mode == "📊 Dashboard ภาพรวม":
            render_dashboard(visits_db, patients_db)
            
    else:
        st.title("🏥 Asthma Care Connect")
        st.info("👈 กรุณากรอกรหัสผ่านที่แถบด้านซ้ายเพื่อเข้าสู่ระบบ")
