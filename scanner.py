"""Shiny scanner: finds game windows on its own, then looks for the Gen 3 shiny sparkle."""
import json, os, re, subprocess, tempfile, shutil
from collections import Counter, deque
import cv2
import numpy as np

# Title filter: shiny, shinies, shinys, shiney, sparkle, sparkles, sparkly, or the sparkle emoji
SHINY_RE = re.compile(r"\bshin(y|ie|ies|ey|ys|ny)|sparkl|\u2728", re.I)

CHUNK = 300          # seconds per layout re-check (the layout can change during a VOD)
LAYOUT_SECONDS = 10  # seconds of each chunk used to find the game windows
SAMPLE_FPS = 5       # frames analysed per second of video
ENEMY = (0.40, 1.00, 0.00, 0.62)   # x0,x1,y0,y1 of a game window where the wild Pokemon sits


# ---------------------------------------------------------------- yt-dlp
def _ytdlp(args):
    p = subprocess.run(["yt-dlp", *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[-600:] or "yt-dlp failed")
    return p.stdout


def list_videos(url, limit=30):
    """Returns (videos, is_list). Each video: title, url, duration."""
    info = json.loads(_ytdlp(["--flat-playlist", "--playlist-end", str(limit), "-J", url]))
    if info.get("entries") is not None:
        vids = [{"title": e.get("title") or "", "url": e.get("url") or e.get("webpage_url"),
                 "duration": e.get("duration")} for e in info["entries"] if e]
        return vids, True
    return [{"title": info.get("title") or "", "url": info.get("webpage_url") or url,
             "duration": info.get("duration")}], False


def stream_url(url, height=480):
    """Direct media address for the video. Nothing is downloaded here, it is only a link."""
    out = _ytdlp(["-f", f"bestvideo[height<={height}]/best[height<={height}]/worst",
                  "--no-playlist", "-g", url])
    lines = [l for l in out.strip().splitlines() if l.strip()]
    if not lines:
        raise RuntimeError("no playable stream found for this link")
    return lines[0]


def _ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        exe = shutil.which("ffmpeg")
        if not exe:
            raise RuntimeError("ffmpeg not found. Run: pip install imageio-ffmpeg")
        return exe


def _net_args(src):
    if src.startswith("http"):
        return ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
    return []


def probe(src):
    """(width, height, duration_seconds or None) read from ffmpeg's banner."""
    p = subprocess.run([_ffmpeg_exe(), "-hide_banner", *_net_args(src), "-i", src],
                       capture_output=True, text=True, timeout=90)
    txt = p.stderr
    m = re.search(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})", txt)
    if not m:
        raise RuntimeError("could not read the video stream")
    d = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", txt)
    dur = int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3)) if d else None
    return int(m.group(1)), int(m.group(2)), dur


