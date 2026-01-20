import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURATION ---
SHEET_ID = "1LF9Yi6CXHaiITVCqj9jj1agEdEE9S-37FwnaxNIlAaE"
PATIENTS_SHEET_NAME = "patients"
VISITS_SHEET_NAME = "visits"

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

# ✅ ฟังก์ชันนี้คือจุดที่มักจะ Error (ผมเช็ค Comma ให้ครบแล้ว)
def save_visit_data(data_dict):
    client = connect_to_gsheet()
    sh = client.open_by_key(SHEET_ID)
    worksheet = sh.worksheet("visits")
    
    # ดึงค่าประเมิน (ถ้าไม่มีให้เป็น -)
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
        inhaler_result  # ✅ ต้องไม่มี Comma เกินหรือขาด
    ]
    worksheet.append_row(row)
    load_data_staff.clear()
    load_data_fast.clear()

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
    client = connect_to_gsheet()
    sh = client.open_by_key(SHEET_ID)
    worksheet = sh.worksheet("patients")
    
    try:
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

def save_multiple_visits(rows_list):
    """
    บันทึกข้อมูล Visit หลายรายการพร้อมกัน (Batch Insert)
    rows_list: list of dict
    """
    client = connect_to_gsheet()
    sh = client.open_by_key(SHEET_ID)
    worksheet = sh.worksheet("visits")
    
    data_to_append = []
    for data in rows_list:
        row = [
            str(data["hn"]), 
            data["date"], 
            data["pefr"],
            data["control_level"], 
            data["controller"], 
            data["reliever"],
            data["adherence"], 
            data["drp"], 
            data["advice"],
            data["technique_check"], 
            data["next_appt"], 
            data["note"], 
            data["is_new_case"],
            data.get("inhaler_eval", "-")
        ]
        data_to_append.append(row)
    
    if data_to_append:
        worksheet.append_rows(data_to_append)
        load_data_staff.clear()
        load_data_fast.clear()

def update_appointments_batch(updates_list):
    """
    อัปเดตวันนัดหมาย (Next Appt) ทีละหลายรายการ
    updates_list: list of dict {'row': sheet_row_int, 'value': 'yyyy-mm-dd'}
    """
    if not updates_list:
        return

    client = connect_to_gsheet()
    sh = client.open_by_key(SHEET_ID)
    worksheet = sh.worksheet("visits")
    
    # สร้าง list ของ Cell object เพื่อ update ทีเดียว (ประหยัด Quota)
    cells_to_update = []
    for item in updates_list:
        # Column 11 คือ next_appt (K)
        # gspread ใช้ Row, Col (เริ่มที่ 1)
        cells_to_update.append(
            gspread.Cell(item['row'], 11, item['value'])
        )
    
    if cells_to_update:
        worksheet.update_cells(cells_to_update)
        load_data_staff.clear()
        load_data_fast.clear()