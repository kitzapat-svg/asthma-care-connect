import streamlit as st
import pandas as pd
import altair as alt
import qrcode
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO
from PIL import Image
from datetime import datetime, timedelta
import numpy as np

# ==========================================
# 1. SETUP & CONFIGURATION
# ==========================================
st.set_page_config(page_title="Asthma Care Connect", layout="centered", page_icon="🫁")

# --- การตั้งค่า Google Sheets ---
SHEET_ID = "1LF9Yi6CXHaiITVCqj9jj1agEdEE9S-37FwnaxNIlAaE"
SHEET_NAME = "asthma_db"

# GID สำหรับโหลดเร็ว (Patient View)
PATIENTS_GID = "0"
VISITS_GID = "1491996218"

# --- 🛡️ SYSTEM CONFIGURATION (Auto-Fallback) ---
# ส่วนนี้จะดักจับ Error กรณีไม่มีไฟล์ secrets.toml ในเครื่อง (Localhost)
# เพื่อให้โปรแกรมยังทำงานต่อได้โดยใช้ค่า Default

# 1. ตั้งค่ารหัสผ่าน (Password)
try:
    if "admin_password" in st.secrets:
        ADMIN_PASSWORD = st.secrets["admin_password"]
    else:
        ADMIN_PASSWORD = "1234"
except Exception:
    # กรณีหาไฟล์ secrets ไม่เจอเลย
    ADMIN_PASSWORD = "1234"

# 2. ตั้งค่า URL (Base URL)
try:
    if "deploy_url" in st.secrets:
        BASE_URL = st.secrets["deploy_url"]
        if BASE_URL.endswith("/"): BASE_URL = BASE_URL[:-1]
    else:
        BASE_URL = "http://localhost:8501"
except Exception:
    BASE_URL = "http://localhost:8501"

# ==========================================
# 2. CALCULATION FORMULAS
# ==========================================

def calculate_predicted_pefr(age, height_cm, gender_prefix):
    if not height_cm or height_cm <= 0: return 0
    is_male = True
    prefix = str(gender_prefix).strip()
    if any(x in prefix for x in ['นาง', 'น.ส.', 'หญิง', 'ด.ญ.', 'Miss', 'Mrs.']):
        is_male = False
     
    if age < 15:
        predicted = -425.5714 + (5.2428 * height_cm)
        return max(predicted, 100)
    else:
        h = height_cm
        a = age
        if is_male:
            pefr_ls = -16.859 + (0.307*a) + (0.141*h) - (0.0018*a**2) - (0.001*a*h)
        else:
            pefr_ls = -31.355 + (0.162*a) - (0.00084*a**2) + (0.391*h) - (0.00099*h**2) - (0.00072*a*h)
        return pefr_ls * 60

def get_percent_predicted(current_pefr, predicted_pefr):
    if predicted_pefr <= 0 or current_pefr <= 0: return 0
    return int((current_pefr / predicted_pefr) * 100)

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================

@st.cache_data(ttl=10)
def load_data_fast(gid):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
        df = pd.read_csv(url, on_bad_lines='skip')
        if 'hn' in df.columns:
            # แปลง HN ให้เป็น text 7 หลักเสมอ
            df['hn'] = df['hn'].astype(str).str.split('.').str[0].str.strip().apply(lambda x: x.zfill(7))
        return df
    except Exception as e:
        st.error(f"โหลดข้อมูลไม่สำเร็จ (Fast Mode): {e}")
        st.stop()

def connect_to_gsheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # ☁️ Priority 1: ลองดึงจาก Secrets (สำหรับ Cloud)
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            return client.open_by_key(SHEET_ID)
    except Exception:
        pass # ถ้าดึงจาก Secrets ไม่ได้ หรือไม่มีไฟล์ Secrets ให้ข้ามไป Priority 2

    # 💻 Priority 2: ลองดึงจากไฟล์ JSON ในเครื่อง (สำหรับ Localhost)
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name('service_account.json', scope)
        client = gspread.authorize(creds)
        return client.open_by_key(SHEET_ID)
    except Exception as e:
        st.error("❌ ไม่สามารถเชื่อมต่อ Google Sheets ได้")
        st.error("กรุณาตรวจสอบว่ามีไฟล์ 'service_account.json' ในโฟลเดอร์ หรือตั้งค่า Secrets บน Cloud แล้ว")
        st.stop()

