import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils.gsheet_handler import save_multiple_visits

def render_import_appointment(patients_db, visits_db):
    st.title("📥 นำเข้าข้อมูลนัดหมาย (จาก HOSxP)")
    
    st.info("💡 อัปโหลดไฟล์ Excel/CSV ที่ Export จาก HOSxP เพื่อบันทึกวันนัดหมายลงระบบอัตโนมัติ")
    
    # 1. Upload File
    uploaded_file = st.file_uploader("เลือกไฟล์ (.csv หรือ .xls)", type=['csv', 'xls', 'xlsx'])
    
    if uploaded_file is not None:
        df = None
        error_msg = ""
        
        # --- 🛠️ ส่วนอ่านไฟล์แบบ Robust (ลองหลายๆ แบบจนกว่าจะอ่านออก) ---
        # รายชื่อ Encoding ที่ HOSxP ชอบใช้
        encodings_to_try = ['utf-8', 'cp874', 'tis-620', 'utf-16', 'utf-16le', 'utf-16be']
        
        try:
            # กรณีไฟล์ .csv (หรือ xls ปลอมที่เป็น csv)
            if uploaded_file.name.lower().endswith(('.csv', '.xls')): 
                for encoding in encodings_to_try:
                    try:
                        uploaded_file.seek(0)
                        # ใช้ engine='python' เพื่อความยืดหยุ่น และ sep=None เพื่อเดาตัวคั่น (, หรือ tab)
                        df = pd.read_csv(uploaded_file, sep=None, engine='python', encoding=encoding)
                        st.success(f"✅ อ่านไฟล์สำเร็จด้วยรหัสภาษา: {encoding}")
                        break # ถ้าอ่านได้แล้ว ให้หยุดลอง
                    except Exception:
                        continue # ถ้าอ่านไม่ได้ ให้ลองรหัสถัดไป

            # กรณีไฟล์ Excel จริงๆ (.xlsx)
            elif uploaded_file.name.lower().endswith('.xlsx'):
                df = pd.read_excel(uploaded_file)
                
        except Exception as e:
            error_msg = str(e)
            
        # ------------------------------------------------------------------

        if df is None:
            st.error(f"❌ ไม่สามารถอ่านไฟล์ได้ (Format ไม่รองรับ หรือ Encoding ผิดพลาด)")
            if error_msg: st.caption(f"Error detail: {error_msg}")
            return

        # 2. ตรวจสอบคอลัมน์ที่จำเป็น (Clean ชื่อคอลัมน์ก่อนเช็ค)
        df.columns = df.columns.str.strip() # ลบช่องว่างหัวท้ายชื่อคอลัมน์
        
        required_cols = ['HN', 'วันที่รับบริการ', 'วันนัดถัดไป']
        # เช็คว่ามีคอลัมน์ครบไหม (Allow case-insensitive check)
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            st.error(f"❌ ไฟล์ไม่ถูกต้อง! ขาดคอลัมน์: {', '.join(missing_cols)}")
            st.warning("⚠️ โปรดตรวจสอบหัวตารางในไฟล์ Excel ต้องมีคำว่า: HN, วันที่รับบริการ, วันนัดถัดไป")
            return

        # 3. แปลงข้อมูล
        # ฟังก์ชันแปลงวันที่ Excel Serial (เช่น 45930) หรือ String
        def convert_date(val):
            try:
                if pd.isna(val) or val == '' or str(val).strip() == '-': return None
                
                # กรณีเป็นตัวเลข Serial ของ Excel (เช่น 45958.0)
                if isinstance(val, (int, float)):
                    d = pd.Timestamp('1899-12-30') + pd.Timedelta(days=float(val))
                    return d.strftime('%Y-%m-%d')
                
                # กรณีเป็น Text (เช่น 19/01/2026)
                val_str = str(val).strip()
                for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']:
                    try:
                        return datetime.strptime(val_str, fmt).strftime('%Y-%m-%d')
                    except:
                        pass
                return None
            except:
                return None

        # แปลง HN ให้เป็น 7 หลัก
        # .astype(str) เพื่อกัน error กรณี HN เป็นตัวเลขเพียวๆ
        df['HN_clean'] = df['HN'].astype(str).str.split('.').str[0].str.strip().str.zfill(7)
        
        # แปลงวันที่
        df['visit_date'] = df['วันที่รับบริการ'].apply(convert_date)
        df['next_appt_date'] = df['วันนัดถัดไป'].apply(convert_date)

        # 4. กรองเฉพาะคนที่มีในฐานข้อมูล (Merge)
        existing_hns = patients_db['hn'].unique()
        
        matched_df = df[df['HN_clean'].isin(existing_hns)].copy()
        matched_df = pd.merge(matched_df, patients_db[['hn', 'first_name', 'last_name']], left_on='HN_clean', right_on='hn', how='left')

        if matched_df.empty:
            st.warning("⚠️ ไม่พบ HN ในไฟล์ที่ตรงกับฐานข้อมูลคนไข้ในระบบเลย")
            st.write("ตัวอย่าง HN ในไฟล์:", df['HN_clean'].head().tolist())
            st.write("ตัวอย่าง HN ในระบบ:", existing_hns[:5])
            return

        # แสดงตัวอย่างข้อมูล
        st.write(f"✅ พบข้อมูลที่ตรงกันและพร้อมนำเข้า **{len(matched_df)}** รายการ:")
        
        preview_df = matched_df[['hn', 'first_name', 'last_name', 'visit_date', 'next_appt_date']].copy()
        preview_df.columns = ['HN', 'ชื่อ', 'นามสกุล', 'วันที่รับบริการ (Visit)', 'วันนัดถัดไป']
        
        # ไฮไลท์แถวที่วันนัดว่างเปล่า (เผื่อ User อยากรู้)
        st.dataframe(preview_df, hide_index=True, use_container_width=True)

        # ปุ่มกดยืนยัน
        if st.button("🚀 ยืนยันการนำเข้าข้อมูล", type="primary"):
            new_visits = []
            update_visits = [] # 📝 เก็บรายการที่จะอัปเดตวันนัด
            count_new = 0
            count_update = 0
            
            # 1. เตรียม Lookup Dictionary จากข้อมูลเดิมในระบบ (เพื่อความเร็ว)
            visit_lookup = {}
            if not visits_db.empty:
                # สร้างคอลัมน์วันที่แบบมาตรฐานชั่วคราวเพื่อเทียบ
                temp_db = visits_db.copy()
                # แปลงวันที่ใน DB ให้เป็น YYYY-MM-DD (รองรับทั้ง format เก่า/ใหม่)
                temp_db['date_norm'] = pd.to_datetime(temp_db['date'], errors='coerce').dt.strftime('%Y-%m-%d')
                
                # สร้าง Dict: Key=(HN, Date) -> Value=Index ของ DataFrame
                for idx, row in temp_db.iterrows():
                    key = (str(row['hn']).strip(), str(row['date_norm']))
                    visit_lookup[key] = idx

            with st.status("กำลังประมวลผล...", expanded=True) as status:
                for _, row in matched_df.iterrows():
                    if not row['visit_date']: continue # ข้ามถ้าไม่มีวันที่
                    
                    # Key ที่จะใช้เช็ค
                    hn_key = str(row['hn']).strip()
                    date_key = str(row['visit_date']) # format YYYY-MM-DD จาก function convert_date
                    lookup_key = (hn_key, date_key)

                    if lookup_key in visit_lookup:
                        # 🟡 เจอซ้ำ -> เก็บข้อมูลเพื่อ Update Row เดิม
                        if row['next_appt_date']: # ถ้าในไฟล์มีวันนัด
                            df_idx = visit_lookup[lookup_key]
                            sheet_row = df_idx + 2 # คำนวณบรรทัดใน Sheet (Header=1 + 0-based index = +2)
                            
                            update_visits.append({
                                'row': sheet_row,
                                'value': row['next_appt_date']
                            })
                            count_update += 1
                    else:
                        # 🟢 ไม่ซ้ำ -> New Visit (เพิ่มแถวใหม่)
                        new_visits.append({
                            "hn": row['hn'],
                            "date": row['visit_date'],
                            "pefr": 0, 
                            "control_level": "-",
                            "controller": "-",
                            "reliever": "-",
                            "adherence": 0,
                            "drp": "-",
                            "advice": "Imported from HOSxP",
                            "technique_check": "-",
                            "next_appt": row['next_appt_date'] if row['next_appt_date'] else "-",
                            "note": "นำเข้าจาก HOSxP",
                            "is_new_case": "FALSE",
                            "inhaler_eval": "-"
                        })
                        count_new += 1
                
                # เริ่มบันทึกข้อมูล
                if new_visits:
                    save_multiple_visits(new_visits)
                    st.write(f"✅ เพิ่มรายการใหม่: {count_new} รายการ")
                
                if update_visits:
                    # ต้อง import ฟังก์ชันใหม่ก่อนใช้
                    from utils.gsheet_handler import update_appointments_batch
                    update_appointments_batch(update_visits)
                    st.write(f"🔄 อัปเดตวันนัดในรายการเดิม: {count_update} รายการ")

                status.update(label="✅ ดำเนินการเสร็จสิ้น!", state="complete", expanded=False)
                
                if count_new == 0 and count_update == 0:
                    st.warning("⚠️ ไม่มีการเปลี่ยนแปลงข้อมูล (ข้อมูลตรงกับในระบบอยู่แล้ว)")
                else:
                    st.success(f"สรุป: เพิ่มใหม่ {count_new} | อัปเดตเดิม {count_update}")
                    st.balloons()