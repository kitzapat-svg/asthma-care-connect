import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, timedelta

def render_dashboard(visits_db, patients_db):
    st.title("📊 Dashboard ภาพรวมคลินิก")

    # --- 1. เตรียมข้อมูล (Data Preparation) ---
    if visits_db.empty:
        st.info("ยังไม่มีข้อมูลการตรวจ")
        return

    # Merge ข้อมูล Visit กับ ชื่อคนไข้ เพื่อให้แสดงผลสวยงาม
    df = pd.merge(
        visits_db, 
        patients_db[['hn', 'prefix', 'first_name', 'last_name']], 
        on='hn', 
        how='left'
    )
    
    # แปลงวันที่
    df['date'] = pd.to_datetime(df['date'])
    df['full_name'] = df['prefix'] + df['first_name'] + " " + df['last_name']
    
    # กรองข้อมูลย้อนหลัง 1 ปี
    one_year_ago = datetime.now() - timedelta(days=365)
    df_1y = df[df['date'] >= one_year_ago].copy()

    # --- 2. KPI Cards (สรุปภาพรวม) ---
    st.markdown("### 📈 สรุปภาพรวม (1 ปีย้อนหลัง)")
    c1, c2, c3, c4 = st.columns(4)
    
    total_visits = len(df_1y)
    unique_patients = df_1y['hn'].nunique()
    new_cases = len(df_1y[df_1y['is_new_case'] == 'TRUE'])
    
    # คำนวณ % Control
    controlled_count = len(df_1y[df_1y['control_level'] == 'Controlled'])
    control_rate = int((controlled_count / total_visits * 100) if total_visits > 0 else 0)

    c1.metric("จำนวน Visit ทั้งหมด", f"{total_visits} ครั้ง")
    c2.metric("คนไข้ (ไม่ซ้ำ)", f"{unique_patients} คน")
    c3.metric("ผู้ป่วยรายใหม่ (New)", f"{new_cases} คน")
    c4.metric("Control Rate", f"{control_rate}%")

    st.divider()

    # --- 3. Weekly Workload (ปริมาณงานรายสัปดาห์) ---
    st.markdown("### 🗓️ ปริมาณงานรายสัปดาห์ (Weekly Workload)")
    
    # เตรียมข้อมูลรายสัปดาห์
    df_weekly = df_1y.copy()
    df_weekly['week_start'] = df_weekly['date'].dt.to_period('W').apply(lambda r: r.start_time)
    
    # Group ข้อมูล
    weekly_stats = df_weekly.groupby('week_start').agg(
        total_visits=('hn', 'count'),
        new_patients=('is_new_case', lambda x: (x == 'TRUE').sum())
    ).reset_index()
    
    # แปลงข้อมูลเป็น Long Format เพื่อพล็อตกราฟซ้อน (Layered/Grouped)
    weekly_melted = weekly_stats.melt('week_start', var_name='type', value_name='count')
    # เปลี่ยนชื่อให้สวยงาม
    weekly_melted['type'] = weekly_melted['type'].replace({
        'total_visits': 'คนไข้ทั้งหมด', 
        'new_patients': 'คนไข้ใหม่'
    })

    # วาดกราฟด้วย Altair
    chart_weekly = alt.Chart(weekly_melted).mark_bar().encode(
        x=alt.X('week_start', title='สัปดาห์', axis=alt.Axis(format='%d/%m')),
        y=alt.Y('count', title='จำนวนคนไข้'),
        color=alt.Color('type', title='ประเภท', scale=alt.Scale(domain=['คนไข้ทั้งหมด', 'คนไข้ใหม่'], range=['#4285F4', '#EA4335'])),
        tooltip=[
            alt.Tooltip('week_start', title='สัปดาห์เริ่ม', format='%d/%m/%Y'),
            alt.Tooltip('type', title='ประเภท'),
            alt.Tooltip('count', title='จำนวน')
        ]
    ).properties(height=300).interactive()

    st.altair_chart(chart_weekly, use_container_width=True)

    st.divider()

    # --- 4. Monthly Workload (แบบย่อ-ขยาย) ---
    st.markdown("### 📅 ปริมาณงานรายเดือน (Monthly Detail)")

    # เตรียมข้อมูลรายเดือน
    df_1y['month_year'] = df_1y['date'].dt.to_period('M')
    unique_months = df_1y['month_year'].unique()
    unique_months = sorted(unique_months, reverse=True) # เรียงจากเดือนล่าสุดลงไป

    for m in unique_months:
        # กรองข้อมูลเฉพาะเดือนนั้น
        month_data = df_1y[df_1y['month_year'] == m].copy()
        
        # คำนวณสถิติของเดือนนั้น
        m_total = len(month_data)
        m_new = len(month_data[month_data['is_new_case'] == 'TRUE'])
        m_uncontrolled = len(month_data[month_data['control_level'] == 'Uncontrolled'])
        
        # ชื่อเดือนภาษาไทย (แบบง่าย)
        month_label = m.strftime('%B %Y') 
        
        # สร้าง Expander
        with st.expander(f"📂 **{month_label}** (ทั้งหมด: {m_total} | ใหม่: {m_new} | Uncontrolled: {m_uncontrolled})"):
            
            # จัดเตรียมตารางแสดงผล
            display_table = month_data[['date', 'hn', 'full_name', 'pefr', 'control_level', 'is_new_case']].copy()
            display_table['date'] = display_table['date'].dt.strftime('%d/%m/%Y')
            
            # ไฮไลท์คนไข้ Uncontrolled
            def highlight_uncontrolled(s):
                return ['background-color: #ffcccc' if v == 'Uncontrolled' else '' for v in s]

            st.dataframe(
                display_table.style.apply(highlight_uncontrolled, subset=['control_level']),
                column_config={
                    "date": "วันที่",
                    "hn": "HN",
                    "full_name": "ชื่อ-สกุล",
                    "pefr": "PEFR",
                    "control_level": "การควบคุม",
                    "is_new_case": "New Case"
                },
                use_container_width=True,
                hide_index=True
            )

    # --- 5. สรุป Control Level (Pie Chart) ---
    st.divider()
    c_pie1, c_pie2 = st.columns(2)
    
    with c_pie1:
        st.subheader("ระดับการควบคุมโรค (Control Level)")
        control_counts = df_1y['control_level'].value_counts().reset_index()
        control_counts.columns = ['level', 'count']
        
        pie_chart = alt.Chart(control_counts).mark_arc(innerRadius=50).encode(
            theta=alt.Theta(field="count", type="quantitative"),
            color=alt.Color(field="level", type="nominal", 
                            scale=alt.Scale(domain=['Controlled', 'Partly Controlled', 'Uncontrolled'],
                                            range=['#34A853', '#FBBC04', '#EA4335'])),
            tooltip=['level', 'count']
        )
        st.altair_chart(pie_chart, use_container_width=True)

    with c_pie2:
        st.subheader("สัดส่วนคนไข้ใหม่ (New vs Old)")
        case_counts = df_1y['is_new_case'].value_counts().reset_index()
        case_counts.columns = ['type', 'count']
        # เปลี่ยนชื่อให้สวย
        case_counts['type'] = case_counts['type'].map({'TRUE': 'New Case', 'FALSE': 'Old Case'})
        
        pie_chart2 = alt.Chart(case_counts).mark_arc(innerRadius=50).encode(
            theta=alt.Theta(field="count", type="quantitative"),
            color=alt.Color(field="type", type="nominal"),
            tooltip=['type', 'count']
        )
        st.altair_chart(pie_chart2, use_container_width=True)
