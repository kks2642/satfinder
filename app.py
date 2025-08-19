import requests, urllib.parse, pandas as pd, streamlit as st

WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
WIKIDATA = "https://www.wikidata.org/wiki/Special:EntityData/"
CELESTRAK_TLE = "https://celestrak.org/NORAD/elements/gp.php"
HEADERS = {"User-Agent": "SatFinder/1.0 (contact: student@example.com)"}

@st.cache_data(ttl=3600)
def wiki_search_title(q):
    r = requests.get(WIKI_API, params={
        "action":"query","list":"search","srsearch":q,
        "format":"json","srlimit":1,"srprop":""
    }, headers=HEADERS, timeout=15)
    hits = r.json().get("query",{}).get("search",[])
    return hits[0]["title"] if hits else None

@st.cache_data(ttl=3600)
def wiki_summary(title):
    r = requests.get(WIKI_SUMMARY + urllib.parse.quote(title), headers=HEADERS, timeout=15)
    return r.json() if r.status_code==200 else {}

@st.cache_data(ttl=3600)
def wikidata_qid(title):
    r = requests.get(WIKI_API, params={
        "action":"query","prop":"pageprops","titles":title,"format":"json"
    }, headers=HEADERS, timeout=15)
    pages = r.json().get("query",{}).get("pages",{})
    for _,pg in pages.items():
        qid = pg.get("pageprops",{}).get("wikibase_item")
        if qid: return qid
    return None

@st.cache_data(ttl=3600)
def wikidata_claims(qid):
    if not qid: return {}
    r = requests.get(f"{WIKIDATA}{qid}.json", headers=HEADERS, timeout=20)
    ent = r.json().get("entities",{}).get(qid,{})
    c = ent.get("claims",{})
    def get_time(p):
        v=c.get(p,[]); 
        return v[0]["mainsnak"]["datavalue"]["value"]["time"] if v else None
    def get_str(p):
        v=c.get(p,[]); 
        return v[0]["mainsnak"]["datavalue"]["value"] if v else None
    return {
        "launch_date": get_time("P619"),
        "cospar_id": get_str("P247"),
        "norad_id": get_str("P593"),
    }

@st.cache_data(ttl=3600)
def celestrak_tle(name_or_title):
    r = requests.get(CELESTRAK_TLE,
                     params={"NAME": name_or_title, "FORMAT":"TLE"},
                     headers=HEADERS, timeout=20)
    if r.status_code!=200 or "No GP data" in r.text: return None
    lines=[l for l in r.text.strip().splitlines() if l.strip()]
    return lines[:3]

def make_table(summary, wd, tle):
    rows = [
        ("Title", summary.get("title")),
        ("Description", summary.get("description")),
        ("Launch Date (Wikidata)", wd.get("launch_date")),
        ("COSPAR ID", wd.get("cospar_id")),
        ("NORAD ID", wd.get("norad_id")),
    ]
    if tle:
        rows += [("TLE Name", tle[0]), ("TLE Line 1", tle[1]), ("TLE Line 2", tle[2])]
    return pd.DataFrame(rows, columns=["Field", "Value"])

# UI
st.set_page_config(page_title="🛰️ SatFinder", page_icon="🛰️", layout="centered")
st.title("🛰️ 인공위성 정보 검색 (Streamlit)")
st.caption("위키백과/위키데이터/CELESTRAK 공개 데이터를 사용합니다.")

q = st.text_input("위성 이름 또는 NORAD ID", "Hubble Space Telescope")
use_exact = st.checkbox("입력한 이름으로 TLE 먼저 검색", True)

if st.button("검색"):
    if not q.strip():
        st.warning("검색어를 입력하세요.")
        st.stop()

    title = wiki_search_title(q)
    if not title:
        st.error("위키백과 문서를 찾지 못했습니다. 정확 명칭 또는 NORAD ID로 다시 시도해 보세요.")
        st.stop()

    summary = wiki_summary(title)
    wd = wikidata_claims(wikidata_qid(title))

    tle = celestrak_tle(q) if use_exact else None
    if tle is None:
        tle = celestrak_tle(title)

    st.subheader("📌 개요")
    st.write(f"**제목**: {summary.get('title')}")
    st.write(f"**설명**: {summary.get('description') or '—'}")
    if summary.get("extract"):
        with st.expander("요약 펼치기"):
            st.write(summary["extract"])

    st.subheader("📊 세부 정보")
    st.dataframe(make_table(summary, wd or {}, tle))

    st.subheader("🧭 TLE")
    if tle: st.code("\n".join(tle))
    else: st.info("Celestrak에서 TLE을 찾지 못했습니다. NORAD ID로 재시도해 보세요.")
