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

# ----------------------------------------------------------------------------
# 기본 설정
# ----------------------------------------------------------------------------
st.set_page_config(page_title="한/미 경제 동향 대시보드", page_icon="📊", layout="wide")

# API 키는 secrets.toml (로컬) 또는 Streamlit Cloud의 Secrets 설정에서 읽어옵니다.
# 절대 코드에 직접 키를 적지 마세요! (README.md 참고)
ECOS_API_KEY = st.secrets.get("ECOS_API_KEY", "")
FRED_API_KEY = st.secrets.get("FRED_API_KEY", "")

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

st.title("📊 한국 · 미국 경제 동향 대시보드")
st.caption(f"마지막 새로고침: {datetime.now().strftime('%Y-%m-%d %H:%M')} (1시간마다 자동 갱신)")

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
    col1, col2, col3, col4 = st.columns(4)

    fx = fetch_fred_series(FRED_SERIES["원/달러 환율 (KRW per USD)"], "2025-01-01")
    fx_latest, fx_prev, fx_diff = pct_change_over(fx, 1)
    if fx_latest is not None:
        col1.metric("원/달러 환율", f"{fx_latest:,.1f}원", f"{fx_diff:+.1f}")

    us_rate = fetch_fred_series(FRED_SERIES["미국 기준금리 (Fed Funds Rate)"], "2024-01-01")
    if not us_rate.empty:
        col2.metric("미국 기준금리", f"{us_rate.iloc[-1]['value']:.2f}%")

    kr_stats = fetch_ecos_key_stats()
    kr_rate_row = find_kr_stat(kr_stats, KR_KEYWORDS["한국 기준금리"])
    if kr_rate_row is not None:
        col3.metric("한국 기준금리", f"{kr_rate_row['DATA_VALUE']}%")

    us10y = fetch_fred_series(FRED_SERIES["미국 10년물 국채금리"], "2025-01-01")
    if not us10y.empty:
        col4.metric("미국 10년물 국채", f"{us10y.iloc[-1]['value']:.2f}%")

    st.divider()
    news_col1, news_col2 = st.columns(2)
    with news_col1:
        st.markdown("**🇰🇷 한국 경제 주요 뉴스**")
        for n in fetch_news("금리+OR+환율+OR+경제", lang="ko", country="KR"):
            st.markdown(f"- [{n['title']}]({n['link']})")
    with news_col2:
        st.markdown("**🇺🇸 미국 경제 주요 뉴스**")
        for n in fetch_news("federal+reserve+OR+interest+rate+OR+inflation", lang="en", country="US"):
            st.markdown(f"- [{n['title']}]({n['link']})")

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
    st.markdown("**이번 주 주요 뉴스 모아보기**")
    for n in fetch_news("금리+인상+OR+인하+환율+전망", lang="ko", country="KR", max_items=8):
        st.markdown(f"- [{n['title']}]({n['link']}) _{n['published']}_")

# ---------------- 월간 ----------------
with tab_month:
    st.subheader("월간 추이 (최근 6개월)")
    six_months_ago = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.markdown("**미국 소비자물가지수(CPI)**")
        cpi = fetch_fred_series(FRED_SERIES["미국 소비자물가지수(CPI)"], six_months_ago)
        if not cpi.empty:
            st.line_chart(cpi.set_index("date")["value"])

        st.markdown("**미국 실업률**")
        unrate = fetch_fred_series(FRED_SERIES["미국 실업률"], six_months_ago)
        if not unrate.empty:
            st.line_chart(unrate.set_index("date")["value"])

    with chart_col2:
        st.markdown("**원/달러 환율**")
        fx6 = fetch_fred_series(FRED_SERIES["원/달러 환율 (KRW per USD)"], six_months_ago)
        if not fx6.empty:
            st.line_chart(fx6.set_index("date")["value"])

        st.markdown("**미국 기준금리**")
        rate6 = fetch_fred_series(FRED_SERIES["미국 기준금리 (Fed Funds Rate)"], six_months_ago)
        if not rate6.empty:
            st.line_chart(rate6.set_index("date")["value"])

    st.divider()
    with st.expander("🇰🇷 한국 100대 통계지표 전체 보기 (원본 데이터 확인용)"):
        st.dataframe(kr_stats[["CLASS_NAME", "KEYSTAT_NAME", "DATA_VALUE", "CYCLE", "UNIT_NAME"]],
                     use_container_width=True, hide_index=True)
