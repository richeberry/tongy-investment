import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import plotly.graph_objects as go
import anthropic
from duckduckgo_search import DDGS
import requests
from bs4 import BeautifulSoup
import subprocess
import tempfile
import re
import os
import webbrowser
import urllib.parse
from datetime import datetime

# ==========================================
# 0. 페이지 설정
# ==========================================
st.set_page_config(
    page_title="BAYSIA Alpha Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');

    html, body, [class*="css"], [data-testid], button, input, textarea, select, table {
        font-family: 'Pretendard', -apple-system, sans-serif !important;
        font-weight: 300 !important;
        letter-spacing: 0.04em;
    }
    h1, h2, h3, h4, h5, h6,
    [data-testid="stMarkdownContainer"] h1,
    [data-testid="stMarkdownContainer"] h2,
    [data-testid="stMarkdownContainer"] h3 {
        font-family: 'Pretendard', sans-serif !important;
        font-weight: 300 !important;
        letter-spacing: 0.02em;
    }
    strong, b {
        font-weight: 500 !important;
    }

    /* 테이블 구조 스타일만 — 색상은 Streamlit 테마에 위임 */
    [data-testid="stMarkdownContainer"] table {
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
        margin: 12px 0;
    }
    [data-testid="stMarkdownContainer"] th {
        padding: 8px 12px;
        text-align: left;
        border: 1px solid rgba(128,128,128,0.3);
        background-color: rgba(128,128,128,0.15);
        font-weight: 600;
    }
    [data-testid="stMarkdownContainer"] td {
        padding: 7px 12px;
        border: 1px solid rgba(128,128,128,0.2);
        vertical-align: top;
    }
    [data-testid="stMarkdownContainer"] tr:nth-child(even) td {
        background-color: rgba(128,128,128,0.07);
    }
    [data-testid="stMarkdownContainer"] h2 {
        border-bottom: 2px solid rgba(128,128,128,0.3);
        padding-bottom: 6px;
        margin-top: 1.4em;
    }
    [data-testid="stMarkdownContainer"] h3 {
        margin-top: 1em;
    }
    [data-testid="stMarkdownContainer"] blockquote {
        border-left: 4px solid rgba(128,128,200,0.5);
        padding: 8px 16px;
        margin: 12px 0;
        background-color: rgba(128,128,200,0.08);
        border-radius: 0 8px 8px 0;
    }
    [data-testid="stMarkdownContainer"] hr {
        margin: 20px 0;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 1. 사이드바
# ==========================================
with st.sidebar:
    st.title("🤖 BAYSIA Algo-Trader")
    st.caption("Professional AI Investment Assistant")

    # secrets.toml 또는 환경변수에서 자동 로드, 없으면 입력창 표시
    def _load_secret(key: str) -> str:
        try:
            val = st.secrets[key]
        except Exception:
            val = os.environ.get(key, "")
        # ASCII 범위 외 문자(한글 등) 및 공백 제거
        return "".join(c for c in val if ord(c) < 128).strip()

    _api = _load_secret("ANTHROPIC_API_KEY")
    if _api:
        os.environ["ANTHROPIC_API_KEY"] = _api
        st.success("✅ API Key 로드됨", icon="🔑")
    else:
        api_key = st.text_input("Anthropic API Key", type="password", placeholder="sk-ant-...")
        if api_key:
            os.environ["ANTHROPIC_API_KEY"] = "".join(c for c in api_key if ord(c) < 128).strip()

    st.divider()
    st.subheader("📤 내보내기 설정")

    _notion = _load_secret("NOTION_TOKEN")
    if _notion:
        os.environ["NOTION_TOKEN"] = _notion
        st.success("✅ Notion Token 로드됨", icon="📓")
    else:
        notion_token = st.text_input("Notion Token", type="password", placeholder="secret_...")
        if notion_token:
            os.environ["NOTION_TOKEN"] = "".join(c for c in notion_token if ord(c) < 128).strip()

    st.divider()
    st.info("💡 Tip: 'NVDA', '005930.KS', 'BTC-USD' 등 티커를 입력하세요.")

# ==========================================
# 2. 뉴스 수집 (신뢰 소스 기반)
# ==========================================

# 신뢰 소스 목록 (youtube_digest/search.md 참조)
TRUSTED_SITES = [
    "bloomberg.com", "reuters.com", "cnbc.com",
    "marketwatch.com", "seekingalpha.com",
    "hankyung.com", "mk.co.kr",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


def fetch_article_text(url: str, max_chars: int = 1500) -> str:
    """URL에서 기사 본문을 추출합니다."""
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(res.text, "html.parser")
        # 본문 태그 우선 추출
        for tag in soup.find_all(["article", "main", "section"]):
            text = tag.get_text(separator=" ", strip=True)
            if len(text) > 300:
                return text[:max_chars]
        return soup.get_text(separator=" ", strip=True)[:max_chars]
    except Exception:
        return ""


# ==========================================
# 내보내기 함수
# ==========================================

def export_buttons(content: str, filename: str, notion_title: str = None):
    """결과 아래에 내보내기 버튼 3종을 표시합니다."""
    st.divider()
    st.caption("📤 결과 내보내기")
    col1, col2, col3 = st.columns(3)

    # 1. 파일 다운로드
    with col1:
        today = datetime.now().strftime("%Y%m%d_%H%M")
        st.download_button(
            label="⬇️ 파일 다운로드 (.md)",
            data=content.encode("utf-8"),
            file_name=f"{filename}_{today}.md",
            mime="text/markdown",
            key=f"dl_{filename}",
        )

    # 2. Notion 저장
    with col2:
        if st.button("📓 Notion 저장", key=f"notion_{filename}"):
            token = os.environ.get("NOTION_TOKEN", "")
            if not token:
                st.error("사이드바에 Notion Token을 입력하세요.")
            else:
                with st.spinner("Notion 저장 중..."):
                    url, err = _save_to_notion(notion_title or filename, content, token)
                if url:
                    st.success("저장 완료!")
                    st.markdown(f"[Notion에서 보기]({url})")
                elif err:
                    st.error(err)
                    if "shared" in err or "find page" in err:
                        st.info(
                            "**Notion 연결 방법:**\n"
                            "1. Notion에서 저장 대상 페이지 열기\n"
                            "2. 우측 상단 `...` → `연결 (Connections)` 클릭\n"
                            "3. 내 Integration 검색 후 추가\n"
                            "4. 다시 저장 시도"
                        )

    # 3. 이메일 전송 — popover 팝업 (기본 메일 앱)
    with col3:
        with st.popover("📧 이메일로 보내기"):
            st.caption("받는 이메일을 입력하면 메일 앱이 열립니다")
            to_addr = st.text_input("받는 이메일", placeholder="to@gmail.com", key=f"to_{filename}")
            if st.button("📨 메일 앱에서 열기", key=f"send_{filename}", type="primary"):
                if not to_addr:
                    st.error("이메일 주소를 입력하세요.")
                else:
                    subject = urllib.parse.quote(f"[BAYSIA] {notion_title or filename}")
                    # 본문은 앞 2000자만 (mailto URL 길이 제한)
                    body = urllib.parse.quote(content[:2000] + "\n\n--- 전체 내용은 파일 다운로드를 이용하세요 ---")
                    mailto_url = f"mailto:{to_addr}?subject={subject}&body={body}"
                    st.markdown(
                        f'<meta http-equiv="refresh" content="0;url={mailto_url}">',
                        unsafe_allow_html=True,
                    )
                    st.success("✅ 메일 앱이 열립니다. 전체 내용은 파일 다운로드를 이용하세요.")


def _md_to_notion_blocks(content: str) -> list:
    """마크다운을 Notion 블록 배열로 변환합니다."""
    blocks = []

    def _rt(t: str) -> list:
        """인라인 **bold**, *italic*, `code` → Notion rich_text annotations"""
        result = []
        pattern = r'\*\*(.*?)\*\*|\*(.*?)\*|`(.*?)`|([^*`\n]+)'
        for m in re.finditer(pattern, t):
            if m.group(1):
                result.append({"type": "text", "text": {"content": m.group(1)[:1990]},
                               "annotations": {"bold": True}})
            elif m.group(2):
                result.append({"type": "text", "text": {"content": m.group(2)[:1990]},
                               "annotations": {"italic": True}})
            elif m.group(3):
                result.append({"type": "text", "text": {"content": m.group(3)[:1990]},
                               "annotations": {"code": True}})
            elif m.group(4):
                result.append({"type": "text", "text": {"content": m.group(4)[:1990]}})
        return result if result else [{"type": "text", "text": {"content": t[:1990]}}]

    for line in content.splitlines():
        s = line.strip()
        if not s:
            continue

        # 구분선
        if re.match(r'^[-=]{3,}$', s):
            blocks.append({"object": "block", "type": "divider", "divider": {}})

        # 제목
        elif s.startswith("#### "):
            blocks.append({"object": "block", "type": "heading_3",
                           "heading_3": {"rich_text": _rt(s[5:])}})
        elif s.startswith("### "):
            blocks.append({"object": "block", "type": "heading_3",
                           "heading_3": {"rich_text": _rt(s[4:])}})
        elif s.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2",
                           "heading_2": {"rich_text": _rt(s[3:])}})
        elif s.startswith("# "):
            blocks.append({"object": "block", "type": "heading_1",
                           "heading_1": {"rich_text": _rt(s[2:])}})

        # 인용
        elif s.startswith("> "):
            blocks.append({"object": "block", "type": "quote",
                           "quote": {"rich_text": _rt(s[2:])}})

        # 불릿
        elif re.match(r'^[-*] ', s):
            blocks.append({"object": "block", "type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": _rt(s[2:])}})

        # 번호 목록
        elif re.match(r'^\d+\. ', s):
            text = re.sub(r'^\d+\. ', '', s)
            blocks.append({"object": "block", "type": "numbered_list_item",
                           "numbered_list_item": {"rich_text": _rt(text)}})

        # 테이블 구분선 스킵
        elif re.match(r'^\|[\s\-:|]+\|', s):
            continue

        # 테이블 행 → callout으로 보기 좋게
        elif s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|") if c.strip()]
            text = "  ·  ".join(cells)
            blocks.append({"object": "block", "type": "paragraph",
                           "paragraph": {"rich_text": _rt(text)}})

        # 일반 단락
        else:
            rt = _rt(s)
            if rt:
                blocks.append({"object": "block", "type": "paragraph",
                               "paragraph": {"rich_text": rt}})

    return blocks