@st.cache_data(ttl=5) 
def load_data_staff(worksheet_name):
    sh = connect_to_gsheet()
    try:
        worksheet = sh.worksheet(worksheet_name)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        if 'hn' in df.columns:
            df['hn'] = df['hn'].astype(str).str.strip().apply(lambda x: x.zfill(7))
        return df
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"ไม่พบแท็บ '{worksheet_name}'")
        st.stop()

def save_visit_data(data_dict):
    sh = connect_to_gsheet()
    worksheet = sh.worksheet("visits")
    row_to_append = [
        str(data_dict["hn"]), # ลบ ' ออกแล้ว (ต้องตั้งค่า Sheet เป็น Plain Text)
        data_dict["date"], data_dict["pefr"],
        data_dict["control_level"], data_dict["controller"], data_dict["reliever"],
        data_dict["adherence"], data_dict["drp"], data_dict["advice"],
        data_dict["technique_check"], data_dict["next_appt"], 
        data_dict["note"],
        data_dict["is_new_case"] # เพิ่มคอลัมน์ใหม่
    ]
    worksheet.append_row(row_to_append)
    load_data_staff.clear()
    load_data_fast.clear()

def save_patient_data(data_dict):
    sh = connect_to_gsheet()
    worksheet = sh.worksheet("patients")
    # ลบ ' ออกเพื่อให้ HN ลงเป็นตัวเลข (ต้องตั้งค่า Sheet เป็น Plain Text)
    hn_val = str(data_dict['hn']) 
    row_to_append = [
        hn_val,
        data_dict["prefix"],
        data_dict["first_name"],
        data_dict["last_name"],
        data_dict["dob"],
        data_dict["best_pefr"],
        data_dict["height"]
    ]
    worksheet.append_row(row_to_append)
    load_data_staff.clear()
    load_data_fast.clear()

def mask_text(text):
    if not isinstance(text, str): return str(text)
    if len(text) <= 2: return text[0] + "x" * (len(text)-1)
    return text[:2] + "x" * (len(text)-2)

def generate_qr(data):
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf)
    return buf.getvalue()

def get_action_plan_zone(current_pefr, reference_pefr):
    if current_pefr <= 0: return "Not Done", "gray", "ไม่ได้เป่า Peak Flow"
    if reference_pefr <= 0: return "Unknown", "gray", "ไม่มีข้อมูลอ้างอิง"
    percent = (current_pefr / reference_pefr) * 100
    if percent >= 80:
        return "Green Zone", "green", "คุมได้ดี"
    elif percent >= 50:
        return "Yellow Zone", "orange", "เริ่มมีอาการ"
    else:
        return "Red Zone", "red", "อันตราย"

def check_technique_status(pt_visits_df):
    if pt_visits_df.empty: return "never", 0, None
    reviews = pt_visits_df[pt_visits_df['technique_check'].astype(str).str.contains('ทำ', na=False)].copy()
    if reviews.empty: return "never", 0, None
    reviews['date'] = pd.to_datetime(reviews['date'])
    last_date = reviews['date'].max()
    days_remaining = (last_date + timedelta(days=365) - pd.to_datetime("today").normalize()).days
    if days_remaining < 0:
        return "overdue", abs(days_remaining), last_date
    else:
        return "ok", days_remaining, last_date

def plot_pefr_chart(visits_df, reference_pefr):
    data = visits_df.copy()
    data = data[data['pefr'] > 0]
     
    if data.empty:
        return alt.Chart(pd.DataFrame({'date':[], 'pefr':[]})).mark_text(text="ไม่มีข้อมูลกราฟ PEFR")

    data['date'] = pd.to_datetime(data['date'])
    ref_val = reference_pefr if reference_pefr > 0 else data['pefr'].max()
     
    def get_color(val):
        if val >= ref_val * 0.8: return 'green'
        elif val >= ref_val * 0.5: return 'orange'
        else: return 'red'
    data['color'] = data['pefr'].apply(get_color)

    base = alt.Chart(data).encode(
        x=alt.X('date', title='วันที่', axis=alt.Axis(format='%d/%m/%Y')),
        y=alt.Y('pefr', title='PEFR (L/min)', scale=alt.Scale(domain=[0, ref_val + 150])),
        tooltip=[alt.Tooltip('date', format='%d/%m/%Y'), 'pefr']
    )
    line = base.mark_line(color='gray').encode()
    points = base.mark_circle(size=100).encode(color=alt.Color('color', scale=None))
    rule_green = alt.Chart(pd.DataFrame({'y': [ref_val * 0.8]})).mark_rule(color='green', strokeDash=[5, 5]).encode(y='y')
    rule_red = alt.Chart(pd.DataFrame({'y': [ref_val * 0.5]})).mark_rule(color='red', strokeDash=[5, 5]).encode(y='y')
    return (line + points + rule_green + rule_red).properties(height=350).interactive()

