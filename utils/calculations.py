import altair as alt
import pandas as pd
import qrcode
from io import BytesIO
from datetime import datetime, timedelta

def calculate_predicted_pefr(age, height_cm, gender_prefix):
    if not height_cm or height_cm <= 0: return 0
    is_male = True
    prefix = str(gender_prefix).strip()
    if any(x in prefix for x in ['นาง', 'น.ส.', 'หญิง', 'ด.ญ.', 'Miss', 'Mrs.']):
        is_male = False
      
    if age < 15:
        predicted = -425.5714 + (5.2428 * height_cm)
        return max(predicted, 100)
    else:
        h = height_cm
        a = age
        if is_male:
            pefr_ls = -16.859 + (0.307*a) + (0.141*h) - (0.0018*a**2) - (0.001*a*h)
        else:
            pefr_ls = -31.355 + (0.162*a) - (0.00084*a**2) + (0.391*h) - (0.00099*h**2) - (0.00072*a*h)
        return pefr_ls * 60

def get_percent_predicted(current_pefr, predicted_pefr):
    if predicted_pefr <= 0 or current_pefr <= 0: return 0
    return int((current_pefr / predicted_pefr) * 100)

def get_action_plan_zone(current_pefr, reference_pefr):
    if current_pefr <= 0: return "Not Done", "gray", "ไม่ได้เป่า Peak Flow"
    if reference_pefr <= 0: return "Unknown", "gray", "ไม่มีข้อมูลอ้างอิง"
    percent = (current_pefr / reference_pefr) * 100
    if percent >= 80: return "Green Zone", "green", "คุมได้ดี"
    elif percent >= 50: return "Yellow Zone", "orange", "เริ่มมีอาการ"
    else: return "Red Zone", "red", "อันตราย"

def check_technique_status(pt_visits_df):
    if pt_visits_df.empty: return "never", 0, None
    reviews = pt_visits_df[pt_visits_df['technique_check'].astype(str).str.contains('ทำ', na=False)]
    if reviews.empty: return "never", 0, None
    reviews = reviews.copy()
    reviews['date'] = pd.to_datetime(reviews['date'])
    last_date = reviews['date'].max()
    days_remaining = (last_date + timedelta(days=365) - pd.to_datetime("today").normalize()).days
    if days_remaining < 0: return "overdue", abs(days_remaining), last_date
    else: return "ok", days_remaining, last_date

def mask_text(text):
    if not isinstance(text, str): return str(text)
    if len(text) <= 2: return text[0] + "x" * (len(text)-1)
    return text[:2] + "x" * (len(text)-2)

def generate_qr(data):
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf)
    return buf.getvalue()

def plot_pefr_chart(visits_df, reference_pefr):
    data = visits_df.copy()
    data = data[data['pefr'] > 0]
    if data.empty:
        return alt.Chart(pd.DataFrame({'date':[], 'pefr':[]})).mark_text(text="ไม่มีข้อมูลกราฟ PEFR")

    data['date'] = pd.to_datetime(data['date'])
    ref_val = reference_pefr if reference_pefr > 0 else data['pefr'].max()
      
    def get_color(val):
        if val >= ref_val * 0.8: return 'green'
        elif val >= ref_val * 0.5: return 'orange'
        else: return 'red'
    data['color'] = data['pefr'].apply(get_color)

    base = alt.Chart(data).encode(
        x=alt.X('date', title='วันที่', axis=alt.Axis(format='%d/%m/%Y')),
        y=alt.Y('pefr', title='PEFR (L/min)', scale=alt.Scale(domain=[0, ref_val + 150])),
        tooltip=[alt.Tooltip('date', format='%d/%m/%Y'), 'pefr']
    )
    line = base.mark_line(color='gray').encode()
    points = base.mark_circle(size=100).encode(color=alt.Color('color', scale=None))
    rule_green = alt.Chart(pd.DataFrame({'y': [ref_val * 0.8]})).mark_rule(color='green', strokeDash=[5, 5]).encode(y='y')
    rule_red = alt.Chart(pd.DataFrame({'y': [ref_val * 0.5]})).mark_rule(color='red', strokeDash=[5, 5]).encode(y='y')
    return (line + points + rule_green + rule_red).properties(height=350).interactive()