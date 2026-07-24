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
import time
import yfinance as yf
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
# [확장 1] 데이터 범위 확장 - 2010년 1월 ~ 현재까지
# 아래는 전부 새로 추가된 함수/상수이며, 기존 함수·화면 코드는 건드리지 않았습니다.
# UI 반영(화면에 그리기)은 다음 단계에서 진행합니다.
# ----------------------------------------------------------------------------

DEFAULT_START_DATE = "2010-01-01"   # 문자열(YYYY-MM-DD) 형식 - yfinance/FRED 공용
DEFAULT_START_PERIOD = "201001"     # YYYYMM 형식 - ECOS 전용

# --- 1. 주식 지수 및 주요 종목 (yfinance, API 키 불필요) ------------------------

STOCK_INDEX_TICKERS = {
    "코스피": "^KS11",
    "코스닥": "^KQ11",
    "S&P500": "^GSPC",
    "나스닥종합": "^IXIC",
}

KR_STOCK_TICKERS = {
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
    "현대차": "005380.KS",
    "LG에너지솔루션": "373220.KS",
    "삼성바이오로직스": "207940.KS",
}

US_STOCK_TICKERS = {
    "애플(AAPL)": "AAPL",
    "마이크로소프트(MSFT)": "MSFT",
    "엔비디아(NVDA)": "NVDA",
    "구글(GOOGL)": "GOOGL",
    "아마존(AMZN)": "AMZN",
}

# 위 세 딕셔너리를 합쳐서 한 번에 참조할 수 있는 전체 티커 맵
ALL_STOCK_TICKERS = {**STOCK_INDEX_TICKERS, **KR_STOCK_TICKERS, **US_STOCK_TICKERS}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yf_series(ticker: str, start_date: str = DEFAULT_START_DATE, retries: int = 3) -> pd.DataFrame:
    """yfinance로 지수/종목의 종가(Close) 시계열을 가져옵니다.
    일시적인 오류에 대비해 최대 retries회 재시도하고, 끝까지 실패하면
    예외를 던지지 않고 빈 DataFrame(columns=[date, value])을 반환합니다.
    (호출부에서 df.empty로 체크 후 "일시적으로 데이터를 가져올 수 없습니다" 등으로 안내하면 됩니다.)
    """
    for attempt in range(retries):
        try:
            raw = yf.download(
                ticker, start=start_date, progress=False,
                auto_adjust=True, timeout=15,
            )
            if raw is not None and not raw.empty and "Close" in raw.columns.get_level_values(0):
                close = raw["Close"]
                if isinstance(close, pd.DataFrame):
                    close = close.iloc[:, 0]
                df = pd.DataFrame({"date": raw.index, "value": close.values})
                df = df.dropna(subset=["value"]).reset_index(drop=True)
                if not df.empty:
                    return df
        except Exception:
            pass
        if attempt < retries - 1:
            time.sleep(1.5)
    return pd.DataFrame(columns=["date", "value"])


def fetch_all_stocks(tickers: dict, start_date: str = DEFAULT_START_DATE) -> dict:
    """{라벨: 티커} 딕셔너리를 받아 {라벨: DataFrame} 형태로 일괄 조회합니다."""
    return {label: fetch_yf_series(ticker, start_date) for label, ticker in tickers.items()}


# --- 2. 환율 (5개국, USD 기준 크로스환율) --------------------------------------

FX_SERIES_EXT = {
    "엔/달러 환율 (JPY per USD)": "DEXJPUS",
    "위안/달러 환율 (CNY per USD)": "DEXCHUS",
    "달러인덱스 (Broad, 미국은 기준통화라 인덱스로 대체)": "DTWEXBGS",
    # 원/달러(DEXKOUS)는 기존 FRED_SERIES에 이미 있어 재사용합니다.
}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_eur_per_usd(start_date: str = DEFAULT_START_DATE) -> pd.DataFrame:
    """유로/달러 환율을 'EUR per USD' 기준으로 통일해서 반환합니다.
    FRED의 DEXUSEU는 반대 방향(USD per EUR)으로 고시되므로 역수를 취합니다.
    """
    df = fetch_fred_series("DEXUSEU", start_date)
    if df.empty:
        return df
    out = df.copy()
    out["value"] = 1.0 / out["value"]
    return out


# --- 3. 기준금리 (한국/일본/미국) ----------------------------------------------
# 미국 기준금리(FEDFUNDS)는 기존 FRED_SERIES에 이미 있어 재사용합니다.