def _save_to_notion(title: str, content: str, token: str) -> tuple[str, str]:
    """Notion에 마크다운 내용을 저장합니다. (url, error) 반환"""
    PARENT_PAGE_ID = "318c1b7041be80c4b9e5f3064ce7aaa4"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    today = datetime.now().strftime("%Y-%m-%d")
    page_title = f"{title} — {today}"
    blocks = _md_to_notion_blocks(content)

    payload = {
        "parent": {"page_id": PARENT_PAGE_ID},
        "properties": {"title": {"title": [{"text": {"content": page_title}}]}},
        "children": blocks[:100],
    }

    try:
        res = requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload, timeout=15)
        if res.ok:
            page_url = res.json().get("url", "")
            # 블록이 100개 초과면 이어서 append
            if len(blocks) > 100:
                page_id = res.json().get("id", "")
                for i in range(100, len(blocks), 100):
                    requests.patch(
                        f"https://api.notion.com/v1/blocks/{page_id}/children",
                        headers=headers,
                        json={"children": blocks[i:i+100]},
                        timeout=15,
                    )
            return page_url, ""
        err = res.json().get("message", res.text)
        return "", f"Notion API 오류: {err}"
    except Exception as e:
        return "", f"연결 오류: {e}"



MACRO_TICKERS = {
    # ── 미국 주요 지수
    "S&P 500":      ("^GSPC",    "미국지수"),
    "나스닥":        ("^IXIC",    "미국지수"),
    "다우존스":      ("^DJI",     "미국지수"),
    "러셀 2000":    ("^RUT",     "미국지수"),
    # ── 글로벌 지수
    "니케이 225":   ("^N225",    "글로벌지수"),
    "항셍":         ("^HSI",     "글로벌지수"),
    "KOSPI":        ("^KS11",    "글로벌지수"),
    "FTSE 100":     ("^FTSE",    "글로벌지수"),
    "DAX":          ("^GDAXI",   "글로벌지수"),
    # ── 공포/변동성
    "VIX":          ("^VIX",     "변동성"),
    "VVIX":         ("^VVIX",    "변동성"),   # VIX의 변동성 (시장 공포 2단계)
    # ── 미국 금리 (채권 수익률)
    "미국 2년물":   ("^IRX",     "금리"),
    "미국 10년물":  ("^TNX",     "금리"),
    "미국 30년물":  ("^TYX",     "금리"),
    # ── 채권 ETF (신용 시장 온도)
    "TLT (장기채)": ("TLT",      "채권ETF"),   # iShares 20Y Treasury
    "HYG (하이일드)": ("HYG",    "채권ETF"),   # 정크본드 ETF — 리스크 선호도 지표
    # ── 달러 / 환율
    "달러 인덱스":  ("DX-Y.NYB", "환율"),
    "EUR/USD":      ("EURUSD=X", "환율"),
    "USD/JPY":      ("JPY=X",    "환율"),
    "USD/KRW":      ("KRW=X",    "환율"),
    "USD/CNY":      ("CNY=X",    "환율"),
    # ── 원자재
    "금 (Gold)":    ("GC=F",     "원자재"),
    "은 (Silver)":  ("SI=F",     "원자재"),
    "WTI 원유":     ("CL=F",     "원자재"),
    "브렌트유":     ("BZ=F",     "원자재"),
    "천연가스":     ("NG=F",     "원자재"),
    "구리":         ("HG=F",     "원자재"),
    # ── 암호화폐
    "BTC":          ("BTC-USD",  "크립토"),
    "ETH":          ("ETH-USD",  "크립토"),
    # ── 미국 섹터 ETF (섹터 온도계)
    "XLK (기술)":   ("XLK",      "섹터ETF"),
    "XLF (금융)":   ("XLF",      "섹터ETF"),
    "XLE (에너지)": ("XLE",      "섹터ETF"),
    "XLV (헬스케어)": ("XLV",    "섹터ETF"),
    "XLI (산업재)": ("XLI",      "섹터ETF"),
    "XLB (소재)":   ("XLB",      "섹터ETF"),
}


def get_macro_data() -> dict:
    """
    yfinance로 주요 거시경제 지표를 수집합니다.
    반환: {이름: {value, change, ticker, category}}
    """
    result = {}
    for name, (ticker, category) in MACRO_TICKERS.items():
        try:
            hist = yf.Ticker(ticker).history(period="5d")
            if hist.empty or len(hist) < 2:
                continue
            curr = hist["Close"].iloc[-1]
            prev = hist["Close"].iloc[-2]
            chg  = (curr - prev) / prev * 100
            result[name] = {"value": curr, "change": chg, "ticker": ticker, "category": category}
        except Exception:
            pass

    # 수익률 커브 스프레드 계산 (10년 - 2년 → 역전 시 경기침체 신호)
    if "미국 10년물" in result and "미국 2년물" in result:
        spread = result["미국 10년물"]["value"] - result["미국 2년물"]["value"]
        result["10Y-2Y 스프레드"] = {
            "value": round(spread, 3),
            "change": 0.0,
            "ticker": "-",
            "category": "금리",
        }

    return result


def format_macro_summary(macro: dict) -> str:
    """거시경제 데이터를 Claude 프롬프트용 텍스트로 포맷합니다."""
    # 카테고리별로 그룹화
    groups: dict[str, list[str]] = {}
    for name, d in macro.items():
        cat = d.get("category", "기타")
        groups.setdefault(cat, [])
        sign = "+" if d["change"] >= 0 else ""
        groups[cat].append(f"  - {name}: {d['value']:.2f} ({sign}{d['change']:.2f}%)")

    lines = ["## 실시간 거시경제 지표"]
    order = ["미국지수", "글로벌지수", "변동성", "금리", "채권ETF", "환율", "원자재", "크립토", "섹터ETF"]
    for cat in order:
        if cat in groups:
            lines.append(f"\n### {cat}")
            lines.extend(groups[cat])
    return "\n".join(lines)


def collect_news(query: str, max_results: int = 15) -> str:
    """
    DuckDuckGo 실시간 뉴스 + yfinance 뉴스로 최신 해외 뉴스를 수집합니다.
    소스 고정 없이 검색어 기반 수집. 최근 1주일 우선.
    """
    all_articles = []
    seen_titles = set()

    # 검색어 변형: 다각도로 최신 뉴스 수집
    variants = [
        query,
        f"{query} market news",
        f"{query} financial analysis",
        f"{query} economy outlook",
        f"{query} price forecast",
    ]

    try:
        with DDGS() as ddgs:
            for sq in variants:
                try:
                    # timelimit="w" : 최근 1주일 뉴스 우선
                    results = list(ddgs.news(sq, max_results=8, region="us-en", timelimit="w"))
                    if not results:
                        results = list(ddgs.news(sq, max_results=8, region="us-en"))
                except Exception:
                    results = []

                for r in results:
                    title = r.get("title", "")
                    if not title or title in seen_titles:
                        continue
                    seen_titles.add(title)
                    body = r.get("body", "") or r.get("excerpt", "")
                    href = r.get("url", "") or r.get("href", "")
                    source = r.get("source", "")
                    date = r.get("date", "")
                    if len(body) < 300 and href:
                        body = fetch_article_text(href) or body
                    if body:
                        all_articles.append(
                            f"[{title}] — {source} ({date})\n{body[:1200]}"
                        )
                    if len(all_articles) >= max_results:
                        break
                if len(all_articles) >= max_results:
                    break
    except Exception as e:
        return f"뉴스 수집 실패: {e}"

    # yfinance 뉴스 보완 (티커처럼 보이는 단어가 있으면)
    words = query.upper().split()
    for word in words[:3]:
        if 2 <= len(word) <= 6 and word.isalpha():
            try:
                yfnews = yf.Ticker(word).news or []
                for n in yfnews[:5]:
                    title = n.get("title", "")
                    if not title or title in seen_titles:
                        continue
                    seen_titles.add(title)
                    pub = datetime.fromtimestamp(n.get("providerPublishTime", 0)).strftime("%Y-%m-%d") if n.get("providerPublishTime") else ""
                    publisher = n.get("publisher", "")
                    all_articles.append(
                        f"[{title}] — {publisher} ({pub})\n{n.get('link', '')}"
                    )
            except Exception:
                pass

    if not all_articles:
        return "수집된 뉴스가 없습니다."

    return "\n\n---\n\n".join(all_articles[:max_results])


