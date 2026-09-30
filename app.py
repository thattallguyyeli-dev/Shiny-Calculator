import base64, html, os
import cv2
import streamlit as st
import scanner

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(HERE, "assets", "logo.png")

st.set_page_config(page_title="Shiny Calculator", page_icon=LOGO, layout="centered")

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Fredoka:wght@500;600;700&family=Nunito:wght@400;600;700&display=swap');
:root{--ink:#16235E;--edge:#1B2A6B;--shadow:#1B2A6B;--btn-ink:#1B2A6B;--gold:#FFC81E;--gold2:#FFA800;--red:#E5322D;--mist:#EEF3FB;--card:#FFFFFF;--field:#FFFFFF;--muted:#5A6799;--line:#C9D4EC;--ph:#8C97C2;--hit-top:#FFE680;--hit-tile:#FFF1A8;}
html,body,.stApp{background:var(--mist);}
.stApp p, .stApp label, .stApp li, .stApp input{font-family:'Nunito','Segoe UI',system-ui,sans-serif;color:var(--ink);}
.stAppDeployButton, [data-testid="stAppDeployButton"]{display:none;}
#MainMenu, footer{visibility:hidden;}
header[data-testid="stHeader"]{background:transparent;}
.block-container{max-width:860px;padding-top:4.2rem;padding-bottom:4rem;}
.hero{display:flex;flex-direction:column;align-items:center;text-align:center;margin:0 0 1.2rem 0;}
.hero img{width:210px;height:auto;display:block;}
.hero p{max-width:34rem;margin:.6rem 0 0 0;font-size:1.05rem;line-height:1.5;color:var(--muted);}
.stTextInput label p{font-family:'Fredoka',sans-serif;font-weight:600;font-size:1.05rem;color:var(--ink);}
.stTextInput input{height:3.1rem;border:2.5px solid var(--edge);border-radius:14px;background:var(--field);color:var(--ink);font-size:1rem;padding:0 1rem;box-shadow:0 4px 0 var(--shadow);}
.stTextInput input:focus{outline:3px solid var(--gold);outline-offset:2px;border-color:var(--edge);}
.stTextInput input::placeholder{color:var(--ph);}
.stTextInput > div > div{border:none;background:transparent;box-shadow:none;}.stTextInput [data-testid="stTextInputRootElement"]{overflow:visible;height:auto;min-height:3.1rem;}
.stButton > button, .stButton > button[kind="primary"], button[data-testid="stBaseButton-primary"]{height:3.1rem;width:100%;border:2.5px solid var(--edge);border-radius:14px;background:linear-gradient(180deg,var(--gold) 0%,var(--gold2) 100%);color:var(--btn-ink);font-family:'Fredoka',sans-serif;font-weight:700;font-size:1.1rem;box-shadow:0 4px 0 var(--shadow);transition:transform .08s, box-shadow .08s;}
.stButton > button p{color:var(--btn-ink);font-family:'Fredoka',sans-serif;font-weight:700;font-size:1.1rem;}
.stButton > button:hover{border-color:var(--edge);color:var(--btn-ink);transform:translateY(-1px);box-shadow:0 5px 0 var(--shadow);}
.stButton > button:active{transform:translateY(3px);box-shadow:0 1px 0 var(--shadow);}
.stButton > button:focus-visible{outline:3px solid var(--red);outline-offset:2px;}
@media (prefers-reduced-motion: reduce){.stButton > button{transition:none;}}
div[data-testid="stExpander"]{border:2px solid var(--line);border-radius:14px;background:var(--card);}
div[data-testid="stExpander"] summary p{font-family:'Fredoka',sans-serif;font-weight:600;color:var(--ink);}
.hint{margin:.5rem 0 1.4rem 0;font-size:.95rem;color:var(--muted);}
.note{border:2px solid var(--edge);border-radius:14px;background:var(--card);padding:.8rem 1rem;margin:0 0 1rem 0;box-shadow:0 4px 0 var(--shadow);}
.note.warn{border-color:var(--red);box-shadow:0 4px 0 var(--red);}
.note b{font-family:'Fredoka',sans-serif;font-weight:600;}
.work{border:2.5px solid var(--edge);border-radius:16px;background:var(--card);padding:1rem 1.1rem;margin:1rem 0;box-shadow:0 4px 0 var(--shadow);}
.work-top{display:flex;justify-content:space-between;gap:1rem;align-items:baseline;}
.work-top b{font-family:'Fredoka',sans-serif;font-weight:600;font-size:1.05rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.work-top span{color:var(--muted);font-size:.9rem;white-space:nowrap;}
.track{height:16px;border:2px solid var(--edge);border-radius:999px;background:var(--mist);overflow:hidden;margin:.7rem 0 .4rem 0;}
.track span{display:block;height:100%;background:linear-gradient(180deg,var(--gold) 0%,var(--gold2) 100%);border-right:2px solid var(--edge);}
.track.busy span{width:30%;}
.work-sub{font-size:.88rem;color:var(--muted);}
.card{border:2.5px solid var(--edge);border-radius:18px;background:var(--card);padding:1.2rem 1.2rem 1.3rem 1.2rem;margin:1.4rem 0 .6rem 0;box-shadow:0 5px 0 var(--shadow);}
.card-head{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start;}
.vtitle{font-family:'Fredoka',sans-serif;font-weight:600;font-size:1.2rem;line-height:1.3;color:var(--ink);text-decoration:none;}
.stApp a.vtitle{color:var(--ink);text-decoration:none;}
.stApp a.vtitle:hover{text-decoration:underline;}
.stApp a.tile, .stApp a.tile:hover{text-decoration:none;}
.stApp a.tile .gname, .stApp a.tile .gstat{color:var(--btn-ink);text-decoration:none;}
.dur{color:var(--muted);font-size:.9rem;white-space:nowrap;padding-top:.2rem;}
.verdict{color:var(--ink);display:flex;align-items:center;justify-content:space-between;gap:1rem;margin:1rem 0;padding:.8rem 1rem;border-radius:14px;border:2px solid var(--edge);}
.verdict.hit{color:var(--btn-ink);background:linear-gradient(180deg,var(--hit-top) 0%,var(--gold) 100%);}
.verdict.miss{background:var(--mist);border-color:var(--line);}
.verdict .what{font-family:'Fredoka',sans-serif;font-weight:600;font-size:1.15rem;}
.verdict .pct{font-family:'Fredoka',sans-serif;font-weight:700;font-size:1.7rem;line-height:1;}
.grid{margin:1rem 0 .4rem 0;}
.row{display:flex;justify-content:center;gap:12px;margin-bottom:12px;flex-wrap:wrap;}
.tile{box-sizing:border-box;width:158px;aspect-ratio:3/2;border-radius:12px;padding:.6rem .7rem;display:flex;flex-direction:column;justify-content:space-between;text-decoration:none;}
.tile .gname{font-family:'Fredoka',sans-serif;font-weight:600;font-size:1rem;}
.tile .gstat{font-size:.92rem;font-weight:700;}
.tile.miss{border:2px dashed var(--line);background:var(--card);color:var(--muted);}
.tile.miss .gname,.tile.miss .gstat{color:var(--muted);}
.tile.hit{border:2.5px solid var(--edge);background:linear-gradient(160deg,var(--hit-tile) 0%,var(--gold) 55%,var(--gold2) 100%);box-shadow:0 3px 0 var(--shadow);}
.tile.hit .gname,.tile.hit .gstat{color:var(--btn-ink);}
a.tile.hit:hover{transform:translateY(-1px);}
a.tile.hit:focus-visible{outline:3px solid var(--red);outline-offset:2px;}
.meter{height:14px;border:2px solid var(--edge);border-radius:999px;background:var(--mist);overflow:hidden;margin-top:1rem;}
.meter span{display:block;height:100%;background:linear-gradient(180deg,var(--gold) 0%,var(--gold2) 100%);}
.extra{font-size:.92rem;color:var(--muted);margin-top:.6rem;}
.sumtable{width:100%;border-collapse:collapse;margin-top:.8rem;font-size:.95rem;}
.sumtable th{border-left:none;border-right:none;border-top:none;font-family:'Fredoka',sans-serif;font-weight:600;text-align:left;border-bottom:2px solid var(--edge);padding:.4rem .5rem;}
.sumtable td{border:none;border-bottom:1px solid var(--line);padding:.45rem .5rem;}
.sumtable td.num,.sumtable th.num{text-align:right;white-space:nowrap;}
@media (max-width:640px){.hero img{width:170px;}.tile{width:calc(50% - 8px);}.verdict{flex-direction:column;align-items:flex-start;}}
.err{color:var(--muted);font-size:.88rem;}.topbar{display:flex;justify-content:flex-end;}.steps{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin:1rem 0 0 0;padding:0;list-style:none;}.steps li{display:flex;align-items:center;gap:8px;max-width:15rem;text-align:left;font-size:.9rem;line-height:1.3;color:var(--ink);border:2px solid var(--line);border-radius:14px;background:var(--card);padding:.5rem .7rem;}.steps b{flex:none;display:inline-flex;align-items:center;justify-content:center;width:1.6rem;height:1.6rem;border-radius:50%;background:linear-gradient(180deg,var(--gold),var(--gold2));color:var(--btn-ink);font-family:'Fredoka',sans-serif;font-weight:700;}.hero p.lead{max-width:36rem;}"""

DARK = """
:root{--ink:#EEF1FF;--edge:#5C6BC2;--shadow:#04061A;--mist:#0D1230;--card:#161D48;--field:#0D1230;--muted:#A4AEDC;--line:#2F3A80;--ph:#7A86BD;}
html{color-scheme:dark;}
html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:var(--mist) !important;color:var(--ink);}
header[data-testid="stHeader"]{background:transparent !important;}
[data-testid="stStatusWidget"], [data-testid="stStatusWidget"] *{color:var(--ink) !important;}
.stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stWidgetLabel"], .stApp [data-testid="stWidgetLabel"] *{color:var(--ink);}
.stApp [data-testid="stCaptionContainer"], .stApp [data-testid="stCaptionContainer"] *, .stApp [data-testid="stImageCaption"]{color:var(--muted);}
.stApp [data-testid="stMarkdownContainer"] a:not(.vtitle):not(.tile){color:#9DB8FF;}
.stApp .stTextInput [data-baseweb="input"], .stApp .stTextInput [data-baseweb="base-input"]{background:var(--field) !important;}
.stApp [data-testid="stNumberInput"] [data-baseweb="input"], .stApp [data-testid="stNumberInput"] [data-baseweb="base-input"], .stApp [data-testid="stNumberInput"] input{background:var(--field) !important;color:var(--ink) !important;}
.stApp [data-testid="stNumberInput"] button{background:var(--card) !important;color:var(--ink) !important;border-color:var(--line) !important;}
.stApp [data-testid="stNumberInput"] button svg{fill:var(--ink);color:var(--ink);}
.stApp [data-baseweb="select"] > div{background:var(--field) !important;border-color:var(--line) !important;color:var(--ink) !important;}
.stApp [data-baseweb="select"] *{color:var(--ink) !important;}
.stApp [data-baseweb="select"] svg{fill:var(--ink) !important;}
div[data-baseweb="popover"], div[data-baseweb="popover"] > div{background:var(--card) !important;color:var(--ink) !important;}
div[data-baseweb="popover"] ul, div[data-baseweb="popover"] [role="listbox"], div[data-baseweb="menu"]{background:var(--card) !important;}
div[data-baseweb="popover"] li, div[data-baseweb="popover"] [role="option"]{background:var(--card) !important;color:var(--ink) !important;}
div[data-baseweb="popover"] li:hover, div[data-baseweb="popover"] [role="option"]:hover, div[data-baseweb="popover"] [aria-selected="true"]{background:var(--line) !important;}
div[data-baseweb="tooltip"] > div, [data-testid="stTooltipContent"]{background:var(--card) !important;color:var(--ink) !important;}
[data-testid="stTooltipIcon"] svg{color:var(--muted);fill:var(--muted);}
.stApp div[data-testid="stExpander"], .stApp div[data-testid="stExpander"] details{background:var(--card);border-color:var(--line);}
.stApp div[data-testid="stExpander"] summary{background:transparent;color:var(--ink);}
.stApp div[data-testid="stExpander"] summary:hover{background:var(--line);}
.stApp div[data-testid="stExpander"] summary svg{color:var(--ink);fill:var(--ink);}
[data-testid="stSelectboxVirtualDropdown"], [data-testid="stSelectboxVirtualDropdown"] > div{background:var(--card) !important;color:var(--ink) !important;}
[data-testid="stSelectboxVirtualDropdown"] [role="option"]{background:transparent !important;color:var(--ink) !important;}
[data-testid="stSelectboxVirtualDropdown"] [role="option"]:hover, [data-testid="stSelectboxVirtualDropdown"] [role="option"][aria-selected="true"], [data-testid="stSelectboxVirtualDropdown"] [role="option"][data-focused], [data-testid="stSelectboxVirtualDropdown"] [role="option"][data-hovered]{background:var(--line) !important;}
.stApp [data-testid="stSelectbox"] div:has(> input){background:var(--field) !important;border-color:var(--line) !important;}
.stApp [data-testid="stSelectbox"] input{color:var(--ink) !important;-webkit-text-fill-color:var(--ink) !important;background:transparent !important;}
.stApp [data-testid="stSelectbox"] button, .stApp [data-testid="stSelectbox"] button svg{color:var(--ink) !important;background:transparent !important;}
.stApp [data-testid="stSelectbox"] button svg path:not([fill="none"]){fill:var(--ink) !important;}
.stApp [data-testid="stNumberInputContainer"], .stApp [data-testid="stNumberInputContainer"] > div{background:var(--field) !important;border-color:var(--line) !important;}
.stApp [data-testid="stToggle"] label p, .stApp [data-testid="stCheckbox"] label p{color:var(--ink);}
"""

if "dark" not in st.session_state:
    st.session_state["dark"] = st.query_params.get("theme") == "dark"


def _remember_theme():
    st.query_params["theme"] = "dark" if st.session_state["dark"] else "light"


_, _tcol = st.columns([6, 2])
dark = _tcol.toggle("Dark mode", key="dark", on_change=_remember_theme)

st.markdown("<style>" + " ".join((CSS + (DARK if dark else "")).split()) + "</style>", unsafe_allow_html=True)


def logo_uri():
    with open(LOGO, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def fmt(sec):
    if sec is None:
        return ""
    s = int(sec)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def link_at(u, sec):
    s = int(sec)
    base = u.split("&t=")[0]
    if "twitch.tv" in u and "/videos/" in u:
        return f"{base.split('?')[0]}?t={s // 3600}h{s % 3600 // 60}m{s % 60}s"
    if "youtube.com/watch" in u or "youtu.be/" in u:
        return f"{base}{'&' if '?' in base else '?'}t={s}s"
    return u


def work_html(title, i, n, t=None, dur=None):
    if dur and t is not None:
        pct = max(2, min(100, int(100 * t / dur)))
        track = f'<div class="track"><span style="width:{pct}%"></span></div>'
        sub = f"{fmt(t)} of {fmt(dur)} watched"
    else:
        track = '<div class="track busy"><span></span></div>'
        sub = "Opening the video..." if t is None else f"{fmt(t)} watched"
    count = f"Video {i} of {n}" if n > 1 else ""
    return ('<div class="work"><div class="work-top"><b>' + html.escape(title or "Video") + "</b><span>" + count +
            "</span></div>" + track + '<div class="work-sub">' + sub + " &middot; streaming only, nothing is saved</div></div>")


def card_html(v, r):
    n = r["n_screens"]
    found = {e["screen"]: e for e in r["events"]}
    hit_keys = {(e["row"], e["col"]): e for e in r["events"]}
    k = len({(e["row"], e["col"]) for e in r["events"]})
    pct = 100.0 * k / n if n else 0.0
    head = ('<div class="card-head"><a class="vtitle" target="_blank" href="' + html.escape(v["url"] or "#") + '">' +
            html.escape(v["title"] or v["url"]) + '</a><span class="dur">' + fmt(r["duration"]) + "</span></div>")
    if not n:
        body = ('<div class="verdict miss"><span class="what">No game screens found</span></div>'
                '<div class="extra">Open &ldquo;What the scanner saw&rdquo; below to check. '
                "The stream may use a layout the scanner does not recognize.</div>")
        return '<div class="card">' + head + body + "</div>"
    guess = ""
    if r.get("method") in ("motion", "whole frame"):
        guess = ('<div class="extra">&#9888; No clear game borders were visible, so the scanner guessed where the '
                 "game is. Check &ldquo;What the scanner saw&rdquo; below.</div>")
    if k:
        what = f"{k} of {n} games hit a shiny" if n > 1 else "This game hit a shiny"
        verdict = f'<div class="verdict hit"><span class="what">&#10022; {what}</span><span class="pct">{pct:.0f}%</span></div>'
    else:
        verdict = f'<div class="verdict miss"><span class="what">No shiny found &middot; 0 of {n} games</span><span class="pct">0%</span></div>'
    rows = {}
    for s in r["layout"]:
        rows.setdefault(s["row"], []).append(s)
    grid = '<div class="grid">'
    for ri in sorted(rows):
        grid += '<div class="row">'
        for s in sorted(rows[ri], key=lambda s: s["col"]):
            e = hit_keys.get((s["row"], s["col"]))
            if e:
                grid += ('<a class="tile hit" target="_blank" href="' + html.escape(link_at(v["url"], e["t"])) +
                         f'"><span class="gname">Game {s["id"]}</span><span class="gstat">&#10022; Shiny at {e["stamp"]}</span></a>')
            else:
                grid += f'<div class="tile miss"><span class="gname">Game {s["id"]}</span><span class="gstat">No shiny</span></div>'
        grid += "</div>"
    grid += "</div>"
    extra = ""
    layout_keys = {(s["row"], s["col"]) for s in r["layout"]}
    odd = [e for e in r["events"] if (e["row"], e["col"]) not in layout_keys]
    if odd:
        extra = '<div class="extra">Also seen while the layout was different: ' + ", ".join(
            f'row {e["row"]} #{e["col"]} at {e["stamp"]}' for e in odd) + "</div>"
    meter = f'<div class="meter"><span style="width:{pct:.1f}%"></span></div>'
    return '<div class="card">' + head + verdict + grid + meter + guess + extra + "</div>"


# ------------------------------------------------------------------ page
st.markdown(
    '<div class="hero"><img alt="Shiny Calculator" src="' + logo_uri() + '">'
    '<p class="lead">Shiny hunters often run several games at once. Paste a Twitch or YouTube link and Shiny Calculator '
    'watches the video for you, finds each game screen, spots the sparkle when a shiny appears, and tells you '
    'which games hit one, when, and what percent of the games got a shiny.</p>'
    '<ul class="steps">'
    '<li><b>1</b><span>Paste a channel, VOD or clip link</span></li>'
    '<li><b>2</b><span>It finds every game screen and watches each one</span></li>'
    '<li><b>3</b><span>See the shinies, their timestamps and the percent</span></li>'
    '</ul></div>', unsafe_allow_html=True)

c1, c2 = st.columns([5, 2], vertical_alignment="bottom")
with c1:
    url = st.text_input("Channel, VOD or clip link",
                        placeholder="twitch.tv/name/videos  or  youtube.com/@name/videos")
with c2:
    go = st.button("Scan for shinies", type="primary")
st.markdown('<div class="hint">On a channel page, only videos with &ldquo;shiny&rdquo; in the title are scanned.</div>',
            unsafe_allow_html=True)
with st.expander("Options"):
    o1, o2 = st.columns(2)
    limit = o1.number_input("Latest videos to check on a channel page", 1, 100, 20)
    height = o2.selectbox("Video quality", [360, 480, 720], index=1,
                          help="Higher quality catches smaller sparkles but takes longer.")
    s1, s2 = st.columns(2)
    style_label = s1.selectbox(
        "Sparkle style", ["Gold stars (Gen 3)", "Any bright sparkle (Gen 4-6, experimental)"],
        help="The second option also catches blue and white sparkles, but it can give more false alarms.")
    layout_mode = s2.selectbox(
        "Game screens", ["Find automatically", "I will mark them"],
        help="Automatic finds any game windows that have a visible edge, in any layout. If the picture under "
             "\"What the scanner saw\" is wrong, mark the game boxes yourself.")
    regions_text = ""
    if layout_mode == "I will mark them":
        st.caption("One game per line: x, y, width, height, as a percent of the video (0 to 100). "
                   "Example for one game filling the right side: 25, 0, 75, 75")
        regions_text = st.text_area("Game boxes", height=110, label_visibility="collapsed",
                                    placeholder="1, 2, 36, 43\n63, 2, 36, 43")
        p1, p2 = st.columns([2, 1], vertical_alignment="bottom")
        preview_at = p1.number_input("Preview at (seconds into the video)", 0, 100000, 60)
        preview_go = p2.button("Preview boxes")
    else:
        preview_go = False
    style = "any" if style_label.startswith("Any") else "gold"
    ignore_text = st.text_input("Ignore screens (optional)", placeholder="3",
                                help="If the scanner counted something that is not a game, like your webcam, type its "
                                     "number from the \"What the scanner saw\" picture. Separate several with commas.")
    ignore = {int(x) for x in ignore_text.replace(" ", "").split(",") if x.isdigit()} if ignore_text else set()

def _parse_boxes():
    try:
        regs = scanner.parse_regions(regions_text)
    except ValueError as e:
        st.markdown('<div class="note warn"><b>Check the game boxes.</b><br><span class="err">'
                    + html.escape(str(e)) + "</span></div>", unsafe_allow_html=True)
        st.stop()
    if not regs:
        st.markdown('<div class="note warn"><b>Add at least one game box</b> or switch back to '
                    "finding the game screens automatically.</div>", unsafe_allow_html=True)
        st.stop()
    return regs


regions = None
if layout_mode == "I will mark them" and (go or preview_go):
    regions = _parse_boxes()

if preview_go:
    if not url.strip():
        st.markdown('<div class="note warn"><b>Add a link first.</b> Paste a video address above to preview on.</div>',
                    unsafe_allow_html=True)
    else:
        purl = url.strip() if url.strip().startswith("http") else "https://" + url.strip()
        try:
            with st.spinner("Grabbing a frame..."):
                pv = scanner.list_videos(purl, 1)[0][0]
                frame = scanner.grab_frame(scanner.stream_url(pv["url"], int(height)), float(preview_at))
            H_, W_ = frame.shape[:2]
            st.caption("Green boxes are the game screens that will be scanned. The thin orange box is where the "
                       "sparkle is looked for.")
            st.image(cv2.cvtColor(scanner.draw_layout(frame, scanner.regions_to_screens(regions, W_, H_)),
                                  cv2.COLOR_BGR2RGB))
        except Exception as e:
            st.markdown('<div class="note warn"><b>Could not preview.</b><br><span class="err">'
                        + html.escape(str(e)[-300:]) + "</span></div>", unsafe_allow_html=True)

if go and not url.strip():
    st.markdown('<div class="note warn"><b>Add a link first.</b> Paste a channel, VOD or clip address above.</div>',
                unsafe_allow_html=True)

if go and url.strip():
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    slot = st.empty()
    slot.markdown(work_html("Reading the link", 1, 1), unsafe_allow_html=True)
    try:
        vids, is_list = scanner.list_videos(url, int(limit))
    except Exception as e:
        slot.empty()
        st.markdown('<div class="note warn"><b>Could not read that link.</b> Check the address and try again.<br>'
                    '<span class="err">' + html.escape(str(e)[-300:]) + "</span></div>",
                    unsafe_allow_html=True)
        st.stop()
    slot.empty()

    if is_list:
        keep = [v for v in vids if scanner.SHINY_RE.search(v["title"])]
        if keep:
            st.markdown(f'<div class="note"><b>{len(keep)} of {len(vids)} videos</b> have shiny in the title and will be scanned.</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="note warn"><b>No shiny videos in the latest {len(vids)}.</b> '
                        "Raise the video count in Options to look further back.</div>", unsafe_allow_html=True)
    else:
        keep = vids

    summary_slot = st.container()
    summary = []
    for i, v in enumerate(keep, 1):
        slot = st.empty()
        live = st.empty()
        slot.markdown(work_html(v["title"], i, len(keep)), unsafe_allow_html=True)
        try:
            src = scanner.stream_url(v["url"], height)

            def on_progress(t, dur, v=v, i=i):
                slot.markdown(work_html(v["title"], i, len(keep), t, dur), unsafe_allow_html=True)

            def on_preview(frame, screens, how):
                with live.container():
                    st.caption(f"What the scanner sees right now ({len(screens)} game screen"
                               f"{'s' if len(screens) != 1 else ''}, found by: {how}). Green = game screen, "
                               "orange = where it looks for the sparkle.")
                    st.image(cv2.cvtColor(scanner.draw_layout(frame, screens), cv2.COLOR_BGR2RGB), width=520)

            r = scanner.scan_video(src, progress=on_progress, duration=v.get("duration"),
                                 regions=regions, style=style, on_preview=on_preview, ignore=ignore)
        except Exception as e:
            slot.empty()
            live.empty()
            st.markdown('<div class="note warn"><b>Skipped &ldquo;' + html.escape(v["title"] or v["url"]) +
                        "&rdquo;.</b><br><span class=\"err\">" +
                        html.escape(str(e)[-300:]) + "</span></div>", unsafe_allow_html=True)
            continue
        slot.empty()
        live.empty()

        st.markdown(card_html(v, r), unsafe_allow_html=True)
        if r["events"]:
            with st.expander(f"Screenshots of the {len(r['events'])} sparkle{'s' if len(r['events']) != 1 else ''}"):
                for e in r["events"]:
                    st.markdown(f"**Game {e['screen']}** (row {e['row']}, #{e['col']} from the left) at "
                                f"[{e['stamp']}]({link_at(v['url'], e['t'])})")
                    st.image(cv2.cvtColor(e["frame"], cv2.COLOR_BGR2RGB), width=520)
        with st.expander("What the scanner saw", expanded=not r["n_screens"]):
            if r["preview"]:
                st.caption("Green boxes are the game screens it found, numbered. The thin orange box is where it looks "
                           "for the sparkle. Something wrong? Type its number under Options, Ignore screens, or mark "
                           "the boxes yourself.")
                st.image(cv2.cvtColor(scanner.draw_layout(*r["preview"]), cv2.COLOR_BGR2RGB))
            else:
                st.caption("The video was too short to grab a picture from.")
        if r["chunks_without_layout"]:
            st.caption(f"{r['chunks_without_layout']} of {r['chunks']} five-minute sections had no game screens "
                       "(break or different scene) and were skipped.")
        k = len({(e["row"], e["col"]) for e in r["events"]})
        summary.append((v["title"], r["n_screens"], k))

    if len(summary) > 1:
        tot_s = sum(s[1] for s in summary)
        tot_k = sum(s[2] for s in summary)
        pct = 100.0 * tot_k / tot_s if tot_s else 0.0
        rows = "".join(
            f'<tr><td>{html.escape(t or "")}</td><td class="num">{n}</td><td class="num">{k}</td>'
            f'<td class="num">{(100.0 * k / n if n else 0):.0f}%</td></tr>' for t, n, k in summary)
        with summary_slot:
            st.markdown(
                '<div class="card"><div class="verdict hit"><span class="what">&#10022; Across '
                f'{len(summary)} videos: {tot_k} of {tot_s} games hit a shiny</span><span class="pct">{pct:.1f}%</span></div>'
                '<table class="sumtable"><tr><th>Video</th><th class="num">Games</th><th class="num">Shinies</th>'
                f'<th class="num">Percent</th></tr>{rows}</table></div>', unsafe_allow_html=True)
