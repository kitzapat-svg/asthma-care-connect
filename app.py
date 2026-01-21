import streamlit as st
import pandas as pd
import io

# Import Utils
# ✅ 1. เพิ่ม log_action ในบรรทัดนี้
from utils.gsheet_handler import load_data_staff, load_data_fast, log_action
from utils.style import load_custom_css

# Import Views
from views.patient_view import render_patient_view
from views.staff_dashboard import render_dashboard
from views.staff_action import render_register_patient, render_search_patient
from views.staff_import import render_import_appointment


# --- Page Config ---
st.set_page_config(page_title="Asthma Care Connect", layout="centered", page_icon="🫁")
load_custom_css()

# ==========================================
# 🔐 SECURITY & CONFIG
# ==========================================
if "admin_password" not in st.secrets:
    st.error("❌ ไม่พบรหัสผ่านผู้ดูแลระบบ (กรุณาตั้งค่า admin_password ใน secrets.toml)")
    st.stop()

ADMIN_PASSWORD = st.secrets["admin_password"]

if "deploy_url" in st.secrets:
    BASE_URL = st.secrets["deploy_url"].rstrip("/")
else:
    BASE_URL = "http://localhost:8501" 

# ==========================================
# 🏥 MAIN APP LOGIC
# ==========================================
query_params = st.query_params
target_token = query_params.get("token", None)

if target_token:
    # ---------------------------------------------------
    # 🟢 PATIENT VIEW (Secure Access)
    # ---------------------------------------------------
    patients_db = load_data_fast("patients")
    
    target_hn = None
    if 'public_token' in patients_db.columns:
        match = patients_db[patients_db['public_token'] == target_token]
        if not match.empty:
            target_hn = match.iloc[0]['hn']
    
    if target_hn:
        visits_db = load_data_fast("visits")
        render_patient_view(target_hn, patients_db, visits_db)
    else:
        st.error("❌ Invalid or Expired Token (ไม่พบข้อมูลผู้ป่วย)")
        if st.button("กลับสู่หน้าหลัก"):
            st.query_params.clear()
            st.rerun()

else:
    # ---------------------------------------------------
    # 🔵 STAFF VIEW (มุมมองเจ้าหน้าที่)
    # ---------------------------------------------------
    st.sidebar.header("🏥 Asthma Clinic")
    
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.title("🔐 เข้าสู่ระบบเจ้าหน้าที่")
        pwd = st.text_input("รหัสผ่าน", type="password")
        if st.button("Login"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.logged_in = True
                log_action("Admin", "Login", "Success") # ✅ 2. บันทึก Log Login
                st.rerun()
            else:
                st.error("❌ รหัสผ่านผิด")
                log_action("Unknown", "Login Failed", "Wrong Password") 
        st.stop() 

    # --- ส่วนทำงานหลัง Login สำเร็จ ---
    st.sidebar.success("สถานะ: เจ้าหน้าที่ (Logged In)")
    
    if st.sidebar.button("🔓 ออกจากระบบ"):
        log_action("Admin", "Logout", "User Initiated") # ✅ 3. บันทึก Log Logout
        st.session_state.logged_in = False
        st.rerun()
    
    st.sidebar.divider()

    # Load Data
    patients_db = load_data_staff("patients")
    visits_db = load_data_staff("visits")

    # Menu
    mode = st.sidebar.radio(
        "เมนูหลัก", 
        [
            "🔍 ค้นหา/บันทึกอาการ", 
            "➕ ลงทะเบียนผู้ป่วยใหม่", 
            "📊 Dashboard ภาพรวม",
            "📥 นำเข้าข้อมูล (Import)"
        ]
    )

    if mode == "🔍 ค้นหา/บันทึกอาการ":
        render_search_patient(patients_db, visits_db, BASE_URL)
        
    elif mode == "➕ ลงทะเบียนผู้ป่วยใหม่":
        render_register_patient(patients_db)
        
    elif mode == "📊 Dashboard ภาพรวม":
        render_dashboard(visits_db, patients_db)
        
    elif mode == "📥 นำเข้าข้อมูล (Import)":
        render_import_appointment(patients_db, visits_db)
