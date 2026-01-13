import streamlit as st
from utils.gsheet_handler import load_data_staff
from views.patient_view import show_patient_view
from views.staff_dashboard import render_dashboard
from views.staff_action import render_register_patient, render_search_patient

st.set_page_config(page_title="Asthma Care Connect", layout="centered", page_icon="🫁")

# --- Security Config ---
if "admin_password" not in st.secrets:
    st.error("❌ ไม่พบรหัสผ่านผู้ดูแลระบบ (กรุณาตั้งค่า admin_password ใน secrets.toml)")
    st.stop()
ADMIN_PASSWORD = st.secrets["admin_password"]

if "deploy_url" in st.secrets:
    BASE_URL = st.secrets["deploy_url"].rstrip("/")
else:
    BASE_URL = "http://localhost:8501"

# --- Main App Logic ---
query_params = st.query_params
target_hn = query_params.get("hn", None)

if target_hn:
    # 🟢 Patient View
    show_patient_view(target_hn)
else:
    # 🔵 Staff View (Login Required)
    st.sidebar.header("🏥 Asthma Clinic")
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.title("🔐 เข้าสู่ระบบเจ้าหน้าที่")
        pwd = st.text_input("รหัสผ่าน", type="password")
        if st.button("Login"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("❌ รหัสผ่านผิด")
        st.stop()

    if st.sidebar.button("🔓 ออกจากระบบ"):
        st.session_state.logged_in = False
        st.rerun()

    st.sidebar.success("สถานะ: เจ้าหน้าที่ (Logged In)")
    
    # Load Data ครั้งเดียว แล้วส่งต่อให้ View อื่นๆ
    patients_db = load_data_staff("patients")
    visits_db = load_data_staff("visits")

    mode = st.sidebar.radio("เมนูหลัก", ["🔍 ค้นหา/บันทึกอาการ", "➕ ลงทะเบียนผู้ป่วยใหม่", "📊 Dashboard ภาพรวม"])

    if mode == "📊 Dashboard ภาพรวม":
        render_dashboard(visits_db)
    elif mode == "➕ ลงทะเบียนผู้ป่วยใหม่":
        render_register_patient(patients_db)
    else:
        render_search_patient(patients_db, visits_db, BASE_URL)