# 일본은행(BOJ)은 정책금리를 '무담보 콜금리(익일물)'로 운용합니다.
# FRED의 공식 정책금리 시리즈(IRSTCB01JPM156N)는 2023-12 이후 갱신이 끊겨 있어,
# 실제로 BOJ가 목표로 삼는 콜/은행간 금리 시리즈(IRSTCI01JPM156N, 2026-06까지 갱신 확인)를
# 정책금리의 대체 지표로 사용합니다.
JP_POLICY_RATE_SERIES = "IRSTCI01JPM156N"
JP_POLICY_RATE_NOTE = (
    "일본은행 공식 정책금리 시리즈는 FRED에서 2023년 12월 이후 갱신이 중단되어, "
    "실제 정책 운용 목표인 '무담보 콜금리(익일물)' 시리즈로 대체 표시합니다. "
    "정책금리와 거의 동일하게 움직입니다."
)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_jp_policy_rate(start_date: str = DEFAULT_START_DATE) -> pd.DataFrame:
    """일본 기준금리(콜금리 대체 지표)를 가져옵니다."""
    return fetch_fred_series(JP_POLICY_RATE_SERIES, start_date)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ecos_series(stat_code: str, item_code1: str, cycle: str = "M",
                       start_period: str = DEFAULT_START_PERIOD, end_period: str = None) -> pd.DataFrame:
    """한국은행 ECOS StatisticSearch API로 특정 통계표의 시계열 데이터를 가져옵니다.
    (기존 fetch_ecos_key_stats는 '100대 통계지표' 스냅샷만 가져오는 함수라
    시계열이 필요한 경우를 위해 별도로 추가한 범용 함수입니다.)
    """
    if end_period is None:
        end_period = datetime.now().strftime("%Y%m")
    url = (
        f"https://ecos.bok.or.kr/api/StatisticSearch/{ECOS_API_KEY}/json/kr/1/500/"
        f"{stat_code}/{cycle}/{start_period}/{end_period}/{item_code1}"
    )
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()
    rows = data.get("StatisticSearch", {}).get("row", [])
    df = pd.DataFrame(rows)
    if df.empty or "DATA_VALUE" not in df.columns:
        return pd.DataFrame(columns=["date", "value"])
    df["date"] = pd.to_datetime(df["TIME"], format="%Y%m", errors="coerce")
    df["value"] = pd.to_numeric(df["DATA_VALUE"], errors="coerce")
    return df.dropna(subset=["date", "value"])[["date", "value"]].sort_values("date").reset_index(drop=True)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_kr_base_rate(start_period: str = DEFAULT_START_PERIOD) -> pd.DataFrame:
    """한국 기준금리 시계열 (ECOS 722Y001, 한국은행 기준금리 및 여수신금리)."""
    return fetch_ecos_series("722Y001", "0101000", cycle="M", start_period=start_period)


# --- 4. 각국 보조 경제지표 (실업률/CPI) ----------------------------------------

def is_data_stale(df: pd.DataFrame, max_age_days: int = 400) -> bool:
    """가장 최근 관측치가 max_age_days 이상 지났으면 '갱신이 끊긴' 것으로 간주합니다."""
    if df.empty:
        return True
    last_date = pd.to_datetime(df.iloc[-1]["date"])
    return (datetime.now() - last_date.to_pydatetime()).days > max_age_days


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_kr_unemployment(start_date: str = DEFAULT_START_DATE) -> pd.DataFrame:
    """한국 실업률 (FRED, LRHUTTTTKRM156S)."""
    return fetch_fred_series("LRHUTTTTKRM156S", start_date)


def fetch_kr_cpi(start_date: str = DEFAULT_START_DATE, start_period: str = DEFAULT_START_PERIOD):
    """한국 소비자물가지수(CPI, 총지수).
    1순위: ECOS StatisticSearch(901Y009, 총지수) / 2순위(ECOS 실패시): FRED KORCPIALLMINMEI
    반환값: (DataFrame, note) - note는 출처/갱신상태에 대한 안내 문구
    """
    df = fetch_ecos_series("901Y009", "0", cycle="M", start_period=start_period)
    if not df.empty and not is_data_stale(df):
        return df, "출처: 한국은행 ECOS (소비자물가지수, 총지수)"

    fallback = fetch_fred_series("KORCPIALLMINMEI", start_date)
    if not fallback.empty and not is_data_stale(fallback):
        return fallback, "출처: FRED KORCPIALLMINMEI"

    # 둘 다 최신 데이터가 없는 경우: 그래도 있는 데이터 중 더 최근 것을 보여주되 경고 문구를 붙임
    best = df if (not df.empty and (fallback.empty or df.iloc[-1]["date"] >= fallback.iloc[-1]["date"])) else fallback
    return best, "⚠️ 최신 갱신이 중단된 지표입니다 (마지막 갱신 이후 새 데이터가 확인되지 않음)"


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_jp_unemployment(start_date: str = DEFAULT_START_DATE) -> pd.DataFrame:
    """일본 실업률 (FRED, LRUN64TTJPM156N)."""
    return fetch_fred_series("LRUN64TTJPM156N", start_date)


