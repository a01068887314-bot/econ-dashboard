# -*- coding: utf-8 -*-
"""
한국/미국 경제 동향 자동 대시보드
- 기준금리, 환율, 주요 경제지표, 주요 뉴스를 일간/주간/월간으로 정리
- 데이터 출처: 한국은행 ECOS, 미국 FRED, 구글 뉴스 RSS
"""

import streamlit as st
import requests
import pandas as pd
import feedparser
from datetime import datetime, timedelta
from html import escape

# ----------------------------------------------------------------------------
# 기본 설정
# ----------------------------------------------------------------------------
st.set_page_config(page_title="한/미 경제 동향 대시보드", page_icon="📊", layout="centered")

# 포인트 컬러 (딥 네이비) - 지표 값, 탭, 차트 선 등에 일관되게 사용
ACCENT = "#1B3358"

# API 키는 secrets.toml (로컬) 또는 Streamlit Cloud의 Secrets 설정에서 읽어옵니다.
# 절대 코드에 직접 키를 적지 마세요! (README.md 참고)
ECOS_API_KEY = st.secrets.get("ECOS_API_KEY", "")
FRED_API_KEY = st.secrets.get("FRED_API_KEY", "")

# ----------------------------------------------------------------------------
# 스타일 (CSS) - 데이터/로직에는 영향 없음, 화면 표현만 담당
# ----------------------------------------------------------------------------
st.markdown(
    """
    <style>
    :root {
        --accent: #1B3358;
        --accent-soft: rgba(27, 51, 88, 0.07);
        --text-primary: #111827;
        --text-secondary: #6B7280;
        --text-muted: #9CA3AF;
        --border-color: rgba(17, 24, 39, 0.09);
        --surface: #FFFFFF;
    }

    .block-container {
        padding-top: 2.75rem;
        padding-bottom: 3rem;
        max-width: 760px;
    }

    /* 상단 타이틀 영역 */
    .app-header { margin-bottom: 1.6rem; }
    .app-title {
        font-size: 1.55rem;
        font-weight: 700;
        color: var(--text-primary);
        letter-spacing: -0.01em;
        margin-bottom: 0.3rem;
    }
    .app-subtitle {
        font-size: 0.85rem;
        color: var(--text-secondary);
        font-weight: 400;
    }

    /* 섹션 라벨 (뉴스/표 소제목) */
    .section-label {
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: var(--text-secondary);
        margin: 1.6rem 0 0.6rem 0;
    }

    h3 {
        color: var(--text-primary) !important;
        font-weight: 600 !important;
        font-size: 1.05rem !important;
        letter-spacing: -0.005em;
    }

    /* 지표 카드 (st.metric) */
    div[data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--border-color);
        border-radius: 10px;
        padding: 1rem 1.1rem;
        margin-bottom: 0.7rem;
        box-shadow: 0 1px 2px rgba(17, 24, 39, 0.04);
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.78rem;
        color: var(--text-secondary);
        font-weight: 500;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.6rem;
        font-weight: 700;
        color: var(--text-primary);
    }
    div[data-testid="stMetricDelta"] {
        font-size: 0.82rem;
        font-weight: 500;
    }

    /* 탭 */
    div[data-testid="stTabs"] button[data-baseweb="tab"] {
        font-size: 0.9rem;
        font-weight: 500;
        color: var(--text-secondary);
        padding: 0.55rem 0.25rem;
    }
    div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
        color: var(--accent);
        font-weight: 700;
    }
    div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
        background-color: var(--accent) !important;
        height: 2px;
    }
    div[data-testid="stTabs"] [data-baseweb="tab-border"] {
        background-color: var(--border-color);
    }

    /* 구분선 */
    hr {
        margin: 1.75rem 0;
        border-color: var(--border-color) !important;
    }

    /* 표 */
    div[data-testid="stDataFrame"] {
        border: 1px solid var(--border-color);
        border-radius: 10px;
        overflow: hidden;
    }

    /* 뉴스 카드 */
    .news-card {
        display: block;
        border: 1px solid var(--border-color);
        border-radius: 10px;
        padding: 0.7rem 0.95rem;
        margin-bottom: 0.55rem;
        background: var(--surface);
        text-decoration: none;
        transition: border-color 0.15s ease, background 0.15s ease;
    }
    .news-card:hover {
        border-color: var(--accent);
        background: var(--accent-soft);
    }
    .news-card-title {
        font-size: 0.9rem;
        font-weight: 600;
        color: var(--text-primary);
        line-height: 1.45;
    }
    .news-card-meta {
        font-size: 0.74rem;
        color: var(--text-muted);
        margin-top: 0.25rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

FRED_SERIES = {
    "미국 기준금리 (Fed Funds Rate)": "FEDFUNDS",
    "미국 10년물 국채금리": "DGS10",
    "미국 소비자물가지수(CPI)": "CPIAUCSL",
    "미국 실업률": "UNRATE",
    "원/달러 환율 (KRW per USD)": "DEXKOUS",
}

# 한국 100대 통계지표 중에서 우리가 관심있는 항목을 찾기 위한 키워드
KR_KEYWORDS = {
    "한국 기준금리": ["한국은행 기준금리", "기준금리"],
    "원/달러 환율": ["원/달러", "원화의 대미 달러 환율", "매매기준율"],
    "소비자물가상승률": ["소비자물가지수", "소비자물가상승률"],
    "실업률": ["실업률"],
    "코스피": ["코스피", "KOSPI"],
    "국고채(10년) 금리": ["국고채(10년)", "국고채10년"],
}

# ----------------------------------------------------------------------------
# 데이터 가져오기 함수들 (1시간 동안 캐시 -> API를 너무 자주 호출하지 않음)
# ----------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fred_series(series_id: str, start_date: str) -> pd.DataFrame:
    """미국 FRED에서 시계열 데이터 하나를 가져옵니다."""
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start_date,
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    obs = r.json().get("observations", [])
    df = pd.DataFrame(obs)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["value"])[["date", "value"]]


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ecos_key_stats() -> pd.DataFrame:
    """한국은행 ECOS '100대 통계지표'를 가져옵니다 (기준금리, 환율, CPI 등이 포함된 요약표)."""
    url = f"https://ecos.bok.or.kr/api/KeyStatisticList/{ECOS_API_KEY}/json/kr/1/100"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()
    rows = data.get("KeyStatisticList", {}).get("row", [])
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_news(query: str, lang: str = "ko", country: str = "KR", max_items: int = 5):
    """구글 뉴스 RSS에서 키워드 관련 최신 뉴스를 가져옵니다. API 키 불필요."""
    ceid = f"{country}:{'ko' if lang == 'ko' else 'en'}"
    url = f"https://news.google.com/rss/search?q={query}&hl={lang}&gl={country}&ceid={ceid}"
    feed = feedparser.parse(url)
    items = []
    for entry in feed.entries[:max_items]:
        items.append({
            "title": entry.title,
            "link": entry.link,
            "published": entry.get("published", ""),
        })
    return items


def find_kr_stat(df: pd.DataFrame, keywords: list):
    """100대 통계지표 표에서 키워드가 포함된 첫 번째 행을 찾습니다."""
    if df.empty or "KEYSTAT_NAME" not in df.columns:
        return None
    for kw in keywords:
        match = df[df["KEYSTAT_NAME"].str.contains(kw, na=False)]
        if not match.empty:
            return match.iloc[0]
    return None


def section_label(text: str):
    """뉴스/표 섹션 위에 붙는 작은 라벨을 그립니다."""
    st.markdown(f'<div class="section-label">{text}</div>', unsafe_allow_html=True)


def render_news_card(item: dict):
    """뉴스 한 건을 카드 형태로 그립니다."""
    title = escape(item.get("title", ""))
    published = escape(item.get("published", ""))
    link = item.get("link", "")
    if not link.startswith(("http://", "https://")):
        link = "#"
    meta_html = f'<div class="news-card-meta">{published}</div>' if published else ""
    st.markdown(
        f'<a class="news-card" href="{link}" target="_blank" rel="noopener noreferrer">'
        f'<div class="news-card-title">{title}</div>{meta_html}</a>',
        unsafe_allow_html=True,
    )


def pct_change_over(df: pd.DataFrame, days: int):
    """최신값과 N일 전 값의 변화를 계산합니다."""
    if df.empty or len(df) < 2:
        return None, None, None
    latest_row = df.iloc[-1]
    target_date = latest_row["date"] - timedelta(days=days)
    past = df[df["date"] <= target_date]
    if past.empty:
        past_row = df.iloc[0]
    else:
        past_row = past.iloc[-1]
    latest_val = latest_row["value"]
    past_val = past_row["value"]
    return latest_val, past_val, latest_val - past_val


# ----------------------------------------------------------------------------
# 화면 그리기
# ----------------------------------------------------------------------------

st.markdown(
    f"""
    <div class="app-header">
        <div class="app-title">📊 한국 · 미국 경제 동향 대시보드</div>
        <div class="app-subtitle">
            기준금리 · 환율 · 주요 지표를 한눈에 ·
            마지막 새로고침 {datetime.now().strftime('%Y-%m-%d %H:%M')} (1시간마다 자동 갱신)
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if not FRED_API_KEY or not ECOS_API_KEY:
    st.warning(
        "⚠️ API 키가 설정되지 않았습니다. README.md의 안내에 따라 "
        "`.streamlit/secrets.toml` 파일 또는 Streamlit Cloud의 Secrets에 "
        "ECOS_API_KEY, FRED_API_KEY를 입력해주세요."
    )
    st.stop()

tab_day, tab_week, tab_month = st.tabs(["📅 일간", "📆 주간", "🗓️ 월간"])

# ---------------- 일간 ----------------
with tab_day:
    st.subheader("오늘의 핵심 지표")

    fx = fetch_fred_series(FRED_SERIES["원/달러 환율 (KRW per USD)"], "2025-01-01")
    fx_latest, fx_prev, fx_diff = pct_change_over(fx, 1)
    if fx_latest is not None:
        st.metric("원/달러 환율", f"{fx_latest:,.1f}원", f"{fx_diff:+.1f}")

    us_rate = fetch_fred_series(FRED_SERIES["미국 기준금리 (Fed Funds Rate)"], "2024-01-01")
    if not us_rate.empty:
        st.metric("미국 기준금리", f"{us_rate.iloc[-1]['value']:.2f}%")

    kr_stats = fetch_ecos_key_stats()
    kr_rate_row = find_kr_stat(kr_stats, KR_KEYWORDS["한국 기준금리"])
    if kr_rate_row is not None:
        st.metric("한국 기준금리", f"{kr_rate_row['DATA_VALUE']}%")

    us10y = fetch_fred_series(FRED_SERIES["미국 10년물 국채금리"], "2025-01-01")
    if not us10y.empty:
        st.metric("미국 10년물 국채", f"{us10y.iloc[-1]['value']:.2f}%")

    st.divider()
    section_label("🇰🇷 한국 경제 주요 뉴스")
    for n in fetch_news("금리+OR+환율+OR+경제", lang="ko", country="KR"):
        render_news_card(n)

    section_label("🇺🇸 미국 경제 주요 뉴스")
    for n in fetch_news("federal+reserve+OR+interest+rate+OR+inflation", lang="en", country="US"):
        render_news_card(n)

# ---------------- 주간 ----------------
with tab_week:
    st.subheader("최근 1주일간 변화")
    rows = []
    for label, series_id in FRED_SERIES.items():
        df = fetch_fred_series(series_id, "2025-01-01")
        latest, past, diff = pct_change_over(df, 7)
        if latest is not None:
            rows.append({"지표": label, "현재값": round(latest, 3), "1주일 전": round(past, 3), "변화": round(diff, 3)})
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.divider()
    section_label("이번 주 주요 뉴스 모아보기")
    for n in fetch_news("금리+인상+OR+인하+환율+전망", lang="ko", country="KR", max_items=8):
        render_news_card(n)

# ---------------- 월간 ----------------
with tab_month:
    st.subheader("월간 추이 (최근 6개월)")
    six_months_ago = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

    section_label("미국 소비자물가지수(CPI)")
    cpi = fetch_fred_series(FRED_SERIES["미국 소비자물가지수(CPI)"], six_months_ago)
    if not cpi.empty:
        st.line_chart(cpi.set_index("date")["value"], color=[ACCENT])

    section_label("미국 실업률")
    unrate = fetch_fred_series(FRED_SERIES["미국 실업률"], six_months_ago)
    if not unrate.empty:
        st.line_chart(unrate.set_index("date")["value"], color=[ACCENT])

    section_label("원/달러 환율")
    fx6 = fetch_fred_series(FRED_SERIES["원/달러 환율 (KRW per USD)"], six_months_ago)
    if not fx6.empty:
        st.line_chart(fx6.set_index("date")["value"], color=[ACCENT])

    section_label("미국 기준금리")
    rate6 = fetch_fred_series(FRED_SERIES["미국 기준금리 (Fed Funds Rate)"], six_months_ago)
    if not rate6.empty:
        st.line_chart(rate6.set_index("date")["value"], color=[ACCENT])

    st.divider()
    with st.expander("🇰🇷 한국 100대 통계지표 전체 보기 (원본 데이터 확인용)"):
        st.dataframe(kr_stats[["CLASS_NAME", "KEYSTAT_NAME", "DATA_VALUE", "CYCLE", "UNIT_NAME"]],
                     use_container_width=True, hide_index=True)
