import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime

def render_dashboard(visits_df):
    if visits_df.empty:
        st.warning("ยังไม่มีข้อมูลการตรวจเยี่ยม")
        return

    # เตรียมข้อมูลหลัก
    df = visits_df.copy()
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['month_year'] = df['date'].dt.strftime('%Y-%m') 

    # --- ส่วนที่ 1: สรุปยอดประจำวัน (Card Metrics) ---
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

    # --- ส่วนที่ 2: ปริมาณงานรายเดือน (Workload) - ปรับปรุงใหม่ ใหญ่ขึ้น ---
    st.subheader("📈 1. ปริมาณงานรายเดือน (Monthly Workload)")
    
    # คำนวณยอด Visit รวม
    monthly_visits = df.groupby('month_year').size().reset_index(name='Total Visits')
    
    # คำนวณยอด New Case
    if 'is_new_case' in df.columns:
        new_cases = df[df['is_new_case'].astype(str).str.upper() == 'TRUE']
        monthly_new = new_cases.groupby('month_year').size().reset_index(name='New Cases')
    else:
        monthly_new = pd.DataFrame(columns=['month_year', 'New Cases'])

    # รวมตารางเข้าด้วยกัน
    trend_df = pd.merge(monthly_visits, monthly_new, on='month_year', how='left').fillna(0)
    
    # แปลงเป็น Long Format เพื่อพล็อตกราฟหลายเส้น
    trend_long = trend_df.melt('month_year', var_name='Type', value_name='Count')
    
    # สร้างกราฟ Workload ขนาดใหญ่
    workload_chart = alt.Chart(trend_long).mark_line(point=True, strokeWidth=3).encode(
        x=alt.X('month_year', title='เดือน-ปี'),
        y=alt.Y('Count', title='จำนวน (ราย)'),
        color=alt.Color('Type', legend=alt.Legend(title="ประเภทผู้ป่วย"), 
                        scale=alt.Scale(domain=['Total Visits', 'New Cases'], range=['#1E88E5', '#D81B60'])),
        tooltip=['month_year', 'Type', 'Count']
    ).properties(
        height=400, # ✅ เพิ่มความสูงกราฟ
        title="เปรียบเทียบจำนวนผู้รับบริการทั้งหมด vs ผู้ป่วยรายใหม่"
    ).interactive()
    
    st.altair_chart(workload_chart, use_container_width=True)
    st.divider()

    # --- ส่วนที่ 3: KPI อื่นๆ (จัด Layout แบบ 2 คอลัมน์) ---
    c_left, c_right = st.columns([1, 1.5])
    
    with c_left:
        st.subheader("2. การควบคุมโรค (Status)")
        latest_visits = df.sort_values('date').groupby('hn').tail(1)
        control_counts = latest_visits['control_level'].value_counts().reset_index()
        control_counts.columns = ['status', 'count']
        domain = ['Controlled', 'Partly Controlled', 'Uncontrolled']
        range_ = ['#66BB6A', '#FFCA28', '#EF5350'] 

        pie = alt.Chart(control_counts).mark_arc(innerRadius=60).encode(
            theta=alt.Theta(field="count", type="quantitative"),
            color=alt.Color(field="status", type="nominal", scale=alt.Scale(domain=domain, range=range_), legend=alt.Legend(orient='bottom')),
            tooltip=['status', 'count']
        ).properties(height=300)
        st.altair_chart(pie, use_container_width=True)

    with c_right:
        st.subheader("3. สอนเทคนิคพ่นยา (Fiscal Year)")
        
        # Logic คำนวณปีงบประมาณ
        df_tech = df[df['technique_check'].astype(str).str.contains('ทำ', na=False)].copy()

        if not df_tech.empty:
            df_tech['fiscal_year_ad'] = df_tech['date'].dt.year + (df_tech['date'].dt.month >= 10).astype(int)
            df_tech['fiscal_year_be'] = df_tech['fiscal_year_ad'] + 543

            fiscal_stats = df_tech.groupby('fiscal_year_be').agg(
                total_sessions=('hn', 'count'),
                total_persons=('hn', 'nunique')
            ).reset_index()
            
            fiscal_stats.columns = ['ปีงบ (พ.ศ.)', 'ครั้ง', 'คน']
            fiscal_stats = fiscal_stats.sort_values('ปีงบ (พ.ศ.)', ascending=False)

            # แสดงเป็นกราฟแท่งแนวนอนผสมตาราง
            chart_data = fiscal_stats.melt('ปีงบ (พ.ศ.)', var_name='Unit', value_name='Value')
            
            bar_fiscal = alt.Chart(chart_data).mark_bar().encode(
                y=alt.Y('ปีงบ (พ.ศ.):O', title=None),
                x=alt.X('Value', title='จำนวน'),
                color=alt.Color('Unit', legend=alt.Legend(title="หน่วยนับ"), scale=alt.Scale(range=['#FFB74D', '#4DB6AC'])),
                tooltip=['ปีงบ (พ.ศ.)', 'Unit', 'Value']
            ).properties(height=200)
            
            st.altair_chart(bar_fiscal, use_container_width=True)
            
            # ตารางย่อ
            st.dataframe(fiscal_stats, hide_index=True, use_container_width=True)
        else:
            st.info("ยังไม่มีข้อมูลการสอนพ่นยา")