# ==========================================
# 3. 티커 정규화
# ==========================================
_TICKER_ALIASES = {
    # Google / Alphabet
    "GOOGLE": "GOOGL", "ALPHABET": "GOOGL",
    # Meta
    "FACEBOOK": "META", "FB": "META",
    # 암호화폐
    "BITCOIN": "BTC-USD", "BTC": "BTC-USD",
    "ETHEREUM": "ETH-USD", "ETH": "ETH-USD",
    "SOLANA": "SOL-USD", "SOL": "SOL-USD",
    "RIPPLE": "XRP-USD", "XRP": "XRP-USD",
    # 한국 대표 종목
    "삼성전자": "005930.KS", "삼성": "005930.KS",
    "카카오": "035720.KS", "네이버": "035420.KS", "NAVER": "035420.KS",
    "SK하이닉스": "000660.KS", "하이닉스": "000660.KS",
    "현대차": "005380.KS", "기아": "000270.KS",
    # 지수
    "SP500": "^GSPC", "S&P500": "^GSPC", "S&P": "^GSPC",
    "NASDAQ": "^IXIC", "DOW": "^DJI", "VIX": "^VIX",
    # 원자재
    "GOLD": "GC=F", "SILVER": "SI=F",
    "OIL": "CL=F", "WTI": "CL=F", "CRUDE": "CL=F",
    # 기타
    "BERKSHIRE": "BRK-B", "WARREN": "BRK-B",
}

def normalize_ticker(raw: str) -> str:
    """회사명이나 별칭을 yfinance 티커로 변환합니다."""
    upper = raw.strip().upper()
    return _TICKER_ALIASES.get(upper, upper)


# ==========================================
# 4. 퀀트 엔진
# ==========================================
class QuantEngine:
    def get_data(self, ticker):
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="1y")

            # yfinance MultiIndex 컬럼 처리 (최신 버전 대응)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            if df.empty or len(df) < 10:
                st.error(f"'{ticker}' 데이터가 없습니다. 티커를 확인하세요. (예: NVDA, AAPL, BTC-USD, 005930.KS)")
                return None

            close = df['Close'].squeeze()
            high  = df['High'].squeeze()
            low   = df['Low'].squeeze()

            curr_price = float(close.iloc[-1])
            prev_price = float(close.iloc[-2])
            change_pct = (curr_price - prev_price) / prev_price * 100

            # 기술적 지표 — 클래스 API 사용 (함수 API보다 안정적)
            try:
                df['RSI'] = ta.momentum.RSIIndicator(close=close, window=14).rsi()
            except Exception:
                df['RSI'] = float('nan')

            try:
                df['SMA_50']  = ta.trend.SMAIndicator(close=close, window=50).sma_indicator()
                df['SMA_200'] = ta.trend.SMAIndicator(close=close, window=200).sma_indicator()
            except Exception:
                df['SMA_50'] = float('nan')
                df['SMA_200'] = float('nan')

            try:
                bb = ta.volatility.BollingerBands(close=close, window=20, window_dev=2)
                df['bb_upper'] = bb.bollinger_hband()
                df['bb_lower'] = bb.bollinger_lband()
            except Exception:
                df['bb_upper'] = float('nan')
                df['bb_lower'] = float('nan')

            try:
                df['ATR'] = ta.volatility.AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range()
            except Exception:
                df['ATR'] = float('nan')

            info = {}
            try:
                info = stock.info or {}
            except Exception:
                pass

            import math

            def _f(key, mul=1, digits=2):
                v = info.get(key)
                if v is None: return None
                try: return round(float(v) * mul, digits)
                except: return None

            def _pct(key): return _f(key, 100, 1)

            week52_high = info.get('fiftyTwoWeekHigh')
            week52_low  = info.get('fiftyTwoWeekLow')
            position_52w = None
            if week52_high and week52_low and (week52_high - week52_low) > 0:
                position_52w = round((curr_price - week52_low) / (week52_high - week52_low) * 100, 1)

            ma50  = df['SMA_50'].iloc[-1]
            ma200 = df['SMA_200'].iloc[-1]
            atr   = df['ATR'].iloc[-1]

            # 최신 뉴스 헤드라인
            recent_news = []
            try:
                for n in (stock.news or [])[:6]:
                    title = n.get("title", "")
                    pub = n.get("publisher", "")
                    if title:
                        recent_news.append(f"- [{pub}] {title}")
            except Exception:
                pass

            # 최근 실적 (분기)
            earnings_hist = []
            try:
                eq = stock.quarterly_earnings
                if eq is not None and not eq.empty:
                    for idx, row in eq.tail(4).iterrows():
                        eps_actual  = row.get("Earnings", "")
                        eps_est     = row.get("Estimate", "")
                        earnings_hist.append(f"{idx}: 실제 {eps_actual} / 예상 {eps_est}")
            except Exception:
                pass

            return {
                "df": df, "info": info,
                # 가격
                "price": curr_price, "change": change_pct,
                "52w_high": week52_high, "52w_low": week52_low, "52w_position": position_52w,
                "target": info.get('targetMeanPrice'),
                "target_low": info.get('targetLowPrice'),
                "target_high": info.get('targetHighPrice'),
                # 기술적
                "rsi": df['RSI'].iloc[-1] if not math.isnan(df['RSI'].iloc[-1]) else 50.0,
                "ma_50": float(ma50) if not math.isnan(float(ma50)) else None,
                "ma_200": float(ma200) if not math.isnan(float(ma200)) else None,
                "ma_signal": "골든크로스" if (not math.isnan(float(ma50)) and not math.isnan(float(ma200)) and ma50 > ma200) else "데드크로스",
                "bb_upper": float(df['bb_upper'].iloc[-1]),
                "bb_lower": float(df['bb_lower'].iloc[-1]),
                "atr": float(atr) if not math.isnan(float(atr)) else curr_price * 0.02,
                # 밸류에이션
                "pe": _f('forwardPE'), "trailing_pe": _f('trailingPE'),
                "peg": _f('pegRatio'), "pb": _f('priceToBook'),
                "ps": _f('priceToSalesTrailing12Months'),
                "ev_ebitda": _f('enterpriseToEbitda'),
                "ev_revenue": _f('enterpriseToRevenue'),
                "market_cap": info.get('marketCap'),
                # 수익성
                "gross_margin": _pct('grossMargins'),
                "operating_margin": _pct('operatingMargins'),
                "net_margin": _pct('profitMargins'),
                "roe": _pct('returnOnEquity'),
                "roa": _pct('returnOnAssets'),
                # 성장
                "revenue_growth": _pct('revenueGrowth'),
                "earnings_growth": _pct('earningsGrowth'),
                "revenue_growth_q": _pct('revenueQuarterlyGrowth'),
                "earnings_growth_q": _pct('earningsQuarterlyGrowth'),
                "total_revenue": info.get('totalRevenue'),
                "ebitda": info.get('ebitda'),
                # EPS
                "eps_trailing": _f('trailingEps'), "eps_forward": _f('forwardEps'),
                # 재무건전성
                "total_cash": info.get('totalCash'),
                "total_debt": info.get('totalDebt'),
                "de_ratio": _f('debtToEquity'),
                "current_ratio": _f('currentRatio'),
                "quick_ratio": _f('quickRatio'),
                "free_cashflow": info.get('freeCashflow'),
                "operating_cashflow": info.get('operatingCashflow'),
                # 배당
                "dividend_yield": _pct('dividendYield'),
                "payout_ratio": _pct('payoutRatio'),
                # 애널리스트
                "recommendation": info.get('recommendationKey', '').upper(),
                "recommendation_mean": _f('recommendationMean'),
                "num_analysts": info.get('numberOfAnalystOpinions'),
                # 심리/소유구조
                "beta": _f('beta'),
                "short_float": _pct('shortPercentOfFloat'),
                "short_ratio": _f('shortRatio'),
                "institution_pct": _pct('heldPercentInstitutions'),
                "insider_pct": _pct('heldPercentInsiders'),
                # 기업 기본정보
                "sector": info.get('sector', ''),
                "industry": info.get('industry', ''),
                "employees": info.get('fullTimeEmployees'),
                # 뉴스 / 실적
                "recent_news": recent_news,
                "earnings_hist": earnings_hist,
            }
        except Exception as e:
            st.error(f"데이터 로드 오류 ({type(e).__name__}): {e}")
            return None


