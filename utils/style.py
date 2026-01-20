import streamlit as st

def load_custom_css():
    """
    โหลด CSS ปรับแต่งหน้าตา (ฉบับแก้บั๊ก Icon กลายเป็นตัวหนังสือ)
    """
    st.markdown("""
    <style>
        /* 1. IMPORT FONT */
        @import url('https://fonts.googleapis.com/css2?family=Kanit:wght@300;400;500;600&display=swap');
        /* Import Material Icons เพื่อความชัวร์ */
        @import url('https://fonts.googleapis.com/icon?family=Material+Icons');

        /* 2. GLOBAL FONT (SAFE MODE) 
           ❌ เอา 'span', 'div', 'i' ออกจากบรรทัดนี้ เพื่อไม่ให้ไอคอนเพี้ยน */
        html, body, h1, h2, h3, h4, h5, h6, p, li, button, input, textarea, label {
            font-family: 'Kanit', sans-serif !important;
        }
        
        /* สั่งเฉพาะ Text Container ของ Streamlit ให้เป็น Kanit */
        [data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] span {
             font-family: 'Kanit', sans-serif !important;
        }

        /* 3. PROTECT ICONS (สำคัญมาก: กู้ชีพไอคอนลูกศร) */
        /* ถ้าคลาสไหนเป็นไอคอน ให้กลับไปใช้ Font Icon ตามเดิม ห้ามใช้ Kanit */
        i, .material-icons, .material-symbols-rounded, [data-testid="stExpander"] svg {
            font-family: 'Material Icons' !important;
            font-weight: normal;
            font-style: normal;
            display: inline-block;
            white-space: nowrap;
            word-wrap: normal;
            direction: ltr;
        }

        /* 4. FIX EXPANDER LAYOUT */
        /* จัด layout ใหม่ ให้ลูกศรกับตัวหนังสือไม่ขี่กัน */
        div[data-testid="stExpander"] summary {
            display: flex !important;
            align-items: center !important;
            gap: 12px !important; /* ระยะห่างลูกศรกับข้อความ */
        }
        
        /* ซ่อนข้อความขยะที่อาจหลุดมา (ถ้ายังเจอ keyboard_arrow_down) */
        div[data-testid="stExpander"] summary .material-icons {
            font-size: 24px !important;
             /* ถ้ามันยังเป็นตัวหนังสือ ให้บังคับขนาด หรือซ่อนไปเลยแล้วใช้ SVG แทน */
        }

        /* 5. PREMIUM METRIC CARDS */
        div[data-testid="stMetric"] {
            background-color: #FFFFFF;
            padding: 15px;
            border-radius: 12px;
            border: 1px solid #E0E0E0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            text-align: center;
        }
        div[data-testid="stMetricLabel"] {
            font-size: 0.9rem !important;
            color: #607d8b !important;
            font-family: 'Kanit', sans-serif !important; /* บังคับเฉพาะจุด */
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.6rem !important;
            font-weight: 600 !important;
            color: #00695C !important;
            font-family: 'Kanit', sans-serif !important;
        }

        /* 6. INPUT STYLING */
        input {
            font-family: 'Kanit', sans-serif !important;
        }

        /* 7. BACKGROUND */
        .stApp {
            background-color: #F8F9FA;
        }
    </style>
    """, unsafe_allow_html=True)