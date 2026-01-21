import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime  # ✅ 1. เพิ่มบรรทัดนี้

# --- CONFIGURATION ---
SHEET_ID = "1LF9Yi6CXHaiITVCqj9jj1agEdEE9S-37FwnaxNIlAaE"
PATIENTS_SHEET_NAME = "patients"
VISITS_SHEET_NAME = "visits"
LOGS_SHEET_NAME = "logs"  # ✅ 2. เพิ่มชื่อ Sheet Logs

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

# ✅ 3. เพิ่มฟังก์ชัน log_action นี้ลงไป
def log_action(user, action, details="-"):
    """
    บันทึก Log การใช้งานลง Sheet 'logs'
    """
    try:
        client = connect_to_gsheet()
        sh = client.open_by_key(SHEET_ID)
        
        # พยายามเปิด Sheet logs ถ้าไม่มีให้สร้างใหม่ (Auto-create)
        try:
            worksheet = sh.worksheet(LOGS_SHEET_NAME)
        except gspread.WorksheetNotFound:
            worksheet = sh.add_worksheet(title=LOGS_SHEET_NAME, rows=1000, cols=4)
            # สร้าง Header
            worksheet.append_row(["Timestamp", "User", "Action", "Details"])

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # บันทึกข้อมูล
        worksheet.append_row([timestamp, user, action, str(details)])
        
    except Exception as e:
        print(f"⚠️ Logging Failed: {e}")

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
            "Active",
            data_dict.get("public_token", "")
        ]
        
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
            worksheet.update_cell(cell.row, 8, new_status)
            load_data_staff.clear()
            load_data_fast.clear()
            return True
        else:
            return False
    except Exception as e:
        st.error(f"Update Status Error: {e}")
        return False

def update_patient_token(hn, token):
    client = connect_to_gsheet()
    sh = client.open_by_key(SHEET_ID)
    worksheet = sh.worksheet("patients")
    
    try:
        header_cell = worksheet.cell(1, 9)
        if header_cell.value != "public_token":
            worksheet.update_cell(1, 9, "public_token")

        cell = worksheet.find(str(hn))
        if cell:
            worksheet.update_cell(cell.row, 9, token)
            load_data_staff.clear()
            load_data_fast.clear()
            return True
        else:
            return False
    except Exception as e:
        st.error(f"Update Token Error: {e}")
        return False

def save_multiple_visits(rows_list):
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
    if not updates_list:
        return

    client = connect_to_gsheet()
    sh = client.open_by_key(SHEET_ID)
    worksheet = sh.worksheet("visits")
    
    cells_to_update = []
    for item in updates_list:
        cells_to_update.append(
            gspread.Cell(item['row'], 11, item['value'])
        )
    
    if cells_to_update:
        worksheet.update_cells(cells_to_update)
        load_data_staff.clear()
        load_data_fast.clear()