# ==========================================
# 4. AI 애널리스트
# ==========================================
class AIAnalyst:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    def _ask(self, prompt: str, max_tokens: int = 2000) -> str:
        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def generate_report(self, ticker, p, news):
        def _n(v, suffix="", na="N/A"):
            return f"{v}{suffix}" if v is not None else na
        def _mc(v):
            if not v: return "N/A"
            if v >= 1e12: return f"${v/1e12:.2f}T"
            if v >= 1e9:  return f"${v/1e9:.2f}B"
            if v >= 1e6:  return f"${v/1e6:.2f}M"
            return f"${v:,.0f}"

        stop_loss  = p['price'] - 2 * p['atr']
        ma50_diff  = round((p['price'] - p['ma_50'])  / p['ma_50']  * 100, 1) if p['ma_50']  else None
        ma200_diff = round((p['price'] - p['ma_200']) / p['ma_200'] * 100, 1) if p['ma_200'] else None
        upside     = round((p['target'] - p['price']) / p['price'] * 100, 1) if p['target'] and p['price'] else None

        news_headlines = "\n".join(p.get('recent_news', [])) or "없음"
        earnings_str   = "\n".join(p.get('earnings_hist', [])) or "없음"

        prompt = f"""당신은 월가 헤지펀드의 수석 애널리스트입니다.
아래 종합 데이터와 최신 뉴스를 바탕으로 전문적인 투자 분석 리포트를 작성하세요.

## 기업 개요
- 종목: {ticker} | 섹터: {p['sector']} | 산업: {p['industry']}
- 시가총액: {_mc(p['market_cap'])} | 직원수: {_n(p['employees'],'명')}

## 가격 / 기술적 지표
- 현재가: {p['price']:.2f} (전일비 {p['change']:+.2f}%)
- 52주 고가: {_n(p['52w_high'],'$')} / 저가: {_n(p['52w_low'],'$')} / 위치: {_n(p['52w_position'],'%')}
- 애널리스트 목표가: {_n(p['target'],'$')} (평균) / 상단: {_n(p['target_high'],'$')} / 하단: {_n(p['target_low'],'$')} | 상승여력: {_n(upside,'%')}
- RSI(14): {p['rsi']:.1f} | 50MA 대비: {_n(ma50_diff,'%')} | 200MA 대비: {_n(ma200_diff,'%')} | {p['ma_signal']}
- 볼린저 상단: {p['bb_upper']:.2f} / 하단: {p['bb_lower']:.2f} | ATR: {p['atr']:.2f} → 손절선: {stop_loss:.2f}
- Beta: {_n(p['beta'])}

## 밸류에이션
- Forward P/E: {_n(p['pe'])} | Trailing P/E: {_n(p['trailing_pe'])} | PEG: {_n(p['peg'])}
- P/B: {_n(p['pb'])} | P/S: {_n(p['ps'])} | EV/EBITDA: {_n(p['ev_ebitda'])} | EV/Revenue: {_n(p['ev_revenue'])}

## 수익성 (Profitability)
- 매출총이익률: {_n(p['gross_margin'],'%')} | 영업이익률: {_n(p['operating_margin'],'%')} | 순이익률: {_n(p['net_margin'],'%')}
- ROE: {_n(p['roe'],'%')} | ROA: {_n(p['roa'],'%')}
- 총매출: {_mc(p['total_revenue'])} | EBITDA: {_mc(p['ebitda'])}

## 성장성
- 매출 성장 YoY: {_n(p['revenue_growth'],'%')} | QoQ: {_n(p['revenue_growth_q'],'%')}
- EPS 성장 YoY: {_n(p['earnings_growth'],'%')} | QoQ: {_n(p['earnings_growth_q'],'%')}
- EPS Trailing: {_n(p['eps_trailing'],'$')} | EPS Forward: {_n(p['eps_forward'],'$')}

## 최근 분기 실적 (EPS)
{earnings_str}

## 재무건전성
- 현금: {_mc(p['total_cash'])} | 부채: {_mc(p['total_debt'])} | D/E: {_n(p['de_ratio'])}
- 유동비율: {_n(p['current_ratio'])} | 당좌비율: {_n(p['quick_ratio'])}
- FCF: {_mc(p['free_cashflow'])} | 영업CF: {_mc(p['operating_cashflow'])}

## 배당
- 배당수익률: {_n(p['dividend_yield'],'%')} | 배당성향: {_n(p['payout_ratio'],'%')}

## 애널리스트 / 시장 심리
- 등급: {p['recommendation']} (평균점수 {_n(p['recommendation_mean'])}/5.0) | 커버리지: {_n(p['num_analysts'],'명')}
- 공매도 비율: {_n(p['short_float'],'%')} | Short Ratio: {_n(p['short_ratio'],'일')}
- 기관보유: {_n(p['institution_pct'],'%')} | 내부자보유: {_n(p['insider_pct'],'%')}

## yfinance 최신 뉴스 헤드라인
{news_headlines}

## 수집된 최신 뉴스
{news[:3500]}

---
아래 형식으로 작성하세요 (Markdown):

## {ticker} 종합 투자 분석 리포트

> **한 줄 핵심 요약** (지금 이 종목의 상황을 한 문장으로)

---

### 📊 핵심 지표 요약

| 구분 | 지표 | 값 | 평가 |
|------|------|----|------|
| 💰 가격 | 현재가 / 52주 위치 | {p['price']:.2f} / {_n(p['52w_position'],'%')} | |
| 💰 가격 | 목표가 (상승여력) | {_n(p['target'],'$')} ({_n(upside,'%')}) | |
| 📈 기술적 | RSI / MA신호 | {p['rsi']:.1f} / {p['ma_signal']} | |
| 💵 밸류 | Fwd P/E / PEG / EV/EBITDA | {_n(p['pe'])} / {_n(p['peg'])} / {_n(p['ev_ebitda'])} | |
| 💹 수익성 | 영업이익률 / ROE | {_n(p['operating_margin'],'%')} / {_n(p['roe'],'%')} | |
| 📊 성장 | 매출YoY / EPS YoY | {_n(p['revenue_growth'],'%')} / {_n(p['earnings_growth'],'%')} | |
| 🏦 재무 | D/E / FCF | {_n(p['de_ratio'])} / {_mc(p['free_cashflow'])} | |
| 🎭 심리 | 공매도 / 기관보유 | {_n(p['short_float'],'%')} / {_n(p['institution_pct'],'%')} | |

평가 칸을 채워주세요 (예: 저평가/고평가/양호/위험/주목 등).

---

### 🏢 비즈니스 & 펀더멘털 분석
- **사업 경쟁력**: 이 기업이 속한 섹터({p['sector']})에서의 위치, 해자(moat), 성장 드라이버
- **수익성 분석**: 이익률 추이, ROE/ROA 수준이 업계 대비 어떤지
- **밸류에이션**: 현재 멀티플이 역사적 평균 대비 비싼지 싼지, 성장률 감안 시 적정가
- **재무 건전성**: 부채 수준, 현금흐름으로 자체 성장 가능한지

### 📈 기술적 분석
- RSI, MA 배열, 볼린저밴드 위치 해석
- 52주 위치 기반 현재 국면 (바닥/상승/과열/조정)
- 핵심 지지/저항선

### 📰 시장 센티먼트 & 뉴스 분석
- 최근 주요 뉴스 호재/악재 요약
- 기관 및 내부자 동향
- 공매도 비율이 의미하는 것

### ⚠️ 리스크 요인
1. (구체적으로)
2. (구체적으로)
3. (구체적으로)

### ⏱️ 투자 판단

| 구분 | 내용 |
|------|------|
| 단기 (1~3개월) | |
| 중기 (3~12개월) | |
| 핵심 카탈리스트 | |
| 매수 고려 구간 | |
| 목표주가 | |
| 손절선 | {stop_loss:.2f} (ATR×2 기반) |
| **최종 판단** | 🟢강력매수 / 🟡분할매수 / ⚪관망 / 🔴매도 |

---
⚠️ 본 리포트는 참고용입니다. 투자 책임은 본인에게 있습니다."""

        return self._ask(prompt, max_tokens=4000)

    def macro_briefing(self, news: str, macro_data: dict = None, query: str = "") -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        macro_text = format_macro_summary(macro_data) if macro_data else ""
        focus_line = f"\n**분석 포커스: '{query}' 관련 내용을 중심으로 분석하세요.**\n" if query else ""

        prompt = f"""당신은 글로벌 매크로 전략가입니다.
아래 실시간 거시경제 지표와 뉴스를 종합하여 오늘의 글로벌 증시 브리핑을 작성하세요.
{focus_line}
{macro_text}

## 수집된 뉴스 ({today})
{news[:4000]}

---
아래 형식으로 상세하게 작성하세요 (Notion 스타일 Markdown):

# 글로벌 증시 브리핑 — {today}
**카테고리:** 주식 / 투자 / AI | **소스:** Bloomberg, Reuters, CNBC, SeekingAlpha

---

## 🚨 핵심 이슈 (Top 3)
각 이슈마다:
- **이슈명**
- 배경: (2~3줄)
- 투자 시사점: (구체적으로)

---

## 🌎 주요 지수 동향
- 미국 (S&P500, 나스닥, 다우): 방향성 및 원인 분석
- 유럽 / 아시아: 주요 움직임
- 달러 인덱스: 강약 원인
- 금리 (10년물 국채): 방향성과 의미

---

## 💡 섹터별 온도

| 섹터 | 온도 | 근거 | 언급 소스 |
|------|------|------|----------|
| AI / 반도체 | 🔥🔥🔥 뜨거움 or 🌡 적온 or 🧊 차가움 | | |
| 에너지 | | | |
| 금융 | | | |
| 소비재 | | | |
| 헬스케어 | | | |
| 귀금속/원자재 | | | |
| 암호화폐 | | | |

뉴스 기반으로 섹터별 온도와 근거를 채워주세요.

---

## 📋 이번 주 주요 일정
- 실적 발표 예정 종목
- 경제 지표 발표 (CPI, PPI, 고용 등)
- 중앙은행 이벤트

---

## 🎯 투자자 액션 포인트

| 구분 | 내용 |
|------|------|
| 단기 (1~2주) | |
| 중기 (1~3개월) | |
| 주의할 리스크 | |
| 주목할 기회 | |

---

## 🧠 오늘의 핵심 결론 — 연결고리 분석

이 섹션이 가장 중요합니다. 위에서 수집한 모든 데이터(지수, 금리, 달러, 원자재, 뉴스)를 종합하여 "왜 이렇게 됐는가"를 인과관계로 설명하세요.

아래 항목을 반드시 포함하세요:

### ① 오늘의 이상 신호 (Anomaly)
- 평소와 다르게 유례없이 튀거나 급락한 지표가 있다면 반드시 짚기
- 예: "VIX가 단기간 40% 급등 — 이는 2020년 코로나 이후 최고치"
- 예: "달러 인덱스가 동시에 오르면서 금도 오름 — 전통적 역상관관계 붕괴"

### ② 인과관계 체인 (Cause → Effect)
- A가 일어나서 → B가 움직이고 → C에 영향을 준다는 형태로 서술
- 최소 2~3개 체인을 구체적으로 작성
- 예: "연준 매파 발언 → 10년물 금리 급등 → 성장주(나스닥) 하락 → 달러 강세 → 신흥국 통화 압박"
- 예: "중동 긴장 고조 → 브렌트유 +5% → 에너지 섹터 강세 / 항공·물류 약세 → 인플레 재점화 우려"

### ③ 정치·지정학 요인 분석
- 현재 시장에 영향을 주는 정치적/지정학적 이벤트 설명
- 예: 미중 관세, 트럼프 발언, 러우 전쟁, 중동 분쟁, 선거 등
- 해당 요인이 어떤 자산에 어떻게 작용하는지 구체적으로

### ④ 지금 시장이 '무엇을 믿고 있는가'
- 시장 참여자들의 집단 심리와 컨센서스를 한 문장으로 요약
- 예: "시장은 현재 연착륙을 70% 확률로 믿고 있으며, 금리 인하 기대가 주가를 지지 중"
- 예: "VIX 급등에도 풋옵션 매수보다 콜옵션이 많은 것은 공포 속 저가매수 심리"

### ⑤ 개인 투자자 결론 (3줄 요약)
> - **지금 시장의 핵심 리스크:** (한 문장)
> - **지금 시장의 핵심 기회:** (한 문장)
> - **내일/이번 주 가장 주목할 변수:** (한 문장)

---

> ⚠️ 본 브리핑은 수집된 뉴스 기반 참고 정보입니다. 투자 결정은 본인 판단 하에 이루어져야 합니다."""

        return self._ask(prompt, max_tokens=3000)


