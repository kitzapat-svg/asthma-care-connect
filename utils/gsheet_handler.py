import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURATION ---
SHEET_ID = "1LF9Yi6CXHaiITVCqj9jj1agEdEE9S-37FwnaxNIlAaE"
PATIENTS_SHEET_NAME = "patients"
VISITS_SHEET_NAME = "visits"

def connect_to_gsheet():
    """เชื่อมต่อ Google Sheets โดยรองรับทั้ง st.secrets และไฟล์ json"""
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # 1. ลองเชื่อมต่อผ่าน Secrets (สำหรับ Cloud)
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            return client
    except Exception:
        pass 

    # 2. ลองเชื่อมต่อผ่านไฟล์ JSON (สำหรับ Local)
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name('service_account.json', scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error("❌ ไม่สามารถเชื่อมต่อ Google Sheets ได้ (ตรวจสอบ service_account.json หรือ Secrets)")
        st.stop()

@st.cache_data(ttl=60)
def load_data_fast(worksheet_name):
    """โหลดข้อมูลแบบเร็ว (ใช้ get_all_values)"""
    try:
        client = connect_to_gsheet()
        sh = client.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(worksheet_name)
        data = worksheet.get_all_values()
        
        if not data: return pd.DataFrame()

        headers = data.pop(0)
        df = pd.DataFrame(data, columns=headers)

        # Clean Data: จัดการ HN ให้เป็น 7 หลักเสมอ
        if 'hn' in df.columns:
            # แปลงเป็น str -> ตัดทศนิยมทิ้ง (เผื่อมาเป็น 123.0) -> เติม 0 ข้างหน้า
            df['hn'] = df['hn'].astype(str).str.split('.').str[0].str.strip().apply(lambda x: x.zfill(7))
            
        # Clean Data: แปลงตัวเลข
        cols_to_numeric = ['pefr', 'best_pefr', 'height']
        for col in cols_to_numeric:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        return df
    except Exception as e:
        st.error(f"❌ Error loading {worksheet_name}: {e}")
        st.stop()

@st.cache_data(ttl=5) 
def load_data_staff(worksheet_name=None):
    """โหลดข้อมูลสำหรับ Staff (โหลดทั้ง 2 Sheet เพื่อคืนค่าเป็น Tuple)"""
    # หมายเหตุ: ฟังก์ชันนี้เดิมของคุณรับ worksheet_name แต่การใช้งานจริงใน app.py 
    # มักจะเรียก load_data_staff() เฉยๆ เพื่อเอาข้อมูลทั้ง 2 ตาราง
    # ผมเลยปรับให้มันยืดหยุ่นขึ้นครับ
    
    client = connect_to_gsheet()
    try:
        sh = client.open_by_key(SHEET_ID)
        
        # 1. Load Patients
        ws_pt = sh.worksheet(PATIENTS_SHEET_NAME)
        data_pt = ws_pt.get_all_records()
        df_pt = pd.DataFrame(data_pt)
        if 'hn' in df_pt.columns:
            df_pt['hn'] = df_pt['hn'].astype(str).str.strip().apply(lambda x: x.zfill(7))
            
        # 2. Load Visits
        ws_vs = sh.worksheet(VISITS_SHEET_NAME)
        data_vs = ws_vs.get_all_records()
        df_vs = pd.DataFrame(data_vs)
        if 'hn' in df_vs.columns:
            df_vs['hn'] = df_vs['hn'].astype(str).str.strip().apply(lambda x: x.zfill(7))
            
        return df_pt, df_vs

    except Exception as e:
        st.error(f"Error loading staff data: {e}")
        st.stop()

def save_visit_data(data_dict):
    """บันทึกข้อมูล Visit ลง Sheet"""
    try:
        client = connect_to_gsheet()
        sh = client.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(VISITS_SHEET_NAME)
        
        inhaler_result = data_dict.get("inhaler_eval", "-")

        # ตรวจสอบ HN ว่าต้องเป็น String แน่นอน
        hn_val = str(data_dict["hn"]).strip()

        row = [
            hn_val, 
            data_dict["date"], 
            data_dict["pefr"],
            data_dict["control_level"], 
            data_dict["controller"], 
            data_dict["reliever"],
            data_dict["adherence"], 
            data_dict["drp"], 
            data_dict["advice"],
            data_dict["technique_check"], 
            data_dict["next_appt"], 
            data_dict["note"], 
            data_dict["is_new_case"],
            inhaler_result
        ]
        
        # ✅ KEY FIX: ใช้ value_input_option='USER_ENTERED' ช่วยให้ Sheet ตีความ Data Type เองอย่างถูกต้อง
        # แต่ถ้าเราตั้ง Column ใน Sheet เป็น Plain Text แล้ว มันจะลงเป็น Text 0003633 ให้เลย
        worksheet.append_row(row, value_input_option='USER_ENTERED')
        
        # Clear Cache
        load_data_staff.clear()
        load_data_fast.clear()
        return True
        
    except Exception as e:
        st.error(f"Save Visit Error: {e}")
        return False

def save_patient_data(data_dict):
    """บันทึกข้อมูลผู้ป่วยใหม่"""
    try:
        client = connect_to_gsheet()
        sh = client.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(PATIENTS_SHEET_NAME)
        
        hn_val = str(data_dict['hn']).strip()
        
        row = [
            hn_val, 
            data_dict["prefix"], 
            data_dict["first_name"],
            data_dict["last_name"], 
            data_dict["dob"], 
            data_dict["best_pefr"], 
            data_dict["height"], 
            "Active"  
        ]
        
        # ✅ KEY FIX: ใช้ value_input_option='USER_ENTERED'
        worksheet.append_row(row, value_input_option='USER_ENTERED')
        
        load_data_staff.clear()
        load_data_fast.clear()
        return True

    except Exception as e:
        st.error(f"Save Patient Error: {e}")
        return False

def update_patient_status(hn, new_status):
    """อัปเดตสถานะผู้ป่วย (Active/Discharge/COPD)"""
    client = connect_to_gsheet()
    sh = client.open_by_key(SHEET_ID)
    worksheet = sh.worksheet(PATIENTS_SHEET_NAME)
    
    try:
        # ค้นหา HN (ต้องแปลงเป็น str)
        cell = worksheet.find(str(hn))
        if cell:
            # อัปเดตสถานะที่คอลัมน์ 8 (H) ของแถวนั้น
            worksheet.update_cell(cell.row, 8, new_status)
            
            load_data_staff.clear()
            load_data_fast.clear()
            return True
        else:
            return False
    except Exception as e:
        st.error(f"Update Status Error: {e}")
        return False
