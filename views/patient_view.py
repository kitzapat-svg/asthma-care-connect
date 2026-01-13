import streamlit as st
import pandas as pd
from datetime import datetime
from utils.gsheet_handler import load_data_fast, PATIENTS_SHEET_NAME, VISITS_SHEET_NAME
from utils.calculations import (
    calculate_predicted_pefr, get_percent_predicted, get_action_plan_zone, 
    check_technique_status, plot_pefr_chart, mask_text
)

def show_patient_view(target_hn):
    patients_db_fast = load_data_fast(PATIENTS_SHEET_NAME)
    visits_db_fast = load_data_fast(VISITS_SHEET_NAME)

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
            pt_visits['date'] = pd.to_datetime(pt_visits['date'], errors='coerce')
            pt_visits_sorted = pt_visits.sort_values(by="date")
            last_visit = pt_visits_sorted.iloc[-1]
            
            zone_name, zone_color, advice = get_action_plan_zone(last_visit['pefr'], ref_pefr)
            pct_std = get_percent_predicted(last_visit['pefr'], predicted_pefr)

            st.info(f"📋 **สถานะล่าสุด ({last_visit['date'].strftime('%d/%m/%Y')})**")
            m1, m2, m3 = st.columns(3)
            pefr_show = last_visit['pefr'] if last_visit['pefr'] > 0 else "N/A"
            m1.metric("PEFR", f"{pefr_show}")
            m2.metric("% มาตรฐาน", f"{pct_std}%", help=f"เทียบค่ามาตรฐาน: {int(predicted_pefr)}")
            m3.markdown(f"โซน: :{zone_color}[**{zone_name}**]")
            st.write(f"**💊 Controller:** {last_visit.get('controller', '-')}")
              
            if 'note' in last_visit and str(last_visit['note']).strip() != "" and str(last_visit['note']).lower() != "nan":
                st.info(f"ℹ️ **หมายเหตุ:** {last_visit['note']}")

            st.subheader("📈 กราฟแนวโน้ม")
            chart = plot_pefr_chart(pt_visits_sorted, ref_pefr)
            st.altair_chart(chart, use_container_width=True)
              
            with st.expander("ดูประวัติ"):
                show_df = pt_visits_sorted.sort_values(by="date", ascending=False).copy()
                show_df['date'] = show_df['date'].dt.strftime('%d/%m/%Y')
                st.dataframe(show_df, hide_index=True)
        else:
            st.warning("ไม่มีประวัติ")
    else:
        st.error(f"ไม่พบข้อมูล HN: {target_hn}")