# ==========================================
# 5. YouTube 에이전트
# ==========================================

# 신뢰 채널 (youtube_digest/search.md 참조)
TRUSTED_CHANNELS = [
    "@CNBC", "@BloombergTV", "@PatrickBoyleOnFinance",
    "@GrahamStephan", "@ThePlainBagel", "@lexfridman",
    "@aiexplained-official", "@mreflow",
]


def check_ytdlp() -> bool:
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _yt_fetch(cmd: list) -> list[dict]:
    """yt-dlp 명령 실행 후 영상 목록을 파싱합니다."""
    blocked = ["리딩방", "유료강의", "수익인증", "#Shorts", "shorts"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        videos = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) < 5:
                continue
            vid_id, title, channel, view_count, upload_date = parts[:5]
            try:
                view_count = int(view_count)
            except Exception:
                view_count = 0
            if any(b in title for b in blocked):
                continue
            videos.append({
                "video_id": vid_id,
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "title": title,
                "channel": channel,
                "view_count": view_count,
                "upload_date": upload_date,
            })
        return videos
    except Exception:
        return []


def search_yt_videos(query: str, limit: int = 5) -> list[dict]:
    """
    순수 키워드 기반 YouTube 검색. 채널 고정 없음.
    최근 6개월 이내, 조회수 높은 순 반환.
    """
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=180)).strftime("%Y%m%d")
    all_videos = []
    seen_ids = set()

    queries = [
        query,
        f"{query} 2025 analysis",
        f"{query} market outlook",
        f"{query} explained",
        f"{query} invest strategy",
    ]

    for q in queries:
        cmd = [
            "yt-dlp",
            "--print", "%(id)s\t%(title)s\t%(channel)s\t%(view_count)s\t%(upload_date)s",
            "--no-download",
            f"ytsearch30:{q}",
        ]
        for v in _yt_fetch(cmd):
            if v["video_id"] in seen_ids:
                continue
            if v["upload_date"] and v["upload_date"] < cutoff:
                continue
            seen_ids.add(v["video_id"])
            v["_score"] = v["view_count"]
            all_videos.append(v)
        if len(all_videos) >= limit * 6:
            break

    all_videos.sort(key=lambda x: x["_score"], reverse=True)
    return all_videos[:limit]


def get_transcript(url: str, video_id: str) -> str:
    """yt-dlp로 자막 시도 → 없으면 faster-whisper STT 폴백"""
    # Streamlit 실행 시 PATH에 Homebrew bin 추가
    _env = os.environ.copy()
    _env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + _env.get("PATH", "")

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1단계: 기존 자막 시도
        for lang in ["ko", "en"]:
            cmd = [
                "yt-dlp",
                "--write-auto-sub", "--write-sub",
                "--sub-lang", lang,
                "--sub-format", "vtt",
                "--skip-download", "--no-playlist",
                "--output", f"{tmpdir}/{video_id}",
                url,
            ]
            subprocess.run(cmd, capture_output=True, timeout=30, env=_env)
            vtt_files = [f for f in os.listdir(tmpdir) if f.endswith(".vtt")]
            if vtt_files:
                return _parse_vtt(f"{tmpdir}/{vtt_files[0]}")

        # 2단계: 자막 없으면 오디오 다운 → Whisper STT
        audio_output = f"{tmpdir}/{video_id}"
        cmd = [
            "yt-dlp",
            "-x", "--audio-format", "mp3",
            "--audio-quality", "5",
            "--no-playlist",
            "--output", audio_output,
            url,
        ]
        subprocess.run(cmd, capture_output=True, timeout=180, env=_env)

        # 실제 저장된 오디오 파일 탐색
        audio_files = [
            f for f in os.listdir(tmpdir)
            if not f.endswith(".vtt") and "." in f
        ]
        if not audio_files:
            return ""
        actual_audio = os.path.join(tmpdir, audio_files[0])

        # faster-whisper로 로컬 STT
        from faster_whisper import WhisperModel
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(actual_audio, beam_size=5)
        return " ".join(seg.text.strip() for seg in segments)

    return ""


