import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, timedelta # ต้อง import timedelta ด้วย
import io

def render_dashboard(visits_df, patients_df):
    if visits_df.empty:
        st.warning("ยังไม่มีข้อมูลการตรวจเยี่ยม")
        return

    # --- 0. เตรียมข้อมูลหลัก (Data Preparation) ---
    df = pd.merge(
        visits_df, 
        patients_df[['hn', 'prefix', 'first_name', 'last_name']], 
        on='hn', 
        how='left'
    )
    
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    # แปลง next_appt เป็น datetime เพื่อใช้เปรียบเทียบ
    df['next_appt'] = pd.to_datetime(df['next_appt'], errors='coerce')
    
    df['month_year'] = df['date'].dt.strftime('%Y-%m') 
    df['full_name'] = df['prefix'].fillna('') + df['first_name'].fillna('') + " " + df['last_name'].fillna('')
    
    # ✅ FIX TIMEZONE: ปรับเวลา Server (UTC) เป็นไทย (UTC+7)
    thai_now = datetime.now() + timedelta(hours=7)
    today_date = thai_now.date()
    today_str_iso = today_date.strftime('%Y-%m-%d') # สำหรับเทียบกับ DataFrame
    
    # ==============================================================================
    # 🔔 ส่วนใหม่: แจ้งเตือนนัดหมายวันนี้ (Today's Appointments & DRP Alert)
    # ==============================================================================
    
    # กรองหาแถวที่มีวันนัด (next_appt) ตรงกับวันนี้ (เวลาไทย)
    appts_today = df[df['next_appt'].dt.date == today_date].copy()
    count_appt = len(appts_today)
    
    st.markdown(f"### 🔔 นัดหมายประจำวันที่ : {today_date.strftime('%d/%m/%Y')}")
    
    if count_appt > 0:
        st.info(f"มีผู้ป่วยนัดวันนี้จำนวน **{count_appt}** ราย")
        
        # เตรียมข้อมูลแสดงผล
        display_appt = appts_today[['hn', 'full_name', 'drp']].copy()
        
        # ฟังก์ชันเช็ค DRP เพื่อสร้าง Alert
        def check_drp_status(val):
            val_str = str(val).strip()
            if val_str not in ['', '-', 'nan', 'None']:
                return f"⚠️ {val_str}" # มีปัญหา ให้โชว์ Warning
            return "✅ ปกติ" # ไม่มีปัญหา

        display_appt['drp_status'] = display_appt['drp'].apply(check_drp_status)
        
        # เรียงลำดับ: เอาคนที่มีปัญหา DRP ขึ้นก่อน
        display_appt['has_issue'] = display_appt['drp_status'].str.contains('⚠️')
        display_appt = display_appt.sort_values(by=['has_issue', 'hn'], ascending=[False, True])
        
        # แสดงตาราง
        st.dataframe(
            display_appt[['hn', 'full_name', 'drp_status']],
            column_config={
                "hn": "HN",
                "full_name": "ชื่อ-สกุล",
                "drp_status": st.column_config.TextColumn("สถานะการใช้ยา (Visit ล่าสุด)", width="large"),
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.success("✅ ไม่มีรายชื่อผู้ป่วยนัดหมายในวันนี้")

    st.divider()

    # ==============================================================================
    # (ส่วนที่เหลือเหมือนเดิม แต่ปรับตัวแปรวันที่ให้ใช้ Timezone ไทย)
    # ==============================================================================

    # --- ส่วนที่ 1: สรุปยอดประจำวัน (Walk-in / Visit จริงที่เกิดขึ้นวันนี้) ---
    # ใช้ today_str_iso ที่ปรับเวลาไทยแล้ว
    today_visits_real = df[df['date'].dt.strftime('%Y-%m-%d') == today_str_iso]
    count_today_total = len(today_visits_real)
    
    if 'is_new_case' in df.columns:
        today_new_cases = today_visits_real[today_visits_real['is_new_case'].astype(str).str.upper() == 'TRUE']
        count_today_new = len(today_new_cases)
    else:
        count_today_new = 0
        
    total_patients = len(df['hn'].unique())

    st.subheader(f"📅 สรุปยอดผู้มารับบริการจริง")
    
    m1, m2, m3 = st.columns(3)
    m1.metric("ผู้รับบริการวันนี้", f"{count_today_total} คน", "Visits", delta_color="off")
    m2.metric("ผู้ป่วยใหม่วันนี้", f"{count_today_new} คน", f"+{count_today_new}" if count_today_new > 0 else "0")
    m3.metric("ทะเบียนผู้ป่วยสะสม", f"{total_patients} คน")
    st.divider()

    # --- ส่วนที่ 2: ปริมาณงานรายเดือน (Monthly Workload) ---
    st.subheader("📈 1. ปริมาณงานรายเดือน (Monthly Workload)")
    
    # 2.1 กราฟแนวโน้ม
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

    # 2.2 ตารางสรุปรายเดือน
    one_year_ago = thai_now - timedelta(days=365) # ใช้เวลาไทย
    df_1y = df[df['date'] >= one_year_ago].copy()
    
    if not df_1y.empty:
        monthly_summary = df_1y.groupby('month_year').agg(
            total_visits=('hn', 'count'),
            new_cases=('is_new_case', lambda x: (x.astype(str).str.upper() == 'TRUE').sum())
        ).reset_index()
        
        monthly_summary = monthly_summary.sort_values('month_year', ascending=False)
        monthly_summary['Month Name'] = pd.to_datetime(monthly_summary['month_year'] + '-01').dt.strftime('%B %Y')
        display_monthly = monthly_summary[['Month Name', 'total_visits', 'new_cases']]
        display_monthly.columns = ['เดือน', 'จำนวนผู้ป่วยทั้งหมด (ราย)', 'ผู้ป่วยใหม่ (ราย)']

        with st.expander("📂 ดูตารางสรุปยอดรายเดือน (คลิก)", expanded=False):
            st.dataframe(
                display_monthly,
                column_config={
                    "เดือน": st.column_config.TextColumn("เดือน"),
                    "จำนวนผู้ป่วยทั้งหมด (ราย)": st.column_config.NumberColumn("ยอดรวม (คน)", format="%d"),
                    "ผู้ป่วยใหม่ (ราย)": st.column_config.NumberColumn("รายใหม่ (คน)", format="%d"),
                },
                hide_index=True,
                use_container_width=True
            )

    st.divider()

    # --- ส่วนที่ 3: ปริมาณงานรายสัปดาห์ (4 Weeks) ---
    st.subheader("📊 2. ปริมาณงานรายสัปดาห์ (4 Weeks Lookback)")
    
    weeks_to_look_back = 4
    four_weeks_ago = thai_now - timedelta(weeks=weeks_to_look_back) # ใช้เวลาไทย
    df_weekly = df[df['date'] >= four_weeks_ago].copy()
    
    if not df_weekly.empty:
        df_weekly['week_start'] = df_weekly['date'].dt.to_period('W').apply(lambda r: r.start_time)
        
        total_visits_period = len(df_weekly)
        total_new_period = len(df_weekly[df_weekly['is_new_case'].astype(str).str.upper() == 'TRUE'])
        
        avg_visits_per_week = total_visits_period / weeks_to_look_back
        avg_new_per_week = total_new_period / weeks_to_look_back
        
        c_avg1, c_avg2 = st.columns(2)
        with c_avg1:
            st.metric(label=f"เฉลี่ยผู้ป่วย (ย้อนหลัง {weeks_to_look_back} สัปดาห์)", value=f"{avg_visits_per_week:.1f} คน/สัปดาห์")
        with c_avg2:
            st.metric(label="เฉลี่ยผู้ป่วยใหม่", value=f"{avg_new_per_week:.1f} คน/สัปดาห์")
        
        st.write("") 

        st.markdown("##### 📂 รายละเอียดรายสัปดาห์")
        unique_weeks = sorted(df_weekly['week_start'].unique(), reverse=True)
        
        for w in unique_weeks:
            week_mask = df_weekly['week_start'] == w
            week_data = df_weekly[week_mask].sort_values(by='date', ascending=False)
            
            w_total = len(week_data)
            w_new = len(week_data[week_data['is_new_case'].astype(str).str.upper() == 'TRUE'])
            week_label = w.strftime('%d/%m/%Y')
            
            with st.expander(f"Week {week_label} (รวม: {w_total} | ใหม่: {w_new})"):
                 st.dataframe(
                    week_data[['date', 'hn', 'full_name', 'pefr', 'control_level', 'note']],
                    column_config={
                        "date": st.column_config.DateColumn("วันที่", format="DD/MM/YYYY"),
                        "hn": "HN",
                        "full_name": "ชื่อ-สกุล",
                        "pefr": "PEFR",
                        "control_level": "สถานะ",
                        "note": "Note"
                    },
                    hide_index=True,
                    use_container_width=True
                )
    else:
        st.info("ไม่มีข้อมูลในช่วง 4 สัปดาห์ที่ผ่านมา")

    st.divider()

    # --- ส่วนที่ 4: KPI ย่อย ---
    c_left, c_right = st.columns([1, 1.2])
    
    with c_left:
        st.subheader("3. การควบคุมโรค (Status)")
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
        st.subheader("4. สอนเทคนิคพ่นยา (Fiscal Year)")
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

    # --- ส่วนที่ 5: สถิติ DRP ---
    st.divider()
    st.subheader("💊 5. สถิติปัญหาจากการใช้ยา (DRP Summary)")
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

    # --- ส่วนที่ 6: รายชื่อผู้รับบริการรายวัน (Log) ---
    st.divider()
    st.subheader("🗓️ 6. ตรวจสอบรายชื่อผู้รับบริการ (Daily Log)")
    
    col_date, col_summary = st.columns([1, 2])
    with col_date:
        # ใช้วันที่ปัจจุบัน (ไทย) เป็นค่าเริ่มต้น
        selected_date = st.date_input("เลือกวันที่ต้องการดูข้อมูล", value=thai_now.date())
    
    daily_visits = df[df['date'].dt.date == selected_date]
    
    if not daily_visits.empty:
        daily_total = len(daily_visits)
        daily_new = len(daily_visits[daily_visits['is_new_case'].astype(str).str.upper() == 'TRUE'])
        
        with col_summary:
            st.write("")
            st.markdown(f"**สรุปยอดวันที่ {selected_date.strftime('%d/%m/%Y')}**")
            s1, s2 = st.columns(2)
            s1.metric("ทั้งหมด", f"{daily_total} คน")
            s2.metric("รายใหม่ (New)", f"{daily_new} คน")
        
        display_df = daily_visits[['hn', 'full_name', 'is_new_case', 'pefr', 'control_level', 'note']].copy()
        display_df['is_new_case'] = display_df['is_new_case'].apply(lambda x: "🆕 New" if str(x).upper() == 'TRUE' else "")
        display_df.columns = ['HN', 'ชื่อ-สกุล', 'สถานะ', 'PEFR', 'Control', 'Note']
        display_df = display_df.sort_values(by='HN')
        
        st.dataframe(display_df, hide_index=True, use_container_width=True)
    else:
        st.info(f"ℹ️ ไม่มีรายการตรวจในวันที่ {selected_date.strftime('%d/%m/%Y')}")

    # --- ส่วนที่ 7: สำรองข้อมูล ---
    st.divider()
    st.subheader("💾 7. สำรองข้อมูล (Backup Database)")
    st.info("ระบบจะรวมข้อมูล 'ทะเบียนผู้ป่วย (Patients)' และ 'ประวัติการตรวจ (Visits)' ทั้งหมดเป็นไฟล์ Excel เดียว")

    def to_excel(df1, df2):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df1.to_excel(writer, sheet_name='Patients', index=False)
            df2.to_excel(writer, sheet_name='Visits', index=False)
        processed_data = output.getvalue()
        return processed_data

    # ชื่อไฟล์ Backup ก็ควรเป็นเวลาไทยด้วย
    timestamp = thai_now.strftime("%Y-%m-%d_%H-%M")
    file_name = f"asthma_backup_{timestamp}.xlsx"
    excel_data = to_excel(patients_df, visits_df)

    st.download_button(
        label="📥 ดาวน์โหลดไฟล์ Backup (.xlsx)",
        data=excel_data,
        file_name=file_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        help="คลิกเพื่อดาวน์โหลดข้อมูลทั้งหมดลงเครื่องคอมพิวเตอร์"
    )