def render_dashboard(visits_df):
    if visits_df.empty:
        st.warning("ยังไม่มีข้อมูลการตรวจเยี่ยม")
        return

    # เตรียมข้อมูลเบื้องต้น
    df = visits_df.copy()
    # แปลงคอลัมน์ date เป็น datetime object เพื่อให้คำนวณง่าย
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['month_year'] = df['date'].dt.strftime('%Y-%m') 

    # ==========================================
    # 🆕 ส่วนที่เพิ่มใหม่: Summary of Today
    # ==========================================
    # หาวันที่ปัจจุบัน (รูปแบบ YYYY-MM-DD ให้ตรงกับใน Sheet)
    today_str = datetime.now().strftime('%Y-%m-%d')
    today_display = datetime.now().strftime('%d/%m/%Y')
    
    # กรองข้อมูลเฉพาะวันนี้
    today_df = df[df['date'].dt.strftime('%Y-%m-%d') == today_str]
    
    # คำนวณยอด
    count_today_total = len(today_df)
    
    # คำนวณยอด New Case วันนี้ (ป้องกัน Error กรณีไม่มี column)
    if 'is_new_case' in df.columns:
        today_new_cases = today_df[today_df['is_new_case'].astype(str).str.upper() == 'TRUE']
        count_today_new = len(today_new_cases)
    else:
        count_today_new = 0
        
    # ยอดผู้ป่วยสะสมทั้งหมด (นับจาก HN ไม่ซ้ำ)
    total_patients = len(df['hn'].unique())

    st.subheader(f"📅 สรุปยอดประจำวัน ({today_display})")
    
    # แสดงผลเป็น Card ตัวเลข 3 ช่อง
    m1, m2, m3 = st.columns(3)
    
    m1.metric(
        label="ผู้รับบริการวันนี้", 
        value=f"{count_today_total} คน",
        delta="Visits",
        delta_color="off"
    )
    
    m2.metric(
        label="ผู้ป่วยใหม่วันนี้ (New Case)", 
        value=f"{count_today_new} คน",
        delta=f"+{count_today_new}" if count_today_new > 0 else "0",
        delta_color="normal" # สีเขียวถ้ามีคนไข้ใหม่
    )
    
    m3.metric(
        label="ทะเบียนผู้ป่วยสะสม", 
        value=f"{total_patients} คน",
        help="นับจำนวน HN ที่ไม่ซ้ำกันทั้งหมดในระบบ"
    )
    
    st.divider() # ขีดเส้นคั่นก่อนเริ่มกราฟเดิม

    # ==========================================
    # กราฟเดิม (KPI 1-4)
    # ==========================================
    
    # KPI 1: สัดส่วนการคุมอาการ
    st.subheader("1. ภาพรวมการควบคุมโรค (Latest Status)")
    latest_visits = df.sort_values('date').groupby('hn').tail(1)
    
    control_counts = latest_visits['control_level'].value_counts().reset_index()
    control_counts.columns = ['status', 'count']
    
    domain = ['Controlled', 'Partly Controlled', 'Uncontrolled']
    range_ = ['#66BB6A', '#FFCA28', '#EF5350'] 

    pie = alt.Chart(control_counts).mark_arc(innerRadius=50).encode(
        theta=alt.Theta(field="count", type="quantitative"),
        color=alt.Color(field="status", type="nominal", scale=alt.Scale(domain=domain, range=range_), legend=alt.Legend(title="สถานะ")),
        tooltip=['status', 'count']
    ).properties(title="สัดส่วนผู้ป่วยแยกตามระดับการควบคุม")
    
    text = pie.mark_text(radius=140).encode(
        text=alt.Text("count", format=".0f"),
        order=alt.Order("status"),
        color=alt.value("black")  
    )
    st.altair_chart(pie + text, use_container_width=True)

    # KPI 2: สถิติรายเดือน
    st.subheader("2. ปริมาณงานรายเดือน (Workload)")
    monthly_visits = df.groupby('month_year').size().reset_index(name='total_visits')
    
    if 'is_new_case' in df.columns:
        new_cases = df[df['is_new_case'].astype(str).str.upper() == 'TRUE']
        monthly_new = new_cases.groupby('month_year').size().reset_index(name='new_cases')
    else:
        monthly_new = pd.DataFrame(columns=['month_year', 'new_cases'])

    trend_df = pd.merge(monthly_visits, monthly_new, on='month_year', how='left').fillna(0)
    trend_long = trend_df.melt('month_year', var_name='type', value_name='count')
    
    line_chart = alt.Chart(trend_long).mark_line(point=True).encode(
        x=alt.X('month_year', title='เดือน-ปี'),
        y=alt.Y('count', title='จำนวน (ครั้ง/คน)'),
        color=alt.Color('type', legend=alt.Legend(title="ประเภท"), scale=alt.Scale(domain=['total_visits', 'new_cases'], range=['#42A5F5', '#AB47BC'])),
        tooltip=['month_year', 'type', 'count']
    ).properties(height=300)
    st.altair_chart(line_chart, use_container_width=True)

    # KPI 3 & 4
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("3. การใช้ยา Controller")
        meds = df['controller'].astype(str).str.split(', ').explode()
        med_counts = meds.value_counts().reset_index()
        med_counts.columns = ['medicine', 'usage_count']
        med_counts = med_counts[med_counts['medicine'] != 'nan']
        
        bar_med = alt.Chart(med_counts.head(10)).mark_bar().encode(
            x=alt.X('usage_count', title='จำนวนครั้งที่จ่าย'),
            y=alt.Y('medicine', sort='-x', title='ชื่อยา'),
            color=alt.value('#26A69A'),
            tooltip=['medicine', 'usage_count']
        )
        st.altair_chart(bar_med, use_container_width=True)
    
    with c2:
        st.subheader("🚨 กลุ่มเสี่ยง (Uncontrolled)")
        high_risk = latest_visits[latest_visits['control_level'] == 'Uncontrolled'][['hn', 'date', 'pefr', 'note']]
        if not high_risk.empty:
            st.dataframe(high_risk, hide_index=True, use_container_width=True)
        else:
            st.success("ไม่มีผู้ป่วย Uncontrolled ในขณะนี้")