def read_frames(src, w, h):
    """Yields (frame_number, BGR frame) at SAMPLE_FPS, straight from the stream (no file is written)."""
    cmd = [_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", *_net_args(src), "-i", src,
           "-an", "-sn", "-vf", f"fps={SAMPLE_FPS}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=w * h * 3 * 2)
    size = w * h * 3
    k = 0
    try:
        while True:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            yield k, np.frombuffer(buf, np.uint8).reshape(h, w, 3)
            k += 1
    finally:
        p.kill()
        p.wait()


# ---------------------------------------------------------------- finding the game windows
def _iou(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / float(aw * ah + bw * bh - inter + 1e-9)


def _contained(a, b):
    """fraction of the smaller rect that lies inside the other"""
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    return ix * iy / float(min(aw * ah, bw * bh) + 1e-9)


def _rects_one_frame(f):
    H, W = f.shape[:2]
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    e = cv2.Canny(g, 60, 160)
    e = cv2.dilate(e, np.ones((3, 3), np.uint8), iterations=2)
    e = cv2.morphologyEx(e, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    cs, _ = cv2.findContours(e, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cs:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h / float(W * H)
        if not (0.012 < area < 0.30) or h == 0:
            continue
        if not (1.35 <= w / float(h) <= 1.65):       # GBA screen is 3:2
            continue
        if cv2.contourArea(c) / float(w * h) < 0.55:  # must be a solid block, not a ring
            continue
        out.append((x, y, w, h))
    return out


def find_screens(frames):
    """Rects that show up (same place) in at least half of the sampled frames."""
    per = [_rects_one_frame(f) for f in frames]
    if not per or not per[0] and len(per) == 1:
        return []
    ref = [r for p in per for r in p]
    stable = []
    for r in ref:
        hits = sum(any(_iou(r, q) > 0.8 for q in p) for p in per)
        if hits >= max(2, len(per) / 2.0) and not any(_iou(r, s) > 0.8 for s in stable):
            stable.append(r)
    stable.sort(key=lambda r: -r[2] * r[3])
    kept = []
    for r in stable:
        if not any(_iou(r, k) > 0.3 or _contained(r, k) > 0.7 for k in kept):
            kept.append(r)
    return _order(kept)


def _order(rects):
    if not rects:
        return []
    mh = float(np.median([r[3] for r in rects]))
    rects = sorted(rects, key=lambda r: r[1] + r[3] / 2)
    rows, cur = [], [rects[0]]
    for r in rects[1:]:
        if abs((r[1] + r[3] / 2) - np.mean([q[1] + q[3] / 2 for q in cur])) < 0.5 * mh:
            cur.append(r)
        else:
            rows.append(cur); cur = [r]
    rows.append(cur)
    out = []
    for ri, row in enumerate(rows, 1):
        for ci, r in enumerate(sorted(row, key=lambda r: r[0]), 1):
            out.append({"rect": tuple(int(v) for v in r), "row": ri, "col": ci})
    for i, s in enumerate(out, 1):
        s["id"] = i
    return out


# ---------------------------------------------------------------- sparkle detection
def _prep(crop):
    return cv2.resize(crop, (128, 96), interpolation=cv2.INTER_AREA)


def sparkle_score(now, old):
    """Number of small, NEW, white/yellow blobs in the enemy area (stars appearing out of nowhere)."""
    b, g, r = cv2.split(now)
    bright = (r > 200) & (g > 185)
    gn = cv2.cvtColor(now, cv2.COLOR_BGR2GRAY).astype(np.int16)
    go = cv2.cvtColor(old, cv2.COLOR_BGR2GRAY).astype(np.int16)
    new = bright & ((gn - go) > 50)
    frac = new.mean()
    if frac > 0.05:                      # whole-area flash / transition, not stars
        return 0
    n, _, stats, _ = cv2.connectedComponentsWithStats(new.astype(np.uint8), connectivity=8)
    blobs = [s for s in stats[1:] if 6 <= s[cv2.CC_STAT_AREA] <= 160
             and s[cv2.CC_STAT_WIDTH] <= 22 and s[cv2.CC_STAT_HEIGHT] <= 22]
    return len(blobs)


def _stamp(sec):
    s = int(sec); return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def draw_layout(frame, screens):
    img = frame.copy()
    for s in screens:
        x, y, w, h = s["rect"]
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
        ex0, ex1, ey0, ey1 = ENEMY
        cv2.rectangle(img, (int(x + ex0 * w), int(y + ey0 * h)), (int(x + ex1 * w), int(y + ey1 * h)), (0, 200, 255), 1)
        cv2.putText(img, str(s["id"]), (x + 6, y + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    return img


class _Tracker:
    """Per-screen sparkle memory. Fed one sampled frame at a time."""

    def __init__(self, threshold):
        self.threshold = threshold
        self.back = max(2, int(round(0.8 * SAMPLE_FPS)))
        self.hist, self.flags, self.last_ev, self.events = {}, {}, {}, []
        self.key = None

    def feed(self, t, f, screens):
        key = tuple(s["rect"] for s in screens)
        if key != self.key:
            self.hist, self.flags, self.key = {}, {}, key
        H, W = f.shape[:2]
        for s in screens:
            x, y, w, h = s["rect"]
            ex0, ex1, ey0, ey1 = ENEMY
            crop = f[max(0, int(y + ey0 * h)):min(H, int(y + ey1 * h)),
                     max(0, int(x + ex0 * w)):min(W, int(x + ex1 * w))]
            if crop.size == 0:
                continue
            cur = _prep(crop)
            q = self.hist.setdefault(s["id"], deque(maxlen=self.back))
            fl = self.flags.setdefault(s["id"], deque(maxlen=3))
            hit = len(q) == self.back and sparkle_score(cur, q[0]) >= self.threshold
            fl.append((t, f.copy() if hit else None))
            q.append(cur)
            recent = [a for a in fl if a[1] is not None]
            if len(recent) >= 2 and t - self.last_ev.get(s["id"], -999) > 45:
                self.last_ev[s["id"]] = t
                self.events.append({"screen": s["id"], "row": s["row"], "col": s["col"],
                                    "t": recent[0][0], "n_screens": len(screens),
                                    "frame": draw_layout(recent[-1][1], [s])})


def scan_video(src, progress=None, threshold=3, duration=None):
    """src: a direct stream address (or a local file). Reads it once, in order, saving nothing."""
    w, h, dur = probe(src)
    dur = dur or duration
    tracker = _Tracker(threshold)
    layouts, preview = {}, None
    cur_ci, layout, buf, prev_layout = -1, None, [], []
    layout_frames = int(LAYOUT_SECONDS * SAMPLE_FPS)

    def decide(ci):
        nonlocal layout, buf, preview, prev_layout
        pick = [buf[i][1] for i in (len(buf) // 5, len(buf) // 2, (len(buf) * 4) // 5)] if len(buf) >= 3 else []
        found = find_screens(pick) if pick else []
        if not found and prev_layout:
            found = prev_layout            # brief scene change: keep the last known layout
        layout = found
        layouts[ci] = found
        if found:
            prev_layout = found
            if preview is None or len(found) > len(preview[1]):
                preview = (buf[len(buf) // 2][1].copy(), found)
        for tb, fb in buf:
            tracker.feed(tb, fb, layout)
        buf = []

    last_t = 0.0
    for k, f in read_frames(src, w, h):
        t = k / float(SAMPLE_FPS)
        last_t = t
        ci = int(t // CHUNK)
        if ci != cur_ci:
            if layout is None and buf:
                decide(cur_ci)
            cur_ci, layout, buf = ci, None, []
        if layout is None:
            buf.append((t, f))
            if len(buf) >= layout_frames:
                decide(ci)
        else:
            tracker.feed(t, f, layout)
        if progress and k % (SAMPLE_FPS * 10) == 0:
            progress(t, dur)
    if layout is None and buf:
        decide(cur_ci)

    counts = Counter(len(v) for v in layouts.values() if v)
    n_screens = counts.most_common(1)[0][0] if counts else 0
    modal = next((v for v in layouts.values() if len(v) == n_screens and v), [])

    # drop stream-wide flashes (several windows "sparkling" at once = transition, not a shiny)
    events = sorted(tracker.events, key=lambda e: e["t"])
    clean = []
    for e in events:
        group = {o["screen"] for o in events if abs(o["t"] - e["t"]) <= 3}
        if e["n_screens"] >= 2 and len(group) >= max(2, 0.6 * e["n_screens"]):
            continue
        clean.append(e)
    for e in clean:
        e["stamp"] = _stamp(e["t"])
    return {"duration": dur or last_t, "n_screens": n_screens, "layout": modal, "events": clean,
            "preview": preview, "chunks_without_layout": sum(1 for v in layouts.values() if not v),
            "chunks": max(1, len(layouts))}