def fetch_jp_cpi(start_date: str = DEFAULT_START_DATE):
    """일본 소비자물가지수(CPI).
    1순위: FRED JPNCPIALLMINMEI(월별 CPI 지수) / 갱신이 끊겼으면
    2순위: FRED JPNPCPIPCPPPT(IMF 제공, 연간 물가상승률(%), 미래 추정치 포함)로 대체.
    반환값: (DataFrame, note)
    """
    df = fetch_fred_series("JPNCPIALLMINMEI", start_date)
    if not df.empty and not is_data_stale(df):
        return df, "출처: FRED JPNCPIALLMINMEI (월별 CPI 지수)"

    fallback = fetch_fred_series("JPNPCPIPCPPPT", start_date)
    if not fallback.empty:
        # IMF 추정치는 미래 연도(예측치)까지 포함되어 있으므로 오늘 이후 데이터는 제외
        today = pd.Timestamp(datetime.now().date())
        fallback = fallback[fallback["date"] <= today].reset_index(drop=True)
        return fallback, (
            "⚠️ 최신 갱신 중단된 지표(월별 공식 CPI, JPNCPIALLMINMEI)라서 "
            "IMF 제공 연간 물가상승률(%) 시리즈로 대체 표시합니다. 월별이 아닌 연간 데이터입니다."
        )

    return df, "⚠️ 최신 갱신이 중단된 지표입니다 (마지막 갱신 이후 새 데이터가 확인되지 않음)"


# --- 5. 쉬운 설명 문구 (기준금리 결정에 영향 주는 보조지표 옆에 표시) -------------