# ==========================================
# 4. MAIN APP LOGIC
# ==========================================
query_params = st.query_params
target_hn = query_params.get("hn", None)

if target_hn:
    # ------------------------------------------------
    # 🟢 PATIENT VIEW (Fast Mode) - NO LOGIN REQUIRED
    # ------------------------------------------------
     
    patients_db_fast = load_data_fast(PATIENTS_GID)
    visits_db_fast = load_data_fast(VISITS_GID)

    target_hn = str(target_hn).strip().zfill(7)
    patient = patients_db_fast[patients_db_fast['hn'] == target_hn]
     
    if not patient.empty:
        pt_data = patient.iloc[0]
        masked_name = f"{pt_data['prefix']}{mask_text(pt_data['first_name'])} {mask_text(pt_data['last_name'])}"
         
        dob = pd.to_datetime(pt_data['dob'])
        age = (datetime.now() - dob).days // 365
        height = pt_data.get('height', 0)
        predicted_pefr = calculate_predicted_pefr(age, height, pt_data['prefix'])
        ref_pefr = predicted_pefr if predicted_pefr > 0 else pt_data['best_pefr']

        c1, c2 = st.columns([1, 4])
        with c1: st.title("🫁")
        with c2:
            st.markdown(f"### HN: {target_hn}")
            st.markdown(f"**ชื่อ-สกุล:** {masked_name}")
            st.caption("🔒 ข้อมูลผู้ป่วย (PDPA)")
        st.divider()

        pt_visits = visits_db_fast[visits_db_fast['hn'] == target_hn].copy()
         
        tech_status, tech_days, tech_last_date = check_technique_status(pt_visits)
        if tech_status == "overdue": st.error(f"⚠️ เตือน: ขาดทบทวนพ่นยา {tech_days} วัน")
        elif tech_status == "ok": st.success(f"✅ เทคนิคพ่นยา: ปกติ (เหลือ {tech_days} วัน)")

        if not pt_visits.empty:
            last_visit = pt_visits.iloc[-1]
            zone_name, zone_color, advice = get_action_plan_zone(last_visit['pefr'], ref_pefr)
            pct_std = get_percent_predicted(last_visit['pefr'], predicted_pefr)

            st.info(f"📋 **สถานะล่าสุด ({last_visit['date']})**")
            m1, m2, m3 = st.columns(3)
            pefr_show = last_visit['pefr'] if last_visit['pefr'] > 0 else "N/A"
            m1.metric("PEFR", f"{pefr_show}")
            m2.metric("% มาตรฐาน", f"{pct_std}%", help=f"เทียบค่ามาตรฐาน: {int(predicted_pefr)}")
            m3.markdown(f"โซน: :{zone_color}[**{zone_name}**]")
            st.write(f"**💊 Controller:** {last_visit.get('controller', '-')}")
             
            if 'note' in last_visit and str(last_visit['note']).strip() != "" and str(last_visit['note']).lower() != "nan":
                st.info(f"ℹ️ **หมายเหตุ:** {last_visit['note']}")

            st.subheader("📈 กราฟแนวโน้ม")
            chart = plot_pefr_chart(pt_visits, ref_pefr)
            st.altair_chart(chart, use_container_width=True)
            st.caption(f"เส้นประ (ค่าเป้าหมาย): {int(ref_pefr)}")
             
            with st.expander("ดูประวัติ"):
                st.dataframe(pt_visits.sort_values(by="date", ascending=False), hide_index=True)
        else:
            st.warning("ไม่มีประวัติ")
    else:
        st.error(f"ไม่พบข้อมูล HN: {target_hn}")

