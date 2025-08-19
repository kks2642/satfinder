import requests, urllib.parse, pandas as pd, streamlit as st

# -----------------------------
# 설정: 위키/위키데이터/CELESTRAK
# -----------------------------
WIKI_API = {
    "en": "https://en.wikipedia.org/w/api.php",
    "ko": "https://ko.wikipedia.org/w/api.php",
}
WIKI_SUMMARY = {
    "en": "https://en.wikipedia.org/api/rest_v1/page/summary/",
    "ko": "https://ko.wikipedia.org/api/rest_v1/page/summary/",
}
WIKIDATA_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/"
CELESTRAK_TLE = "https://celestrak.org/NORAD/elements/gp.php"  # NAME=... & FORMAT=TLE

HEADERS = {"User-Agent": "SatFinder/1.1 (contact: student@example.com)"}


# -----------------------------
# 유틸 함수
# -----------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def wiki_search_title(q: str, lang: str) -> str | None:
    """해당 언어 위키백과에서 제목 검색 → 최상위 문서 제목 반환"""
    r = requests.get(
        WIKI_API[lang],
        params={
            "action": "query",
            "list": "search",
            "srsearch": q,
            "format": "json",
            "srlimit": 1,
            "srprop": "",
        },
        headers=HEADERS,
        timeout=15,
    )
    hits = r.json().get("query", {}).get("search", [])
    return hits[0]["title"] if hits else None


@st.cache_data(ttl=3600, show_spinner=False)
def wiki_summary(title: str, lang: str) -> dict:
    """해당 언어의 위키 REST 요약"""
    r = requests.get(WIKI_SUMMARY[lang] + urllib.parse.quote(title), headers=HEADERS, timeout=15)
    return r.json() if r.status_code == 200 else {}


@st.cache_data(ttl=3600, show_spinner=False)
def wikidata_qid_from_title(title: str, lang: str) -> str | None:
    """해당 언어 위키 제목 → QID"""
    r = requests.get(
        WIKI_API[lang],
        params={"action": "query", "prop": "pageprops", "titles": title, "format": "json"},
        headers=HEADERS,
        timeout=15,
    )
    pages = r.json().get("query", {}).get("pages", {})
    for _, pg in pages.items():
        qid = pg.get("pageprops", {}).get("wikibase_item")
        if qid:
            return qid
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def wikidata_entity(qid: str) -> dict:
    """위키데이터 엔티티(라벨/클레임/사이트링크 포함)"""
    r = requests.get(f"{WIKIDATA_ENTITY}{qid}.json", headers=HEADERS, timeout=20)
    ent = r.json().get("entities", {}).get(qid, {})
    return ent


def get_claim_value(ent: dict, prop: str, kind="time|str"):
    c = ent.get("claims", {})
    v = c.get(prop, [])
    if not v:
        return None
    mainsnak = v[0].get("mainsnak", {})
    dv = mainsnak.get("datavalue", {})
    val = dv.get("value")
    if not val:
        return None
    if kind == "time|str":
        return val.get("time") if isinstance(val, dict) else val
    return val


@st.cache_data(ttl=3600, show_spinner=False)
def celestrak_tle(name: str) -> list[str] | None:
    """Celestrak TLE 검색 (이름 그대로 시도)"""
    r = requests.get(
        CELESTRAK_TLE,
        params={"NAME": name, "FORMAT": "TLE"},
        headers=HEADERS,
        timeout=20,
    )
    if r.status_code != 200 or "No GP data" in r.text:
        return None
    lines = [l for l in r.text.strip().splitlines() if l.strip()]
    return lines[:3] if lines else None


def make_table(summary: dict, ent: dict | None, tle_lines: list[str] | None) -> pd.DataFrame:
    """핵심 필드 표로 정리 (한국어 우선)"""
    # 기본 메타
    title = summary.get("title")
    desc = summary.get("description")
    extract = summary.get("extract")

    # 위키데이터 클레임
    launch_date = cospar_id = norad_id = None
    if ent:
        launch_date = get_claim_value(ent, "P619")  # 발사일
        cospar_id = get_claim_value(ent, "P247")    # COSPAR
        norad_id = get_claim_value(ent, "P593")     # NORAD

    rows = [
        ("제목(Title)", title),
        ("설명(Description)", desc),
        ("발사일(Launch Date)", launch_date),
        ("COSPAR ID", cospar_id),
        ("NORAD ID", norad_id),
    ]
    if tle_lines:
        rows += [
            ("TLE Name", tle_lines[0] if len(tle_lines) > 0 else None),
            ("TLE Line 1", tle_lines[1] if len(tle_lines) > 1 else None),
            ("TLE Line 2", tle_lines[2] if len(tle_lines) > 2 else None),
        ]
    return pd.DataFrame(rows, columns=["항목(Field)", "값(Value)"])


# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="🛰️ SatFinder | 위성 조회", page_icon="🛰️", layout="centered")
st.title("🛰️ 인공위성 정보 검색 (Streamlit)")
st.caption("위키백과/위키데이터/CELESTRAK 공개 데이터를 사용합니다. (한국어 우선 표시)")

# 예시 버튼들
st.caption("예시: 허블 우주 망원경 / NOAA 19 / Sentinel-2A / 스타링크-30000")
c1, c2, c3, c4 = st.columns(4)
if c1.button("허블 우주 망원경"):
    st.session_state["query"] = "허블 우주 망원경"
if c2.button("NOAA 19"):
    st.session_state["query"] = "NOAA 19"
if c3.button("Sentinel-2A"):
    st.session_state["query"] = "Sentinel-2A"
if c4.button("스타링크-30000"):
    st.session_state["query"] = "스타링크-30000"

default_q = st.session_state.get("query", "Hubble Space Telescope")
q = st.text_input("위성 이름 또는 NORAD ID", default_q)
use_exact = st.checkbox("입력한 이름으로 TLE 먼저 검색", True)

if st.button("검색"):
    if not q.strip():
        st.warning("검색어를 입력하세요.")
        st.stop()

    # 1) ko → en 순서로 위키 제목 탐색
    with st.spinner("위키 제목 검색(ko→en) 중..."):
        title_ko = wiki_search_title(q, "ko")
        title_en = wiki_search_title(q, "en")

        # 아무 것도 못 찾으면 종료
        if not (title_ko or title_en):
            st.error("위키에서 문서를 찾지 못했습니다. 공식 명칭 또는 NORAD ID로 다시 시도해 보세요.")
            st.stop()

    # 2) QID 확보 (ko가 있으면 ko로, 없으면 en으로)
    with st.spinner("Wikidata(QID) 확인 중..."):
        qid = None
        if title_ko:
            qid = wikidata_qid_from_title(title_ko, "ko")
        if not qid and title_en:
            qid = wikidata_qid_from_title(title_en, "en")

        ent = wikidata_entity(qid) if qid else None
        sitelinks = ent.get("sitelinks", {}) if ent else {}
        ko_title_from_qid = sitelinks.get("kowiki", {}).get("title") if sitelinks else None
        en_title_from_qid = sitelinks.get("enwiki", {}).get("title") if sitelinks else None

    # 3) 한국어 요약 우선, 없으면 영어 요약
    with st.spinner("위키 요약(한국어 우선) 불러오는 중..."):
        summary = {}
        tried = []

        if ko_title_from_qid:
            summary = wiki_summary(ko_title_from_qid, "ko"); tried.append(("ko", ko_title_from_qid))
        if not summary and title_ko:
            summary = wiki_summary(title_ko, "ko"); tried.append(("ko", title_ko))
        if not summary and en_title_from_qid:
            summary = wiki_summary(en_title_from_qid, "en"); tried.append(("en", en_title_from_qid))
        if not summary and title_en:
            summary = wiki_summary(title_en, "en"); tried.append(("en", title_en))

        if not summary:
            st.error("요약 정보를 불러오지 못했습니다.")
            st.stop()

    # 4) TLE 검색: 입력값 → ko/en 제목 순서로 재시도
    with st.spinner("TLE 검색 중..."):
        tle = celestrak_tle(q) if use_exact else None
        if tle is None:
            # ko/en에서 얻은 제목들로 재시도 (영문이 더 잘 맞는 편)
            for cand in [en_title_from_qid, title_en, ko_title_from_qid, title_ko]:
                if cand:
                    tle = celestrak_tle(cand)
                    if tle:
                        break

    # 5) 출력
    st.subheader("📌 개요 (한국어 우선)")
    st.write(f"**제목**: {summary.get('title')}")
    st.write(f"**설명**: {summary.get('description') or '—'}")
    if summary.get("extract"):
        with st.expander("요약 펼치기"):
            st.write(summary["extract"])

    st.subheader("📊 세부 정보")
    df = make_table(summary, ent, tle)
    st.dataframe(df, use_container_width=True)

    st.subheader("🧭 TLE")
    if tle:
        st.code("\n".join(tle))
    else:
        st.info("Celestrak에서 TLE을 찾지 못했습니다. NORAD ID(예: 20580)로 재시도해 보세요.")
