# utils/styles.py
# Global CSS for MDR PepDesign dashboard
# Supports light + dark themes via the sidebar theme picker in app.py

def inject_css(theme_name="Deep Navy"):
    import streamlit as st

    # ── THEME DEFINITIONS ────────────────────────────────────
    # Each theme defines every color the CSS below uses - swapping
    # theme_name swaps the whole palette, light or dark, automatically.
    THEMES = {
        "Deep Navy": {
            "navy": "#050B18", "card": "#0A1628", "card2": "#0D1E35",
            "violet": "#7C3AED", "cyan": "#06B6D4", "orange": "#E85D24",
            "green": "#10B981", "text": "#F0F4FF", "text2": "#8896B3",
            "text3": "#3D4F6B", "border": "rgba(255,255,255,0.06)",
            "border2": "rgba(255,255,255,0.11)", "is_dark": True,
        },
        "Pure White": {
            "navy": "#FAFBFE", "card": "#FFFFFF", "card2": "#F3F5FA",
            "violet": "#7C3AED", "cyan": "#0891B2", "orange": "#D9480F",
            "green": "#059669", "text": "#0F1729", "text2": "#475569",
            "text3": "#94A3B8", "border": "rgba(15,23,41,0.07)",
            "border2": "rgba(15,23,41,0.12)", "is_dark": False,
        },
        "Forest Green": {
            "navy": "#04342C", "card": "#0A4438", "card2": "#0D5343",
            "violet": "#5DCAA5", "cyan": "#34D399", "orange": "#E85D24",
            "green": "#5DCAA5", "text": "#F0FFF8", "text2": "#9CCABB",
            "text3": "#4D8A75", "border": "rgba(255,255,255,0.06)",
            "border2": "rgba(255,255,255,0.11)", "is_dark": True,
        },
        "Midnight Purple": {
            "navy": "#0D0A1A", "card": "#161229", "card2": "#1C1733",
            "violet": "#AFA9EC", "cyan": "#67E8F9", "orange": "#E85D24",
            "green": "#10B981", "text": "#F4F2FF", "text2": "#A39DD9",
            "text3": "#564F8C", "border": "rgba(255,255,255,0.06)",
            "border2": "rgba(255,255,255,0.11)", "is_dark": True,
        },
    }
    t = THEMES.get(theme_name, THEMES["Deep Navy"])

    # Glow/shadow effects only look right on dark backgrounds - drop them
    # to flat borders on light themes so it doesn't look muddy.
    glow = "0 4px 16px rgba(124,58,237,0.3)" if t["is_dark"] else "0 1px 3px rgba(15,23,41,0.08)"
    glow_hover = "0 6px 24px rgba(124,58,237,0.5)" if t["is_dark"] else "0 2px 8px rgba(15,23,41,0.12)"

    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Syne:wght@600;700;800&family=Inter:wght@300;400;500;600&display=swap');

    :root {{
        --navy:       {t['navy']};
        --card:       {t['card']};
        --card2:      {t['card2']};
        --violet:     {t['violet']};
        --cyan:       {t['cyan']};
        --orange:     {t['orange']};
        --green:      {t['green']};
        --text:       {t['text']};
        --text2:      {t['text2']};
        --text3:      {t['text3']};
        --border:     {t['border']};
        --border2:    {t['border2']};
    }}

    /* Hide default Streamlit chrome */
    #MainMenu, footer, header {{ visibility: hidden }}

    /* Proportional page container - was 0 padding/full-bleed before,
       which made content stretch edge-to-edge on wide screens and look
       cramped on narrow ones. A max-width with auto margins keeps line
       lengths readable at any screen size. */
    .block-container {{
        padding: 1.5rem 2rem !important;
        max-width: 1400px !important;
        margin: 0 auto !important;
    }}
    .stApp {{ background: var(--navy) !important }}

    /* Sidebar */
    [data-testid="stSidebar"] {{
        background: var(--card) !important;
        border-right: 0.5px solid var(--border2) !important;
    }}
    [data-testid="stSidebar"] * {{ color: var(--text2) !important }}
    [data-testid="stSidebarNav"] {{ display: none }}

    /* Metric cards - consistent internal spacing regardless of theme */
    [data-testid="stMetric"] {{
        background: var(--card2);
        border: 0.5px solid var(--border2);
        border-radius: 14px;
        padding: 16px 20px;
    }}
    [data-testid="stMetricLabel"] {{
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 10px !important;
        color: var(--text3) !important;
        text-transform: uppercase;
        letter-spacing: .08em;
    }}
    [data-testid="stMetricValue"] {{
        font-family: 'Syne', sans-serif !important;
        font-size: 28px !important;
        font-weight: 800 !important;
        color: var(--text) !important;
    }}

    /* Columns - consistent gap so multi-column rows (charts, metric rows)
       don't crowd together or drift apart depending on content width */
    [data-testid="stHorizontalBlock"] {{
        gap: 1.25rem;
    }}

    /* Dataframe */
    [data-testid="stDataFrame"] {{
        border: 0.5px solid var(--border2) !important;
        border-radius: 12px !important;
        overflow: hidden !important;
    }}

    /* Buttons */
    .stButton > button {{
        background: linear-gradient(135deg, var(--violet), #9333EA) !important;
        border: none !important;
        color: #fff !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
        border-radius: 10px !important;
        padding: 8px 20px !important;
        box-shadow: {glow} !important;
        transition: all .2s !important;
    }}
    .stButton > button:hover {{
        box-shadow: {glow_hover} !important;
        transform: translateY(-1px) !important;
    }}

    /* Text input */
    .stTextInput > div > div > input {{
        background: var(--card) !important;
        border: 0.5px solid var(--border2) !important;
        border-radius: 10px !important;
        color: var(--text) !important;
        font-family: 'Inter', sans-serif !important;
    }}
    .stTextInput > div > div > input:focus {{
        border-color: rgba(124,58,237,0.5) !important;
        box-shadow: 0 0 0 2px rgba(124,58,237,0.15) !important;
    }}

    /* Select box */
    .stSelectbox > div > div {{
        background: var(--card) !important;
        border: 0.5px solid var(--border2) !important;
        border-radius: 10px !important;
        color: var(--text) !important;
    }}

    /* Slider */
    .stSlider > div > div > div {{
        background: linear-gradient(90deg, var(--violet), var(--cyan)) !important;
    }}

    /* Section header - consistent spacing above/below across all pages */
    .section-head {{
        font-family: 'Syne', sans-serif;
        font-size: 18px;
        font-weight: 700;
        color: var(--text);
        margin: 4px 0 16px;
        display: flex;
        align-items: center;
        gap: 10px;
    }}

    /* Stat card */
    .stat-card {{
        background: var(--card);
        border: 0.5px solid var(--border2);
        border-radius: 14px;
        padding: 18px 20px;
    }}
    .stat-label {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px;
        color: var(--text3);
        text-transform: uppercase;
        letter-spacing: .08em;
        margin-bottom: 6px;
    }}
    .stat-val {{
        font-family: 'Syne', sans-serif;
        font-size: 32px;
        font-weight: 800;
        line-height: 1;
        margin-bottom: 4px;
        color: var(--text);
    }}
    .stat-sub {{
        font-size: 11px;
        color: var(--text3);
    }}

    /* Sequence display */
    .seq-display {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 14px;
        color: var(--cyan);
        background: rgba(6,182,212,0.08);
        border: 0.5px solid rgba(6,182,212,0.2);
        border-radius: 8px;
        padding: 10px 16px;
        letter-spacing: .1em;
    }}

    /* Candidate row */
    .cand-row {{
        background: var(--card);
        border: 0.5px solid var(--border2);
        border-radius: 12px;
        padding: 14px 16px;
        margin-bottom: 8px;
        transition: border-color .15s;
        cursor: pointer;
    }}
    .cand-row:hover {{ border-color: rgba(124,58,237,0.4) }}

    /* Page content padding - kept for any pages still using this class
       directly, now consistent with .block-container above */
    .page-content {{ padding: 0 }}

    /* Divider */
    .divider {{
        height: 0.5px;
        background: var(--border2);
        margin: 24px 0;
    }}

    /* Pulsing status dot (used by the "All systems operational" indicator
       in the sidebar) - was referenced via animation:pulse but never
       actually defined anywhere, so it just sat static. */
    @keyframes pulse {{
        0%, 100% {{ opacity: 1; }}
        50% {{ opacity: 0.35; }}
    }}
    </style>
    """, unsafe_allow_html=True)