INDICATOR_EXPLAINERS = {
    "실업률": "일할 의사가 있는 사람 중 일자리를 못 구한 비율. 낮을수록 경기가 좋다는 신호예요.",
    "CPI": "소비자물가지수. 우리가 실제로 사는 물건과 서비스의 평균 가격 수준으로, 전년 대비 상승폭이 크면 물가가 많이 올랐다는 뜻이에요.",
    "기준금리": "중앙은행이 시중 금리의 기준으로 정하는 금리. 올리면 대출이자가 비싸져 돈이 덜 풀리고(물가를 누르는 효과), 내리면 반대예요.",
}


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

    jp_rate = fetch_jp_policy_rate("2025-01-01")
    if not jp_rate.empty:
        st.metric("일본 기준금리 (콜금리 대체)", f"{jp_rate.iloc[-1]['value']:.2f}%")
        st.caption(JP_POLICY_RATE_NOTE)

    st.divider()
    section_label("🌍 환율 (달러 기준 크로스환율)")
    fx_specs = [
        ("엔/달러 환율", fetch_fred_series("DEXJPUS", "2025-01-01"), "엔", 2),
        ("위안/달러 환율", fetch_fred_series("DEXCHUS", "2025-01-01"), "위안", 3),
        ("유로/달러 환율 (EUR/USD)", fetch_eur_per_usd("2025-01-01"), "", 4),
        ("달러인덱스 (Broad)", fetch_fred_series("DTWEXBGS", "2025-01-01"), "", 2),
    ]
    fx_cols = st.columns(4)
    for col, (label, df, unit, decimals) in zip(fx_cols, fx_specs):
        with col:
            if df.empty:
                st.metric(label, "일시적으로 데이터를 가져올 수 없습니다")
            else:
                latest, prev, diff = pct_change_over(df, 1)
                st.metric(label, f"{latest:,.{decimals}f}{unit}", f"{diff:+.{decimals}f}")

    section_label("📈 주요 지수")
    index_cols = st.columns(4)
    for col, (label, ticker) in zip(index_cols, STOCK_INDEX_TICKERS.items()):
        with col:
            df = fetch_yf_series(ticker)
            if df.empty:
                st.metric(label, "일시적으로 데이터를 가져올 수 없습니다")
            else:
                latest, prev, diff = pct_change_over(df, 1)
                st.metric(label, f"{latest:,.2f}", f"{diff:+,.2f}")

    section_label("🏢 한국 주요 종목")
    kr_stock_rows = []
    for label, ticker in KR_STOCK_TICKERS.items():
        df = fetch_yf_series(ticker)
        if df.empty:
            kr_stock_rows.append({"종목": label, "현재가": "일시적으로 데이터를 가져올 수 없습니다", "전일대비(%)": None})
            continue
        latest, prev, diff = pct_change_over(df, 1)
        pct = (diff / prev * 100) if prev else None
        kr_stock_rows.append({
            "종목": label, "현재가": round(latest, 1),
            "전일대비(%)": round(pct, 2) if pct is not None else None,
        })
    st.dataframe(pd.DataFrame(kr_stock_rows), use_container_width=True, hide_index=True)

    section_label("🏢 미국 주요 종목")
    us_stock_rows = []
    for label, ticker in US_STOCK_TICKERS.items():
        df = fetch_yf_series(ticker)
        if df.empty:
            us_stock_rows.append({"종목": label, "현재가": "일시적으로 데이터를 가져올 수 없습니다", "전일대비(%)": None})
            continue
        latest, prev, diff = pct_change_over(df, 1)
        pct = (diff / prev * 100) if prev else None
        us_stock_rows.append({
            "종목": label, "현재가": round(latest, 2),
            "전일대비(%)": round(pct, 2) if pct is not None else None,
        })
    st.dataframe(pd.DataFrame(us_stock_rows), use_container_width=True, hide_index=True)

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

    # [확장] 새로 추가된 환율/기준금리/실업률 지표도 같은 표에 함께 표시
    extra_fred_series = {
        "엔/달러 환율": "DEXJPUS",
        "위안/달러 환율": "DEXCHUS",
        "달러인덱스": "DTWEXBGS",
        "일본 기준금리 (콜금리 대체)": JP_POLICY_RATE_SERIES,
        "한국 실업률": "LRHUTTTTKRM156S",
        "일본 실업률": "LRUN64TTJPM156N",
    }
    for label, series_id in extra_fred_series.items():
        df = fetch_fred_series(series_id, "2025-01-01")
        latest, past, diff = pct_change_over(df, 7)
        if latest is not None:
            rows.append({"지표": label, "현재값": round(latest, 3), "1주일 전": round(past, 3), "변화": round(diff, 3)})

    eur_df = fetch_eur_per_usd("2025-01-01")
    latest, past, diff = pct_change_over(eur_df, 7)
    if latest is not None:
        rows.append({"지표": "유로/달러 환율 (EUR/USD)", "현재값": round(latest, 4), "1주일 전": round(past, 4), "변화": round(diff, 4)})

    kr_cpi_week_df, kr_cpi_week_note = fetch_kr_cpi()
    latest, past, diff = pct_change_over(kr_cpi_week_df, 7)
    if latest is not None:
        rows.append({"지표": "한국 CPI (총지수)", "현재값": round(latest, 2), "1주일 전": round(past, 2), "변화": round(diff, 2)})

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(
        f"한국 CPI {kr_cpi_week_note} · 일본 CPI는 연간 데이터라 1주일 단위 비교표에서는 제외했습니다 (월간 탭 참고)."
    )

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
    st.subheader("[확장] 글로벌 기준금리 비교")
    six_months_ago_period = (datetime.now() - timedelta(days=180)).strftime("%Y%m")

    section_label("한국 기준금리")
    kr_rate6 = fetch_kr_base_rate(start_period=six_months_ago_period)
    if not kr_rate6.empty:
        st.line_chart(kr_rate6.set_index("date")["value"], color=[ACCENT])
    else:
        st.caption("일시적으로 데이터를 가져올 수 없습니다.")
    st.caption(INDICATOR_EXPLAINERS["기준금리"])

    section_label("일본 기준금리 (콜금리 대체)")
    jp_rate6 = fetch_jp_policy_rate(six_months_ago)
    if not jp_rate6.empty:
        st.line_chart(jp_rate6.set_index("date")["value"], color=[ACCENT])
    else:
        st.caption("일시적으로 데이터를 가져올 수 없습니다.")
    st.caption(JP_POLICY_RATE_NOTE)

    st.divider()
    st.subheader("[확장] 환율 추이 (엔 · 위안 · 유로 · 달러인덱스)")

    for label, series_id in FX_SERIES_EXT.items():
        section_label(label)
        df6 = fetch_fred_series(series_id, six_months_ago)
        if not df6.empty:
            st.line_chart(df6.set_index("date")["value"], color=[ACCENT])
        else:
            st.caption("일시적으로 데이터를 가져올 수 없습니다.")

    section_label("유로/달러 환율 (EUR/USD)")
    eur6 = fetch_eur_per_usd(six_months_ago)
    if not eur6.empty:
        st.line_chart(eur6.set_index("date")["value"], color=[ACCENT])
    else:
        st.caption("일시적으로 데이터를 가져올 수 없습니다.")

    st.divider()
    st.subheader("[확장] 한국 · 일본 보조 경제지표")

    section_label("한국 실업률")
    kr_unemp6 = fetch_kr_unemployment(six_months_ago)
    if not kr_unemp6.empty:
        st.line_chart(kr_unemp6.set_index("date")["value"], color=[ACCENT])
    else:
        st.caption("일시적으로 데이터를 가져올 수 없습니다.")
    st.caption(INDICATOR_EXPLAINERS["실업률"])

    section_label("한국 CPI (한국은행 ECOS, 총지수)")
    kr_cpi_month_df, kr_cpi_month_note = fetch_kr_cpi()
    kr_cpi6 = kr_cpi_month_df[kr_cpi_month_df["date"] >= pd.Timestamp(six_months_ago)]
    if not kr_cpi6.empty:
        st.line_chart(kr_cpi6.set_index("date")["value"], color=[ACCENT])
    else:
        st.caption("일시적으로 데이터를 가져올 수 없습니다.")
    st.caption(f"{INDICATOR_EXPLAINERS['CPI']} ({kr_cpi_month_note})")

    section_label("일본 실업률")
    jp_unemp6 = fetch_jp_unemployment(six_months_ago)
    if not jp_unemp6.empty:
        st.line_chart(jp_unemp6.set_index("date")["value"], color=[ACCENT])
    else:
        st.caption("일시적으로 데이터를 가져올 수 없습니다.")
    st.caption(INDICATOR_EXPLAINERS["실업률"])

    section_label("🇯🇵 일본 CPI ⚠️ 연간(Annual) 데이터 - 월별 아님")
    jp_cpi_df, jp_cpi_note = fetch_jp_cpi()
    if not jp_cpi_df.empty:
        st.line_chart(jp_cpi_df.set_index("date")["value"], color=[ACCENT])
        st.caption(f"⚠️ 이 지표는 다른 차트와 달리 **연간(매년 1개 값)** 데이터입니다. {jp_cpi_note}")
    else:
        st.caption("일시적으로 데이터를 가져올 수 없습니다.")
    st.caption(INDICATOR_EXPLAINERS["CPI"])

    st.divider()
    st.subheader("[확장] 주요 지수 추이")
    for label, ticker in STOCK_INDEX_TICKERS.items():
        section_label(label)
        df = fetch_yf_series(ticker)
        df6 = df[df["date"] >= pd.Timestamp(six_months_ago)] if not df.empty else df
        if not df6.empty:
            st.line_chart(df6.set_index("date")["value"], color=[ACCENT])
        else:
            st.caption("일시적으로 데이터를 가져올 수 없습니다.")

    with st.expander("🏢 주요 종목 6개월 추이 보기"):
        section_label("한국 주요 종목")
        for label, ticker in KR_STOCK_TICKERS.items():
            st.caption(label)
            df = fetch_yf_series(ticker)
            df6 = df[df["date"] >= pd.Timestamp(six_months_ago)] if not df.empty else df
            if not df6.empty:
                st.line_chart(df6.set_index("date")["value"], color=[ACCENT])
            else:
                st.caption("일시적으로 데이터를 가져올 수 없습니다.")

        section_label("미국 주요 종목")
        for label, ticker in US_STOCK_TICKERS.items():
            st.caption(label)
            df = fetch_yf_series(ticker)
            df6 = df[df["date"] >= pd.Timestamp(six_months_ago)] if not df.empty else df
            if not df6.empty:
                st.line_chart(df6.set_index("date")["value"], color=[ACCENT])
            else:
                st.caption("일시적으로 데이터를 가져올 수 없습니다.")

    st.divider()
    with st.expander("🇰🇷 한국 100대 통계지표 전체 보기 (원본 데이터 확인용)"):
        st.dataframe(kr_stats[["CLASS_NAME", "KEYSTAT_NAME", "DATA_VALUE", "CYCLE", "UNIT_NAME"]],
                     use_container_width=True, hide_index=True)