else:
    # ------------------------------------------------
    # 🔵 STAFF VIEW - 🔐 LOGIN REQUIRED
    # ------------------------------------------------
    st.sidebar.header("🏥 Asthma Clinic")

    # --- Login System ---
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.title("🔐 เข้าสู่ระบบเจ้าหน้าที่")
        col1, col2 = st.columns([2, 1])
        with col1:
            password = st.text_input("กรุณาใส่รหัสผ่าน", type="password")
            if st.button("Login"):
                if password == ADMIN_PASSWORD:
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error("❌ รหัสผ่านไม่ถูกต้อง")
        st.stop()

    # --- Staff Working Area ---
    if st.sidebar.button("🔓 ออกจากระบบ"):
        st.session_state.logged_in = False
        st.rerun()

    st.sidebar.success(f"สถานะ: เจ้าหน้าที่ (Logged In)")
    
    patients_db = load_data_staff("patients")
    visits_db = load_data_staff("visits")

    mode = st.sidebar.radio("เมนูหลัก", ["🔍 ค้นหา/บันทึกอาการ", "➕ ลงทะเบียนผู้ป่วยใหม่", "📊 Dashboard ภาพรวม"])

    # ==========================================
    # 📊 MODE 1: DASHBOARD
    # ==========================================
    if mode == "📊 Dashboard ภาพรวม":
        st.title("📊 Dashboard สรุปสถานะคลินิก")
        st.info("ข้อมูลวิเคราะห์จากฐานข้อมูล Visits ทั้งหมด")
        render_dashboard(visits_db)

    # ==========================================
    # ➕ MODE 2: REGISTER NEW PATIENT
    # ==========================================
    elif mode == "➕ ลงทะเบียนผู้ป่วยใหม่":
        st.title("➕ ลงทะเบียนผู้ป่วยรายใหม่")
        st.info("ระบบจะจัดรูปแบบ HN เป็น 7 หลักให้อัตโนมัติ")

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
            
            submitted_reg = st.form_submit_button("✅ ลงทะเบียน")

            if submitted_reg:
                if not reg_hn_input or not reg_fname or not reg_lname:
                    st.error("❌ กรุณากรอกข้อมูลให้ครบถ้วน")
                    st.stop()
                
                formatted_hn = str(reg_hn_input).strip().zfill(7)
                if formatted_hn in patients_db['hn'].values:
                    st.error(f"❌ ลงทะเบียนไม่สำเร็จ: HN {formatted_hn} มีอยู่ในระบบแล้ว")
                    st.stop()
                
                dup_name = patients_db[
                    (patients_db['first_name'] == reg_fname) & 
                    (patients_db['last_name'] == reg_lname)
                ]
                if not dup_name.empty:
                    st.error(f"❌ ลงทะเบียนไม่สำเร็จ: ชื่อ {reg_fname} {reg_lname} มีอยู่ในระบบแล้ว")
                    st.stop()
                
                new_pt_data = {
                    "hn": formatted_hn,
                    "prefix": reg_prefix,
                    "first_name": reg_fname,
                    "last_name": reg_lname,
                    "dob": str(reg_dob),
                    "best_pefr": reg_best_pefr,
                    "height": reg_height
                }
                
                try:
                    with st.spinner("กำลังลงทะเบียน..."):
                        save_patient_data(new_pt_data)
                    st.success(f"🎉 ลงทะเบียน HN: {formatted_hn} เรียบร้อยแล้ว!")
                    st.info("ไปที่เมนู 'ค้นหา' เพื่อเริ่มบันทึกการรักษาได้เลยครับ")
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาด: {e}")

