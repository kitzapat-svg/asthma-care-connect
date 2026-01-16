import pandas as pd
import altair as alt
import qrcode
import io

# 1. คำนวณค่ามาตรฐาน (Predicted PEFR)
def calculate_predicted_pefr(age, height, gender_prefix):
    age = int(age)
    height = int(height)
    
    if gender_prefix in ["นาย", "ด.ช."]:
        predicted = (5.48 * height) - (1.51 * age) - 279.7
    else:
        predicted = (3.72 * height) - (2.24 * age) - 96.6
    
    return max(0, predicted)

# 2. คำนวณเปอร์เซ็นต์
def get_percent_predicted(current_pefr, predicted_pefr):
    if predicted_pefr == 0: return 0
    return int((current_pefr / predicted_pefr) * 100)

# 3. กำหนด Action Plan Zone
def get_action_plan_zone(current_pefr, predicted_pefr):
    pct = get_percent_predicted(current_pefr, predicted_pefr)
    
    if pct >= 80:
        return (
            "🟢 Green Zone (ควบคุมได้ดี)", 
            "#2E7D32", 
            """✅ <b>ใช้ชีวิตและออกกำลังกายได้ตามปกติ</b><br>
            ⚠️ <b>สำคัญ:</b> ให้ใช้ 'ยาควบคุมอาการ' (Controller) ต่อไปตามที่แพทย์สั่ง (ห้ามหยุดยาเอง)"""
        )
    elif pct >= 60:
        return (
            "🟡 Yellow Zone (เริ่มมีอาการ)", 
            "#F9A825", 
            """⚡ <b>ให้พก 'ยาฉุกเฉิน' ติดตัวเสมอ และใช้ทันทีเมื่อมีอาการ</b><br>
            🔍 <b>สำคัญ:</b> ควรปรึกษาแพทย์หรือเภสัชกร เพื่อตรวจสอบเทคนิคการพ่นยา หรือค้นหาสิ่งกระตุ้นอาการ (ไม่ควรปล่อยไว้นาน)"""
        )
    else:
        return (
            "🔴 Red Zone (อันตราย)", 
            "#C62828", 
            """🚨 <b>ระวังอันตราย! อาการหอบอาจกำเริบรุนแรงได้ทุกเมื่อ</b><br>
            🏥 <b>สำคัญ:</b> ต้องรีบกลับไปพบแพทย์ 'ก่อนวันนัด' หากมีอาการแย่ลง หรือพ่นยาฉุกเฉินแล้วอาการยังไม่ทุเลา"""
        )

# 4. วาดกราฟแนวโน้ม (Trend Chart) - ✅ เพิ่มพื้นที่กันตกขอบ
def plot_pefr_chart(visits_df, predicted_pefr):
    df = visits_df.copy()
    df['date'] = pd.to_datetime(df['date'])
    
    base = alt.Chart(df).encode(x=alt.X('date', title='วันที่'))
    
    line = base.mark_line(point=True).encode(
        y=alt.Y(
            'pefr', 
            title='ค่าการเป่าปอด (L/min)', 
            scale=alt.Scale(domain=[0, 800])
        ),
        tooltip=[
            alt.Tooltip('date', title='วันที่', format='%d/%m/%Y'),
            alt.Tooltip('pefr', title='ค่า PEFR')
        ]
    )
    
    rule_green = alt.Chart(pd.DataFrame({'y': [predicted_pefr * 0.8]})).mark_rule(color='#66BB6A', strokeDash=[5, 5]).encode(y='y')
    rule_red = alt.Chart(pd.DataFrame({'y': [predicted_pefr * 0.6]})).mark_rule(color='#EF5350', strokeDash=[5, 5]).encode(y='y')
    
    chart = (line + rule_green + rule_red).properties(height=300).interactive()
    
    # ✅ ปรับ left padding จาก 50 เป็น 70 (เผื่อที่ให้แกน Y เวลา Zoom Out)
    return chart.configure(padding={'left': 70, 'top': 10, 'right': 10, 'bottom': 10})

# 5. ตรวจสอบสถานะเทคนิคพ่นยา
def check_technique_status(visits_df):
    if visits_df.empty:
        return "never", 0, None

    visits_df['date'] = pd.to_datetime(visits_df['date'])
    tech_visits = visits_df[visits_df['technique_check'].astype(str).str.contains("ทำ", na=False)].sort_values(by='date')
    
    if tech_visits.empty:
        return "never", 0, None
        
    last_tech_date = tech_visits.iloc[-1]['date']
    days_since = (pd.Timestamp.now() - last_tech_date).days
    
    if days_since > 365:
        return "overdue", days_since, last_tech_date
    else:
        return "valid", days_since, last_tech_date

# 6. สร้าง QR Code
def generate_qr(data):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    return img_byte_arr.getvalue()
