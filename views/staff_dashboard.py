import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime

# ✅ แก้บรรทัดนี้: รับ patients_df เพิ่มเข้ามา
def render_dashboard(visits_df, patients_df):
    if visits_df.empty:
        st.warning("ยังไม่มีข้อมูลการตรวจเยี่ยม")
        return

    # เตรียมข้อมูลหลัก
    df = visits_df.copy()
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['month_year'] = df['date'].dt.strftime('%Y-%m') 

    # --- ส่วนที่ 1: สรุปยอดประจำวัน ---
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

    # --- ส่วนที่ 2: ปริมาณงานรายเดือน ---
    st.subheader("📈 1. ปริมาณงานรายเดือน (Monthly Workload)")
    monthly_visits = df.groupby('month_year').size().reset_index(name='Total Visits')
    
    if 'is_new_case' in df.columns:
        new_cases = df[df['is_new_case'].astype(str).str.upper() == 'TRUE']
        monthly_new = new_cases.groupby('month_year').size().reset_index(name='New Cases')
    else:
        monthly_new = pd.DataFrame(columns=['month_year', 'New Cases'])

    trend_df = pd.merge(monthly_visits, monthly_new, on='month_year', how='left').fillna(0)
    trend_long = trend_df.melt('month_year', var_name='Type', value_name='Count')
    
    workload_chart = alt.Chart(trend_long).mark_line(point=True, strokeWidth=3).encode(
        x=alt.X('month_year', title='เดือน-ปี'),
        y=alt.Y('Count', title='จำนวน (ราย)'),
        color=alt.Color('Type', legend=alt.Legend(title="ประเภทผู้ป่วย"), 
                        scale=alt.Scale(domain=['Total Visits', 'New Cases'], range=['#1E88E5', '#D81B60'])),
        tooltip=['month_year', 'Type', 'Count']
    ).properties(height=350).interactive()
    st.altair_chart(workload_chart, use_container_width=True)
    st.divider()

    # --- ส่วนที่ 3: KPI ย่อย ---
    c_left, c_right = st.columns([1, 1.2])
    
    with c_left:
        st.subheader("2. การควบคุมโรค (Status)")
        latest_visits = df.sort_values('date').groupby('hn').tail(1)
        control_counts = latest_visits['control_level'].value_counts().reset_index()
        control_counts.columns = ['status', 'count']
        domain = ['Controlled', 'Partly Controlled', 'Uncontrolled']
        range_ = ['#66BB6A', '#FFCA28', '#EF5350'] 

        pie = alt.Chart(control_counts).mark_arc(innerRadius=60).encode(
            theta=alt.Theta(field="count", type="quantitative"),
            color=alt.Color(field="status", type="nominal", scale=alt.Scale(domain=domain, range=range_), 
                            legend=alt.Legend(orient='bottom', columns=1, title=None)),
            tooltip=['status', 'count']
        ).properties(height=300)
        st.altair_chart(pie, use_container_width=True)

    with c_right:
        st.subheader("3. สอนเทคนิคพ่นยา (Fiscal Year)")
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
            chart_data = fiscal_stats.melt('ปีงบ (พ.ศ.)', var_name='Unit', value_name='Value')
            
            bar_fiscal = alt.Chart(chart_data).mark_bar().encode(
                y=alt.Y('ปีงบ (พ.ศ.):O', title="ปีงบประมาณ (พ.ศ.)"),
                x=alt.X('Value', title='จำนวน'),
                color=alt.Color('Unit', legend=alt.Legend(title="หน่วยนับ"), scale=alt.Scale(range=['#FFB74D', '#26A69A'])),
                tooltip=['ปีงบ (พ.ศ.)', 'Unit', 'Value']
            ).properties(height=200)
            st.altair_chart(bar_fiscal, use_container_width=True)
            st.dataframe(fiscal_stats, hide_index=True, use_container_width=True)
        else:
            st.info("ยังไม่มีข้อมูลการสอนพ่นยา")

    # --- ส่วนที่ 4: สถิติ DRP ---
    st.divider()
    st.subheader("💊 4. สถิติปัญหาจากการใช้ยา (DRP Summary)")
    df_drp = df.copy()
    df_drp['drp_str'] = df_drp['drp'].astype(str).str.strip()
    df_drp = df_drp[(df_drp['drp_str'] != '') & (df_drp['drp_str'] != '-') & (df_drp['drp_str'].str.lower() != 'nan')]

    if not df_drp.empty:
        df_drp['fiscal_year_ad'] = df_drp['date'].dt.year + (df_drp['date'].dt.month >= 10).astype(int)
        df_drp['fiscal_year_be'] = df_drp['fiscal_year_ad'] + 543
        drp_stats = df_drp.groupby('fiscal_year_be').size().reset_index(name='จำนวนเรื่อง (DRPs)')
        drp_stats = drp_stats.sort_values('fiscal_year_be', ascending=False)
        
        c_drp_table, c_drp_chart = st.columns([1, 2])
        with c_drp_table:
            st.dataframe(drp_stats, hide_index=True, use_container_width=True)
        with c_drp_chart:
            drp_chart = alt.Chart(drp_stats).mark_bar(color='#EF5350').encode(
                x=alt.X('fiscal_year_be:O', title='ปีงบประมาณ'),
                y=alt.Y('จำนวนเรื่อง (DRPs)', title='จำนวนเรื่อง'),
                tooltip=['fiscal_year_be', 'จำนวนเรื่อง (DRPs)']
            ).properties(height=200)
            st.altair_chart(drp_chart, use_container_width=True)
    else:
        st.success("ยังไม่พบรายงานปัญหาการใช้ยา (DRP) ในระบบ")

    # --- ✅ ส่วนที่ 5 (ใหม่): รายชื่อผู้รับบริการรายวัน ---
    st.divider()
    st.subheader("🗓️ 5. ตรวจสอบรายชื่อผู้รับบริการ (Daily Log)")
    
    col_date, col_summary = st.columns([1, 2])
    with col_date:
        # ปฏิทินเลือกวันที่
        selected_date = st.date_input("เลือกวันที่ต้องการดูข้อมูล", value=datetime.today())
    
    # กรองข้อมูลตามวันที่เลือก
    daily_visits = df[df['date'].dt.date == selected_date]
    
    if not daily_visits.empty:
        # สรุปยอด
        daily_total = len(daily_visits)
        daily_new = len(daily_visits[daily_visits['is_new_case'].astype(str).str.upper() == 'TRUE'])
        
        with col_summary:
            st.write("") # ดันลงมานิดนึง
            st.markdown(f"**สรุปยอดวันที่ {selected_date.strftime('%d/%m/%Y')}**")
            s1, s2 = st.columns(2)
            s1.metric("ทั้งหมด", f"{daily_total} คน")
            s2.metric("รายใหม่ (New)", f"{daily_new} คน")
        
        # เตรียมข้อมูลสำหรับแสดงผล (Join กับ patients_db เพื่อเอาชื่อ)
        pt_lookup = patients_df[['hn', 'prefix', 'first_name', 'last_name']].copy()
        pt_lookup['hn'] = pt_lookup['hn'].astype(str).str.strip()
        
        daily_visits_show = daily_visits.copy()
        daily_visits_show['hn'] = daily_visits_show['hn'].astype(str).str.strip()
        
        # Merge ข้อมูล
        merged_df = pd.merge(daily_visits_show, pt_lookup, on='hn', how='left')
        merged_df['ชื่อ-สกุล'] = merged_df['prefix'] + merged_df['first_name'] + " " + merged_df['last_name']
        
        # เลือกคอลัมน์ที่จะแสดง
        display_df = merged_df[['hn', 'ชื่อ-สกุล', 'is_new_case', 'pefr', 'control_level', 'note']].copy()
        
        # จัดรูปแบบ
        display_df['is_new_case'] = display_df['is_new_case'].apply(lambda x: "🆕 New" if str(x).upper() == 'TRUE' else "")
        display_df.columns = ['HN', 'ชื่อ-สกุล', 'สถานะ', 'PEFR', 'Control', 'Note']
        
        # เรียงตาม HN
        display_df = display_df.sort_values(by='HN')
        
        st.dataframe(display_df, hide_index=True, use_container_width=True)
    else:
        st.info(f"ℹ️ ไม่มีรายการตรวจในวันที่ {selected_date.strftime('%d/%m/%Y')}")