# ==========================================
    # 🔍 MODE 3: SEARCH & VISIT RECORD
    # ==========================================
    else:
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
            
            # คำนวณค่าอ้างอิงสำหรับคำนวณ % (ใช้ Predicted หรือ Personal Best)
            ref_pefr = predicted_pefr if predicted_pefr > 0 else pt_data['best_pefr']
            
            st.title(f"{pt_data['prefix']}{pt_data['first_name']} {pt_data['last_name']}")
            
            # --- ข้อมูลพื้นฐาน ---
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("HN", pt_data['hn'])
            c2.metric("อายุ", f"{age} ปี")
            c3.metric("ส่วนสูง", f"{height} cm")
            c4.metric("Standard PEFR", f"{int(predicted_pefr)}")

            # --- 🆕 ส่วนที่เพิ่ม: แสดงสถานะล่าสุด (เหมือน Patient View) ---
            if not pt_visits.empty:
                # เรียงวันที่เพื่อให้ได้ visit ล่าสุดจริงๆ
                pt_visits_sorted = pt_visits.sort_values(by="date")
                last_visit = pt_visits_sorted.iloc[-1]
                
                # คำนวณโซนและ %
                current_pefr = last_visit['pefr']
                zone_name, zone_color, advice = get_action_plan_zone(current_pefr, ref_pefr)
                pct_std = get_percent_predicted(current_pefr, ref_pefr)
                
                # แสดงผล
                st.markdown("---")
                st.info(f"📋 **สถานะล่าสุด ({last_visit['date']})**")
                
                s1, s2, s3, s4 = st.columns(4)
                
                pefr_show = current_pefr if current_pefr > 0 else "N/A"
                s1.metric("PEFR ล่าสุด", f"{pefr_show}")
                
                s2.metric("% มาตรฐาน", f"{pct_std}%", help=f"เทียบค่ามาตรฐาน: {int(ref_pefr)}")
                
                with s3:
                    st.markdown("โซนอาการ")
                    st.markdown(f":{zone_color}[**{zone_name}**]")
                
                with s4:
                    st.markdown("ระดับการควบคุม")
                    ctrl = last_visit.get('control_level', '-')
                    if ctrl == "Controlled": st.success(ctrl)
                    elif ctrl == "Partly Controlled": st.warning(ctrl)
                    elif ctrl == "Uncontrolled": st.error(ctrl)
                    else: st.write(ctrl)

            # --- Alerts ---
            st.divider()
            
            # Alert Tech
            tech_status, tech_days, tech_last_date = check_technique_status(pt_visits)
            if tech_status == "overdue": st.error(f"🚨 ขาดทบทวนพ่นยา {tech_days} วัน!")
            elif tech_status == "never": st.error(f"🚨 ยังไม่เคยสอนพ่นยา!")
            else: st.success(f"✅ สอนพ่นยาแล้ว (เหลือ {tech_days} วัน)")
            
            # Alert DRP
            if not pt_visits.empty:
                last_visit_row = pt_visits.sort_values(by="date").iloc[-1] # ใช้ตัวแปร Local
                last_drp_text = str(last_visit_row['drp']).strip()
                if last_drp_text != "" and last_drp_text != "-" and last_drp_text.lower() != "nan":
                    d_date = pd.to_datetime(last_visit_row['date']).strftime('%d/%m/%Y')
                    st.warning(f"💊 **DRP ล่าสุด ({d_date}):** {last_drp_text}")

            st.subheader("📈 กราฟติดตามอาการ")
            if not pt_visits.empty:
                chart = plot_pefr_chart(pt_visits, ref_pefr)
                st.altair_chart(chart, use_container_width=True)

            with st.expander("ประวัติการรักษา"):
                st.dataframe(pt_visits.sort_values(by="date", ascending=False), use_container_width=True)
                
            st.divider()
            st.subheader("📝 บันทึก Visit")
            
            with st.form("new_visit", clear_on_submit=True):
                col_a, col_b = st.columns(2)
                v_date = col_a.date_input("วันที่", value=datetime.today())
                v_is_new = col_a.checkbox("🆕 เป็นผู้ป่วยรายใหม่ (New Case)") 
                
                with col_b:
                    v_pefr = st.number_input("PEFR (L/min)", 0, 900, step=10)
                    v_no_pefr = st.checkbox("ไม่ได้เป่า Peak Flow (N/A)")
                
                if predicted_pefr > 0 and v_pefr > 0:
                    pct = int((v_pefr / predicted_pefr) * 100)
                    st.caption(f"💡 คิดเป็น **{pct}%** ของค่ามาตรฐาน ({int(predicted_pefr)}) (คำนวณเมื่อกดบันทึก)")

                v_control = st.radio("Control", ["Controlled", "Partly Controlled", "Uncontrolled"], horizontal=True)
                
                c_med1, c_med2 = st.columns(2)
                v_cont = c_med1.multiselect("Controller", ["Seretide", "Budesonide", "Symbicort"])
                v_rel = c_med2.multiselect("Reliever", ["Salbutamol", "Berodual"])
                
                c_adh, c_chk = st.columns(2)
                with c_adh:
                    v_adh = st.slider("ความร่วมมือ (%)", 0, 100, 100)
                    v_relative_pickup = st.checkbox("ญาติรับยาแทน / ประเมินไม่ได้", help="หากเลือก ความร่วมมือจะเป็น 0 และจะระบุในหมายเหตุ")
                with c_chk:
                    st.write("") 
                    st.write("")
                    v_tech = st.checkbox("✅ สอนเทคนิควันนี้")
                
                v_drp = st.text_area("DRP (ปัญหาการใช้ยา)")
                v_adv = st.text_area("Advice (คำแนะนำ)")
                v_note = st.text_input("หมายเหตุ (Note)")
                v_next = st.date_input("นัดถัดไป")
                
                submitted = st.form_submit_button("💾 บันทึกข้อมูล")

                if submitted:
                    actual_pefr = 0 if v_no_pefr else v_pefr
                    
                    if v_relative_pickup:
                        actual_adherence = 0
                        prefix = "[ญาติรับแทน] "
                        final_note = prefix + v_note if v_note else prefix.strip()
                    else:
                        actual_adherence = v_adh
                        final_note = v_note

                    new_data = {
                        "hn": selected_hn, "date": str(v_date), "pefr": actual_pefr,
                        "control_level": v_control, "controller": ", ".join(v_cont),
                        "reliever": ", ".join(v_rel), 
                        "adherence": actual_adherence,
                        "drp": v_drp, 
                        "advice": v_adv,
                        "technique_check": "ทำ" if v_tech else "ไม่ทำ",
                        "next_appt": str(v_next),
                        "note": final_note,
                        "is_new_case": "TRUE" if v_is_new else "FALSE"
                    }
                    try:
                        save_visit_data(new_data)
                        st.success("บันทึกสำเร็จ")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
            
            st.divider()
            st.subheader("📇 Asthma Card")
            
            link = f"{BASE_URL}/?hn={selected_hn}"
            
            c_q, c_t = st.columns([1,2])
            c_q.image(generate_qr(link), width=150)
            
            with c_t:
                st.markdown(f"**{pt_data['first_name']} {pt_data['last_name']}**")
                st.markdown(f"**HN:** `{selected_hn}`")
                st.markdown(f"Predicted PEFR: {int(predicted_pefr)}")
                st.link_button("🔗 เปิดลิงก์คนไข้", link, type="primary")
            
            st.caption(f"Direct Link: {link}")
