import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid # ✅ ต้องมี import uuid สำหรับสร้าง Token

# --- CONFIGURATION ---
# ใส่ ID ของ Google Sheet คุณที่นี่
SHEET_ID = st.secrets.get("sheet_id", "1LF9Yi6CXHaiITVCqj9jj1agEdEE9S-37FwnaxNIlAaE") 

def connect_to_gsheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            return client
    except Exception:
        pass 

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name('service_account.json', scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error("❌ ไม่สามารถเชื่อมต่อ Google Sheets ได้ (ตรวจสอบ service_account.json หรือ Secrets)")
        st.stop()

@st.cache_data(ttl=60)
def load_data_fast(worksheet_name):
    try:
        client = connect_to_gsheet()
        sh = client.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(worksheet_name)
        data = worksheet.get_all_values()
        if not data: return pd.DataFrame()

        headers = data.pop(0)
        df = pd.DataFrame(data, columns=headers)

        if 'hn' in df.columns:
            df['hn'] = df['hn'].astype(str).str.split('.').str[0].str.strip().apply(lambda x: x.zfill(7))
            
        cols_to_numeric = ['pefr', 'best_pefr', 'height']
        for col in cols_to_numeric:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"❌ Error loading {worksheet_name}: {e}")
        st.stop()

@st.cache_data(ttl=5) 
def load_data_staff(worksheet_name):
    client = connect_to_gsheet()
    try:
        sh = client.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(worksheet_name)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        if 'hn' in df.columns:
            df['hn'] = df['hn'].astype(str).str.strip().apply(lambda x: x.zfill(7))
        return df
    except Exception as e:
        st.error(f"Error: {e}")
        st.stop()

def save_visit_data(data_dict):
    client = connect_to_gsheet()
    sh = client.open_by_key(SHEET_ID)
    worksheet = sh.worksheet("visits")
    
    inhaler_result = data_dict.get("inhaler_eval", "-")

    row = [
        str(data_dict["hn"]), 
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
    worksheet.append_row(row)
    load_data_staff.clear()
    load_data_fast.clear()

def save_patient_data(data_dict):
    client = connect_to_gsheet()
    sh = client.open_by_key(SHEET_ID)
    worksheet = sh.worksheet("patients")
    
    # สร้าง Token อัตโนมัติสำหรับคนไข้ใหม่
    new_token = str(uuid.uuid4())
    
    row = [
        str(data_dict['hn']), 
        data_dict["prefix"], 
        data_dict["first_name"],
        data_dict["last_name"], 
        data_dict["dob"], 
        data_dict["best_pefr"], 
        data_dict["height"], 
        "Active",
        new_token # บันทึก Token ลงคอลัมน์ I
    ]
    worksheet.append_row(row)
    load_data_staff.clear()
    load_data_fast.clear()

def update_patient_status(hn, new_status):
    client = connect_to_gsheet()
    sh = client.open_by_key(SHEET_ID)
    worksheet = sh.worksheet("patients")
    
    try:
        cell = worksheet.find(str(hn))
        if cell:
            # สมมติ Status อยู่คอลัมน์ 8 (H)
            worksheet.update_cell(cell.row, 8, new_status)
            load_data_staff.clear()
            load_data_fast.clear()
            return True
        else:
            return False
    except Exception as e:
        st.error(f"Update Status Error: {e}")
        return False

# ✅ ฟังก์ชันที่ขาดไป (ทำให้เกิด Error)
def update_patient_token(hn, new_token):
    client = connect_to_gsheet()
    sh = client.open_by_key(SHEET_ID)
    worksheet = sh.worksheet("patients")
    
    try:
        cell = worksheet.find(str(hn))
        if cell:
            # สมมติ Token อยู่คอลัมน์ 9 (I)
            # ถ้าใน Google Sheet คุณคอลัมน์ Token ไม่ใช่ I อาจต้องแก้เลข 9 เป็นเลขอื่น
            worksheet.update_cell(cell.row, 9, new_token)
            load_data_staff.clear()
            load_data_fast.clear()
            return True
        else:
            return False
    except Exception as e:
        st.error(f"Update Token Error: {e}")
        return False
