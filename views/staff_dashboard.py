import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime

def render_dashboard(visits_df):
    if visits_df.empty:
        st.warning("ยังไม่มีข้อมูลการตรวจเยี่ยม")
        return

    df = visits_df.copy()
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['month_year'] = df['date'].dt.strftime('%Y-%m') 

    today_str = datetime.now().strftime('%Y-%m-%d')
    today_df = df[df['date'].dt.strftime('%Y-%m-%d') == today_str]
    count_today_total = len(today_df)
    
    if 'is_new_case' in df.columns:
        today_new_cases = today_df[today_df['is_new_case'].astype(str).str.upper() == 'TRUE']
        count_today_new = len(today_new_cases)
    else:
        count_today_new = 0
        
    total_patients = len(df['hn'].unique())

    st.subheader(f"📅 สรุปยอดประจำวัน ({datetime.now().strftime('%d/%m/%Y')})")
    
    m1, m2, m3 = st.columns(3)
    m1.metric("ผู้รับบริการวันนี้", f"{count_today_total} คน", "Visits", delta_color="off")
    m2.metric("ผู้ป่วยใหม่วันนี้", f"{count_today_new} คน", f"+{count_today_new}" if count_today_new > 0 else "0")
    m3.metric("ทะเบียนผู้ป่วยสะสม", f"{total_patients} คน")
    st.divider()

    st.subheader("1. ภาพรวมการควบคุมโรค")
    latest_visits = df.sort_values('date').groupby('hn').tail(1)
    control_counts = latest_visits['control_level'].value_counts().reset_index()
    control_counts.columns = ['status', 'count']
    domain = ['Controlled', 'Partly Controlled', 'Uncontrolled']
    range_ = ['#66BB6A', '#FFCA28', '#EF5350'] 

    pie = alt.Chart(control_counts).mark_arc(innerRadius=50).encode(
        theta=alt.Theta(field="count", type="quantitative"),
        color=alt.Color(field="status", type="nominal", scale=alt.Scale(domain=domain, range=range_)),
        tooltip=['status', 'count']
    ).properties(title="สัดส่วนผู้ป่วยแยกตามระดับการควบคุม")
    st.altair_chart(pie, use_container_width=True)

    st.subheader("2. ปริมาณงานรายเดือน")
    monthly_visits = df.groupby('month_year').size().reset_index(name='total_visits')
    line_chart = alt.Chart(monthly_visits).mark_line(point=True).encode(
        x=alt.X('month_year', title='เดือน-ปี'),
        y=alt.Y('total_visits', title='จำนวน'),
        tooltip=['month_year', 'total_visits']
    ).properties(height=300)
    st.altair_chart(line_chart, use_container_width=True)