def _parse_vtt(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    raw = re.sub(r"\d{2}:\d{2}:\d{2}\.\d{3} --> .*\n", "", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = re.sub(r"WEBVTT.*\n", "", raw)
    lines = raw.splitlines()
    seen, deduped = set(), []
    for line in lines:
        line = line.strip()
        if line and line not in seen:
            seen.add(line)
            deduped.append(line)
    return " ".join(deduped)


class YouTubeAnalyst:
    def __init__(self, client):
        self.client = client

    def summarize(self, video: dict) -> str:
        transcript = video.get("transcript", "")
        if not transcript:
            return "자막 없음"

        prompt = f"""당신은 투자/금융 콘텐츠 분석가입니다.
아래 YouTube 영상 자막을 투자 관점에서 분석하세요.

제목: {video['title']}
채널: {video['channel']}
조회수: {video['view_count']:,}

자막:
{transcript[:6000]}

---
아래 형식으로 작성하세요 (Markdown):

## [{video['title']}]
출처: {video['channel']} | 조회수: {video['view_count']:,} | {video['upload_date']}
URL: {video['url']}

### 📌 핵심 요약
- (3~5줄, 사실 기반, 수치 포함)

### 💡 인사이트
- (투자자에게 실질적으로 유용한 정보 2~3줄)

### ⚠️ 유의사항
- (편향, 특이 전제, 주의사항 — 없으면 생략)

### 🏷️ 언급 종목/자산
- 티커 또는 자산명 목록 (예: NVDA, BTC, 삼성전자)

---
주의: 단정적 표현 금지. 원문에 없는 내용 추가 금지. 영어 자막이면 한국어로 번역."""

        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def recommend(self, summaries_text: str) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        prompt = f"""당신은 투자 리서치 애널리스트입니다.
아래 YouTube 영상 요약들을 종합하여 투자 추천 리포트를 작성하세요.

{summaries_text}

---
아래 형식으로 작성하세요 (Markdown):

# 📈 투자 추천 — {today}

## 🏆 이번 주 주목할 투자처

언급 빈도와 긍정/부정 맥락을 종합하여 상위 3~5개 종목/자산을 추천하세요.
각 항목마다:
- 추천 등급: ⭐⭐⭐ 강력추천 / ⭐⭐ 관심 / ⭐ 참고
- 언급 소스: (어느 채널에서 언급됐는지)
- 핵심 근거: (2~3줄)
- 리스크: (1~2줄)
- 투자 타이밍: 🟢지금 진입 / 🟡분할매수 / 🔴관망 / ⏳중장기 대기

## ⚠️ 주의 종목 / 리스크 요인
- 부정적으로 언급된 종목이나 이슈

## 📊 섹터별 온도
| 섹터 | 온도 | 언급 소스 수 |
|------|------|------------|
| AI / 반도체 | 🔥🔥🔥 | |
| ... | | |

---
⚠️ 본 추천은 미디어 언급 빈도 기반 참고 정보입니다. 투자 책임은 본인에게 있습니다."""

        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text


# ==========================================
# 6. 메인 화면
# ==========================================
st.title("📊 BAYSIA Insight Terminal")

tab1, tab2, tab3 = st.tabs(["🔍 종목 분석 (Stock)", "🌍 시장 브리핑 (Macro)", "🎬 YouTube Digest"])

with tab1:
    col1, col2 = st.columns([1, 3])
    with col1:
        ticker_raw = st.text_input("Ticker Symbol", value="NVDA", help="티커(NVDA) 또는 회사명(GOOGLE, 삼성전자, BITCOIN) 입력 가능")
        ticker_input = normalize_ticker(ticker_raw)
        if ticker_input != ticker_raw.upper():
            st.caption(f"→ 티커 변환: **{ticker_raw.upper()}** → **{ticker_input}**")
        analyze_btn = st.button("🚀 Analyze Stock", type="primary")

    if analyze_btn:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            st.error("⚠️ 사이드바에 Anthropic API Key를 입력해주세요.")
            st.stop()

        quant = QuantEngine()
        ai = AIAnalyst()

        with st.spinner(f"📡 '{ticker_input}' 데이터 수집 및 분석 중..."):
            data = quant.get_data(ticker_input)

            if data:
                news_query = f"{ticker_input} stock analysis investment 2026"
                news_text = collect_news(news_query, max_results=8)
                report = ai.generate_report(ticker_input, data, news_text)
                st.session_state["tab1_report"] = report
                st.session_state["tab1_ticker"] = ticker_input
                st.session_state["tab1_data"] = data
            else:
                st.error("데이터를 불러올 수 없습니다. 티커를 확인해주세요.")

    # 세션에 결과가 있으면 항상 렌더링 (버튼 재클릭 없이도 유지)
    if st.session_state.get("tab1_data"):
        data = st.session_state["tab1_data"]
        report = st.session_state["tab1_report"]
        saved_ticker = st.session_state["tab1_ticker"]

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("현재가", f"{data['price']:.2f}", f"{data['change']:.2f}%")

        rsi_val = data['rsi']
        rsi_label = "과매수 🔴" if rsi_val > 70 else "과매도 🟢" if rsi_val < 30 else "중립 🟡"
        m2.metric("RSI (14)", f"{rsi_val:.1f}", rsi_label, delta_color="off")

        pos = data['52w_position']
        pos_label = "저점권 🟢" if pos and pos <= 30 else "고점권 🔴" if pos and pos >= 80 else "중간 🟡"
        m3.metric("52주 위치", f"{pos:.1f}%" if pos else "N/A", pos_label, delta_color="off")

        peg_val = data['peg']
        peg_label = "저평가 🟢" if peg_val and peg_val < 1 else "고평가 🔴" if peg_val and peg_val > 2 else "적정 🟡"
        m4.metric("PEG", f"{peg_val:.2f}" if peg_val else "N/A", peg_label)

        m5.metric("MA 신호", data['ma_signal'],
                  "🟢" if data['ma_signal'] == "골든크로스" else "🔴",
                  delta_color="off")

        st.divider()

        st.subheader("📈 Technical Chart")
        fig = go.Figure()
        chart_df = data['df'].tail(120)

        fig.add_trace(go.Candlestick(
            x=chart_df.index,
            open=chart_df['Open'], high=chart_df['High'],
            low=chart_df['Low'], close=chart_df['Close'], name='Price'
        ))
        fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df['SMA_50'],
                                 line=dict(color='orange', width=1.5), name='MA50'))
        fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df['SMA_200'],
                                 line=dict(color='cyan', width=1.5), name='MA200'))
        fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df['bb_upper'],
                                 line=dict(color='gray', width=1, dash='dot'), name='BB Upper'))
        fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df['bb_lower'],
                                 line=dict(color='gray', width=1, dash='dot'), name='BB Lower'))
        fig.update_layout(height=420, xaxis_rangeslider_visible=False, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("📊 퀀트 데이터 상세"):
            upside = round((data['target'] - data['price']) / data['price'] * 100, 1) if data['target'] and data['price'] else None

            def _v(val, digits=2):
                if val is None:
                    return "N/A"
                try:
                    return round(float(val), digits)
                except Exception:
                    return str(val)

            def _mc(v):
                if not v:
                    return "N/A"
                try:
                    v = float(v)
                    if v >= 1e12: return f"${v/1e12:.2f}T"
                    if v >= 1e9:  return f"${v/1e9:.2f}B"
                    if v >= 1e6:  return f"${v/1e6:.2f}M"
                    return f"${v:,.0f}"
                except Exception:
                    return "N/A"

            def _row(label, val):
                return f"| {label} | {val} |"

            c1, c2 = st.columns(2)

            with c1:
                st.markdown("**💰 가격 / 기술적**")
                st.markdown(
                    "| 항목 | 값 |\n|---|---|\n"
                    + "\n".join([
                        _row("현재가", f"${_v(data['price'])}"),
                        _row("전일 대비", f"{_v(data['change'])}%"),
                        _row("52주 고가", f"${_v(data['52w_high'])}"),
                        _row("52주 저가", f"${_v(data['52w_low'])}"),
                        _row("52주 위치", f"{_v(data['52w_position'])}%" if data['52w_position'] else "N/A"),
                        _row("RSI (14)", _v(data['rsi'], 1)),
                        _row("MA50", f"${_v(data['ma_50'])}"),
                        _row("MA200", f"${_v(data['ma_200'])}"),
                        _row("MA 신호", data['ma_signal']),
                        _row("BB 상단", f"${_v(data['bb_upper'])}"),
                        _row("BB 하단", f"${_v(data['bb_lower'])}"),
                        _row("ATR", _v(data['atr'])),
                        _row("손절선 (ATR×2)", f"${_v(data['price'] - 2 * data['atr'])}"),
                        _row("Beta", _v(data['beta'])),
                    ])
                )

                st.markdown("**📊 밸류에이션**")
                st.markdown(
                    "| 항목 | 값 |\n|---|---|\n"
                    + "\n".join([
                        _row("시가총액", _mc(data['market_cap'])),
                        _row("Forward P/E", _v(data['pe'])),
                        _row("Trailing P/E", _v(data['trailing_pe'])),
                        _row("PEG", _v(data['peg'])),
                        _row("P/B", _v(data['pb'])),
                        _row("P/S", _v(data['ps'])),
                        _row("EV/EBITDA", _v(data['ev_ebitda'])),
                        _row("EV/Revenue", _v(data['ev_revenue'])),
                        _row("애널목표가(평균)", f"${_v(data['target'])}"),
                        _row("목표가 상단", f"${_v(data['target_high'])}"),
                        _row("목표가 하단", f"${_v(data['target_low'])}"),
                        _row("상승여력", f"{upside}%" if upside else "N/A"),
                    ])
                )

                st.markdown("**🎭 심리 / 소유구조**")
                st.markdown(
                    "| 항목 | 값 |\n|---|---|\n"
                    + "\n".join([
                        _row("공매도 비율", f"{_v(data['short_float'])}%" if data['short_float'] else "N/A"),
                        _row("Short Ratio (일)", _v(data['short_ratio'])),
                        _row("기관 보유", f"{_v(data['institution_pct'])}%" if data['institution_pct'] else "N/A"),
                        _row("내부자 보유", f"{_v(data['insider_pct'])}%" if data['insider_pct'] else "N/A"),
                        _row("애널리스트 등급", data['recommendation'] or "N/A"),
                        _row("등급 평균점수", f"{_v(data['recommendation_mean'])}/5.0" if data['recommendation_mean'] else "N/A"),
                        _row("커버리지 애널리스트", f"{data['num_analysts']}명" if data['num_analysts'] else "N/A"),
                    ])
                )

            with c2:
                st.markdown("**💹 수익성**")
                st.markdown(
                    "| 항목 | 값 |\n|---|---|\n"
                    + "\n".join([
                        _row("매출총이익률", f"{_v(data['gross_margin'])}%" if data['gross_margin'] else "N/A"),
                        _row("영업이익률", f"{_v(data['operating_margin'])}%" if data['operating_margin'] else "N/A"),
                        _row("순이익률", f"{_v(data['net_margin'])}%" if data['net_margin'] else "N/A"),
                        _row("ROE", f"{_v(data['roe'])}%" if data['roe'] else "N/A"),
                        _row("ROA", f"{_v(data['roa'])}%" if data['roa'] else "N/A"),
                        _row("총매출", _mc(data['total_revenue'])),
                        _row("EBITDA", _mc(data['ebitda'])),
                    ])
                )

                st.markdown("**📈 성장성**")
                st.markdown(
                    "| 항목 | 값 |\n|---|---|\n"
                    + "\n".join([
                        _row("매출 성장 YoY", f"{_v(data['revenue_growth'])}%" if data['revenue_growth'] else "N/A"),
                        _row("매출 성장 QoQ", f"{_v(data['revenue_growth_q'])}%" if data['revenue_growth_q'] else "N/A"),
                        _row("EPS 성장 YoY", f"{_v(data['earnings_growth'])}%" if data['earnings_growth'] else "N/A"),
                        _row("EPS 성장 QoQ", f"{_v(data['earnings_growth_q'])}%" if data['earnings_growth_q'] else "N/A"),
                        _row("EPS Trailing", f"${_v(data['eps_trailing'])}"),
                        _row("EPS Forward", f"${_v(data['eps_forward'])}"),
                    ])
                )

                st.markdown("**🏦 재무건전성**")
                st.markdown(
                    "| 항목 | 값 |\n|---|---|\n"
                    + "\n".join([
                        _row("현금", _mc(data['total_cash'])),
                        _row("부채", _mc(data['total_debt'])),
                        _row("D/E 비율", _v(data['de_ratio'])),
                        _row("유동비율", _v(data['current_ratio'])),
                        _row("당좌비율", _v(data['quick_ratio'])),
                        _row("FCF", _mc(data['free_cashflow'])),
                        _row("영업CF", _mc(data['operating_cashflow'])),
                    ])
                )

                st.markdown("**💸 배당 / 기업정보**")
                st.markdown(
                    "| 항목 | 값 |\n|---|---|\n"
                    + "\n".join([
                        _row("배당수익률", f"{_v(data['dividend_yield'])}%" if data['dividend_yield'] else "N/A"),
                        _row("배당성향", f"{_v(data['payout_ratio'])}%" if data['payout_ratio'] else "N/A"),
                        _row("섹터", data['sector'] or "N/A"),
                        _row("산업", data['industry'] or "N/A"),
                        _row("임직원 수", f"{data['employees']:,}명" if data['employees'] else "N/A"),
                    ])
                )

            if data.get('earnings_hist'):
                st.markdown("**📋 최근 분기 실적 (EPS)**")
                st.markdown("\n".join(f"- {e}" for e in data['earnings_hist']))

            if data.get('recent_news'):
                st.markdown("**📰 최신 뉴스 헤드라인**")
                st.markdown("\n".join(data['recent_news']))

        st.divider()
        st.subheader("🧠 AI Investment Report")
        with st.container(border=True):
            st.markdown(report)

        export_buttons(report, f"stock_{saved_ticker}", f"{saved_ticker} 종목 분석")

with tab2:
    st.header("🌍 Global Market Digest")
    st.caption("Bloomberg · Reuters · CNBC · SeekingAlpha 수집 → Claude 분석")

    col1, col2 = st.columns([2, 1])
    with col1:
        macro_query = st.text_input(
            "검색 키워드 (선택)",
            value="global stock market AI semiconductor investment 2026",
            help="분석할 주제를 입력하세요"
        )
    with col2:
        st.write("")
        st.write("")
        briefing_btn = st.button("📰 브리핑 생성", type="primary")

    if briefing_btn:
        # 새 검색 시 이전 결과 초기화
        st.session_state.pop("tab2_briefing", None)
        st.session_state.pop("tab2_macro", None)

        if not os.environ.get("ANTHROPIC_API_KEY"):
            st.error("⚠️ 사이드바에 Anthropic API Key를 입력해주세요.")
        else:
            with st.spinner("실시간 거시경제 지표 수집 중..."):
                macro_data = get_macro_data()

            # 거시경제 지표 메트릭 표시
            if macro_data:
                st.subheader("📊 실시간 거시경제 지표")

                def _fmt_val(val: float) -> str:
                    if val >= 10000:
                        return f"{val:,.0f}"
                    elif val >= 100:
                        return f"{val:,.2f}"
                    else:
                        return f"{val:.3f}"

                def _show_row(label: str, keys: list[str]):
                    st.caption(f"**{label}**")
                    cols = st.columns(len(keys))
                    for i, key in enumerate(keys):
                        if key in macro_data:
                            d = macro_data[key]
                            delta_color = "normal"
                            # VIX, VVIX, 하이일드 스프레드 — 오를수록 나쁨
                            if key in ("VIX", "VVIX"):
                                delta_color = "inverse"
                            cols[i].metric(key, _fmt_val(d["value"]), f"{d['change']:+.2f}%", delta_color=delta_color)
                        else:
                            cols[i].metric(key, "N/A", "")

                # 쿼리 키워드로 관련 섹터 강조 표시
                q_lower = macro_query.lower()
                is_tech    = any(w in q_lower for w in ["tech", "ai", "semiconductor", "nvda", "nvidia", "반도체", "기술"])
                is_energy  = any(w in q_lower for w in ["oil", "energy", "crude", "petroleum", "원유", "에너지"])
                is_crypto  = any(w in q_lower for w in ["bitcoin", "btc", "crypto", "eth", "ethereum", "코인", "암호화폐"])
                is_gold    = any(w in q_lower for w in ["gold", "silver", "metal", "금", "은"])
                is_rate    = any(w in q_lower for w in ["rate", "fed", "inflation", "bond", "금리", "인플레", "연준"])
                is_korea   = any(w in q_lower for w in ["korea", "kospi", "한국", "코스피"])
                is_china   = any(w in q_lower for w in ["china", "hong kong", "hang seng", "중국", "항셍"])

                # 관련 섹터를 최상단에 먼저 표시
                if is_tech:
                    _show_row("⭐ [검색 관련] 기술 섹터", ["나스닥", "XLK (기술)"])
                if is_energy:
                    _show_row("⭐ [검색 관련] 에너지", ["WTI 원유", "브렌트유", "천연가스", "XLE (에너지)"])
                if is_crypto:
                    _show_row("⭐ [검색 관련] 암호화폐", ["BTC", "ETH"])
                if is_gold:
                    _show_row("⭐ [검색 관련] 귀금속", ["금 (Gold)", "은 (Silver)"])
                if is_rate:
                    _show_row("⭐ [검색 관련] 금리", ["미국 2년물", "미국 10년물", "미국 30년물", "10Y-2Y 스프레드", "TLT (장기채)", "HYG (하이일드)"])
                if is_korea:
                    _show_row("⭐ [검색 관련] 한국 시장", ["KOSPI", "USD/KRW"])
                if is_china:
                    _show_row("⭐ [검색 관련] 중국/홍콩", ["항셍", "USD/CNY"])

                if any([is_tech, is_energy, is_crypto, is_gold, is_rate, is_korea, is_china]):
                    st.divider()

                _show_row("🇺🇸 미국 주요 지수", ["S&P 500", "나스닥", "다우존스", "러셀 2000"])
                _show_row("🌏 글로벌 지수", ["니케이 225", "항셍", "KOSPI", "FTSE 100", "DAX"])
                _show_row("😱 공포/변동성", ["VIX", "VVIX"])
                _show_row("🏦 미국 금리 (%)", ["미국 2년물", "미국 10년물", "미국 30년물", "10Y-2Y 스프레드"])
                _show_row("📄 채권 시장 (ETF)", ["TLT (장기채)", "HYG (하이일드)"])
                _show_row("💱 달러 / 환율", ["달러 인덱스", "EUR/USD", "USD/JPY", "USD/KRW", "USD/CNY"])
                _show_row("🛢️ 원자재", ["금 (Gold)", "은 (Silver)", "WTI 원유", "브렌트유", "천연가스", "구리"])
                _show_row("₿ 암호화폐", ["BTC", "ETH"])
                _show_row("📂 미국 섹터 ETF", ["XLK (기술)", "XLF (금융)", "XLE (에너지)", "XLV (헬스케어)", "XLI (산업재)", "XLB (소재)"])

                st.divider()

            # 검색어 관련 차트
            _QUERY_CHART_MAP = [
                (["nvda", "nvidia"],            [("NVDA", "NVIDIA")]),
                (["tsla", "tesla"],             [("TSLA", "Tesla")]),
                (["aapl", "apple"],             [("AAPL", "Apple")]),
                (["msft", "microsoft"],         [("MSFT", "Microsoft")]),
                (["meta"],                      [("META", "Meta")]),
                (["google", "googl", "goog"],   [("GOOGL", "Google")]),
                (["amzn", "amazon"],            [("AMZN", "Amazon")]),
                (["bitcoin", "btc", "crypto"],  [("BTC-USD", "Bitcoin"), ("ETH-USD", "Ethereum")]),
                (["ethereum", "eth"],           [("ETH-USD", "Ethereum")]),
                (["oil", "crude", "energy", "wti"], [("CL=F", "WTI Oil"), ("BZ=F", "Brent"), ("XLE", "Energy ETF")]),
                (["gold", "silver", "metal"],   [("GC=F", "Gold"), ("SI=F", "Silver")]),
                (["semiconductor", "chip", "반도체", "ai", "artificial"], [("NVDA", "NVIDIA"), ("AMD", "AMD"), ("INTC", "Intel"), ("XLK", "Tech ETF")]),
                (["korea", "kospi", "한국"],    [("^KS11", "KOSPI"), ("EWY", "Korea ETF")]),
                (["china", "중국", "항셍"],     [("^HSI", "Hang Seng"), ("FXI", "China ETF")]),
                (["japan", "일본", "닛케이"],   [("^N225", "Nikkei")]),
                (["rate", "fed", "inflation", "금리", "연준"], [("^TNX", "10Y Yield"), ("^IRX", "2Y Yield"), ("TLT", "Bond ETF")]),
                (["dollar", "달러", "dxy"],     [("DX-Y.NYB", "Dollar Index")]),
                (["s&p", "sp500", "spx"],       [("^GSPC", "S&P 500")]),
                (["nasdaq", "나스닥"],          [("^IXIC", "NASDAQ")]),
            ]

            q_lower = macro_query.lower()
            chart_tickers = []
            for keywords, tickers in _QUERY_CHART_MAP:
                if any(kw in q_lower for kw in keywords):
                    chart_tickers = tickers
                    break
            if not chart_tickers:
                chart_tickers = [("^GSPC", "S&P 500"), ("^IXIC", "NASDAQ"), ("^VIX", "VIX")]

            st.subheader(f"📈 관련 차트")
            fig2 = go.Figure()
            for ct, ct_name in chart_tickers:
                try:
                    h = yf.Ticker(ct).history(period="6mo")
                    if not h.empty:
                        # 정규화(첫날=100 기준)해서 비교 가능하게
                        norm = h['Close'] / h['Close'].iloc[0] * 100
                        fig2.add_trace(go.Scatter(x=h.index, y=norm, name=ct_name, mode='lines'))
                except Exception:
                    pass
            fig2.update_layout(
                height=350, template="plotly_dark",
                yaxis_title="상대 성과 (시작=100)",
                xaxis_title="",
                legend=dict(orientation="h", y=1.1),
                margin=dict(t=30, b=30),
            )
            st.plotly_chart(fig2, use_container_width=True)
            st.divider()

            with st.spinner(f"'{macro_query}' 관련 뉴스 수집 중..."):
                ai = AIAnalyst()
                news = collect_news(macro_query, max_results=12)
                briefing = ai.macro_briefing(news, macro_data=macro_data, query=macro_query)
                st.session_state["tab2_briefing"] = briefing
                st.session_state["tab2_macro"] = macro_data

    if st.session_state.get("tab2_briefing"):
        with st.container(border=True):
            st.markdown(st.session_state["tab2_briefing"])
        export_buttons(st.session_state["tab2_briefing"], "macro_briefing", "글로벌 증시 브리핑")

with tab3:
    st.header("🎬 YouTube Digest")
    st.caption("yt-dlp로 자막 수집 → Claude 투자 인사이트 분석")

    if not check_ytdlp():
        st.error("yt-dlp가 설치되어 있지 않습니다. `brew install yt-dlp` 후 다시 시도하세요.")
    else:
        # 모드 선택
        mode = st.radio("모드 선택", ["🔗 URL 직접 입력", "🔍 키워드 검색"], horizontal=True)

        if mode == "🔗 URL 직접 입력":
            url_input = st.text_area(
                "YouTube URL 입력 (여러 개는 줄바꿈으로 구분)",
                placeholder="https://www.youtube.com/watch?v=...",
                height=100,
            )
            yt_btn = st.button("🚀 분석 시작", type="primary", key="yt_url")

            if yt_btn and url_input.strip():
                if not os.environ.get("ANTHROPIC_API_KEY"):
                    st.error("⚠️ 사이드바에 Anthropic API Key를 입력해주세요.")
                else:
                    urls = [u.strip() for u in url_input.strip().splitlines() if u.strip()]
                    video_list = []
                    for url in urls:
                        # youtu.be/ID 와 youtube.com/watch?v=ID 두 형식 모두 처리
                        if "youtu.be/" in url:
                            vid_id = url.split("youtu.be/")[-1].split("?")[0]
                        else:
                            vid_id = url.split("v=")[-1].split("&")[0]
                        video_list.append({
                            "video_id": vid_id, "url": url,
                            "title": "직접 입력 영상", "channel": "",
                            "view_count": 0, "upload_date": "",
                        })

                    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
                    yt_ai = YouTubeAnalyst(client)
                    summaries_text = ""

                    for i, video in enumerate(video_list):
                        with st.spinner(f"[{i+1}/{len(video_list)}] 자막/음성 분석 중... (자막 없으면 Whisper STT 자동 실행)"):
                            transcript = get_transcript(video["url"], video["video_id"])
                            if not transcript:
                                st.warning(f"자막 및 음성 추출 실패: {video['url']}")
                                continue
                            video["transcript"] = transcript

                        with st.spinner(f"[{i+1}/{len(video_list)}] 분석 중..."):
                            summary = yt_ai.summarize(video)
                            summaries_text += summary + "\n\n---\n\n"
                            st.markdown(summary)

                    if summaries_text:
                        st.divider()
                        with st.spinner("투자 추천 생성 중..."):
                            recommend = yt_ai.recommend(summaries_text)
                        st.markdown(recommend)
                        full = summaries_text + "\n\n---\n\n" + recommend
                        st.session_state["tab3_result"] = full
                        st.session_state["tab3_key"] = "youtube_digest_url"

            if st.session_state.get("tab3_result") and st.session_state.get("tab3_key") == "youtube_digest_url":
                export_buttons(st.session_state["tab3_result"], "youtube_digest_url", "YouTube Digest")

        else:  # 키워드 검색 모드
            col1, col2 = st.columns([3, 1])
            with col1:
                search_query = st.text_input(
                    "검색어 (영어 권장)",
                    value="stock market analysis AI investment 2026",
                    placeholder="e.g. NVDA stock analysis 2026",
                )
            with col2:
                st.write("")
                st.write("")
                max_videos = st.selectbox("영상 수", [3, 5, 7], index=1)

            yt_search_btn = st.button("🔍 검색 후 분석", type="primary", key="yt_search")

            if yt_search_btn:
                if not os.environ.get("ANTHROPIC_API_KEY"):
                    st.error("⚠️ 사이드바에 Anthropic API Key를 입력해주세요.")
                else:
                    with st.spinner(f"'{search_query}' 영상 검색 중..."):
                        videos = search_yt_videos(search_query, limit=max_videos * 2)
                        videos = videos[:max_videos]

                    if not videos:
                        st.warning("검색 결과가 없습니다. 조회수 5만 이상 영상이 없거나 yt-dlp 오류입니다.")
                    else:
                        st.success(f"{len(videos)}개 영상 발견")

                        # 영상 목록 표시
                        with st.expander("📋 수집된 영상 목록"):
                            for v in videos:
                                st.write(f"- [{v['title']}]({v['url']}) | {v['channel']} | {v['view_count']:,}회")

                        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
                        yt_ai = YouTubeAnalyst(client)
                        summaries_text = ""
                        processed = 0

                        for i, video in enumerate(videos):
                            with st.spinner(f"[{i+1}/{len(videos)}] 자막/음성 분석 중: {video['title'][:40]}..."):
                                transcript = get_transcript(video["url"], video["video_id"])
                                if not transcript:
                                    st.warning(f"음성 추출 실패 (건너뜀): {video['title'][:50]}")
                                    continue
                                video["transcript"] = transcript

                            with st.spinner(f"[{i+1}/{len(videos)}] 분석 중..."):
                                summary = yt_ai.summarize(video)
                                summaries_text += summary + "\n\n---\n\n"
                                st.markdown(summary)
                                processed += 1

                        if summaries_text:
                            st.divider()
                            st.subheader(f"📈 투자 추천 — {processed}개 영상 종합")
                            with st.spinner("투자 추천 생성 중..."):
                                recommend = yt_ai.recommend(summaries_text)
                            st.markdown(recommend)
                            full = summaries_text + "\n\n---\n\n" + recommend
                            st.session_state["tab3_result"] = full
                            st.session_state["tab3_key"] = "youtube_digest_search"

            if st.session_state.get("tab3_result") and st.session_state.get("tab3_key") == "youtube_digest_search":
                export_buttons(st.session_state["tab3_result"], "youtube_digest_search", "YouTube Digest")
