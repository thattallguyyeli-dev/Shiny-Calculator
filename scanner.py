"""Shiny scanner: finds game windows (automatically or from boxes you set), then looks for the shiny sparkle."""
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


def _positions(profile, min_len, radius=3, cap=40):
    """Coordinates where a projected line mask is long enough to be a real border. Strongest peaks first,
    peaks closer than `radius` px to a stronger one are dropped, so neighbouring borders stay separate."""
    idx = np.where(profile >= min_len)[0]
    if idx.size == 0:
        return []
    order = idx[np.argsort(-profile[idx], kind="stable")]
    taken = []
    for i in order:
        if all(abs(int(i) - t) > radius for t in taken):
            taken.append(int(i))
            if len(taken) >= cap:
                break
    return sorted(taken)


def _side_cover(mask, x0, y0, x1, y1, horizontal, band=3):
    """Fraction of a rect side that has a line pixel within `band` px of it. A side on the edge of the frame
    counts as fully covered (games often run right up to the edge of the stream)."""
    H, W = mask.shape
    if horizontal:
        if y0 <= band or y0 >= H - 1 - band:
            return 1.0
        seg = mask[max(0, y0 - band):min(H, y0 + band + 1), max(0, x0):min(W, x1)]
        return float((seg.max(axis=0) > 0).mean()) if seg.size else 0.0
    if x0 <= band or x0 >= W - 1 - band:
        return 1.0
    seg = mask[max(0, y0):min(H, y1), max(0, x0 - band):min(W, x0 + band + 1)]
    return float((seg.max(axis=1) > 0).mean()) if seg.size else 0.0


def _has_content(g, e, x, y, w, h):
    """A game window is full of detail. Empty overlay background between windows is nearly flat."""
    gi = g[y + 3:y + h - 3, x + 3:x + w - 3]
    ei = e[y + 3:y + h - 3, x + 3:x + w - 3]
    if gi.size == 0:
        return False
    return float(gi.std()) >= 18 and float((ei > 0).mean()) >= 0.004


def _rects_one_frame(f):
    """Border-based rectangle finder. Finds long straight edges, then keeps every rectangle whose four sides are
    all mostly covered by them, whatever its size or position (GBA 3:2, DS 4:3, 16:9 ...).
    Overlays, webcams without a border and game UI are filtered by shape."""
    H, W = f.shape[:2]
    g = cv2.GaussianBlur(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (3, 3), 0)
    e = cv2.Canny(g, 40, 120)
    kh = max(15, W // 24)
    kv = max(15, H // 24)
    # bridge small gaps along each direction first (compression makes borders dashed), then keep only long runs
    eh = cv2.morphologyEx(e, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 1)))
    ev = cv2.morphologyEx(e, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 9)))
    hor = cv2.morphologyEx(eh, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (kh, 1)))
    ver = cv2.morphologyEx(ev, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, kv)))
    xs = sorted(set(_positions((ver > 0).sum(axis=0), kv * 2)) | {0, W - 1})
    ys = sorted(set(_positions((hor > 0).sum(axis=1), kh * 2)) | {0, H - 1})
    cand, wide = [], []
    for i, xl in enumerate(xs):
        for xr in xs[i + 1:]:
            w = xr - xl
            if w < 40 or w > 0.95 * W:
                continue
            for j, yt in enumerate(ys):
                for yb in ys[j + 1:]:
                    h = yb - yt
                    ar = w / float(h)
                    if h < 30 or not (1.15 <= ar <= 4.7):
                        continue
                    if not (0.012 < w * h / float(W * H) < 0.93):
                        continue
                    if ar > 2.1 and w * h / float(W * H) < 0.22:
                        continue          # small and wide: a health bar or dialog box, not a game
                    cov = min(_side_cover(hor, xl, yt, xr, yb, True), _side_cover(hor, xl, yb, xr, yt, True),
                              _side_cover(ver, xl, yt, xr, yb, False), _side_cover(ver, xr, yt, xl, yb, False))
                    if cov >= 0.85 and _has_content(g, e, xl, yt, w, h):
                        (wide if ar > 2.1 else cand).append((xl, yt, w, h))
    # nested candidates: keep the one whose shape looks most like a real game screen (3:2, 4:3, 16:10, 16:9);
    # on a tie the larger wins, so a window is not cut off at its own dialog box
    cand.sort(key=lambda r: -r[2] * r[3])
    keep = []
    for r in cand:
        dup = False
        for i, k in enumerate(keep):
            if _iou(r, k) > 0.8:
                dup = True
                break
            if _contained(r, k) > 0.9:
                inner, outer = (r, k) if r[2] * r[3] < k[2] * k[3] else (k, r)
                if _shape_score(inner) < _shape_score(outer) - 0.06 and inner[2] * inner[3] >= 0.8 * outer[2] * outer[3]:
                    keep[i] = inner
                else:
                    keep[i] = outer
                dup = True
                break
        if not dup:
            keep.append(r)
    # games placed side by side with no gap read as one wide block: split it into equal windows
    for r in sorted(wide, key=lambda r: -r[2] * r[3]):
        n = int(round(r[2] / (1.5 * r[3])))
        if n < 2 or not (1.25 <= (r[2] / n) / float(r[3]) <= 1.9):
            continue
        if sum(_contained(k, r) > 0.9 for k in keep) >= 2 or any(_iou(r, k) > 0.5 for k in keep):
            continue
        parts = [(r[0] + i * r[2] // n, r[1], r[2] // n, r[3]) for i in range(n)]
        if any(_contained(p, k) > 0.6 for p in parts for k in keep):
            continue
        keep.extend(parts)
    return keep


def _shape_score(r):
    """How far a rect's aspect ratio is from the common game-screen ratios (lower is better)."""
    ar = r[2] / float(r[3])
    return min(abs(ar - s) for s in (1.333, 1.5, 1.6, 1.778))


def _motion_rects(frames):
    """Fallback when no borders are visible: regions that keep changing (game animation), while overlays stay still."""
    if len(frames) < 3:
        return []
    H, W = frames[0].shape[:2]
    small = [cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (W // 4, H // 4)).astype(np.int16) for f in frames]
    act = np.zeros_like(small[0], dtype=np.float32)
    for a, b in zip(small[:-1], small[1:]):
        act += (np.abs(a - b) > 12)
    m = (act >= 2).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    m = cv2.dilate(m, np.ones((5, 5), np.uint8))
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cs:
        x, y, w, h = [v * 4 for v in cv2.boundingRect(c)]
        area = w * h / float(W * H)
        if 0.02 < area < 0.9 and 1.1 <= w / float(max(h, 1)) <= 2.2:
            out.append((x, y, w, h))
    return out


def find_screens(frames, allow_fallback=True):
    """Game windows that show up (same place) in at least half of the sampled frames.
    Returns (screens, method) where method is 'borders', 'motion' or 'whole frame'."""
    per = [_rects_one_frame(f) for f in frames]
    stable = []
    if per:
        ref = [r for p in per for r in p]
        for r in ref:
            hits = sum(any(_iou(r, q) > 0.8 for q in p) for p in per)
            if hits >= max(2, len(per) / 2.0) and not any(_iou(r, s) > 0.8 for s in stable):
                stable.append(r)
    stable.sort(key=lambda r: -r[2] * r[3])
    kept = []
    for r in stable:
        if not any(_iou(r, k) > 0.3 or _contained(r, k) > 0.7 for k in kept):
            kept.append(r)
    if kept:
        return _order(kept), "borders"
    if not allow_fallback or not frames:
        return [], "none"
    mot = _motion_rects(frames)
    if mot:
        mot.sort(key=lambda r: -r[2] * r[3])
        kept = []
        for r in mot:
            if not any(_iou(r, k) > 0.3 or _contained(r, k) > 0.7 for k in kept):
                kept.append(r)
        return _order(kept), "motion"
    H, W = frames[0].shape[:2]
    return _order([(0, 0, W, H)]), "whole frame"


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


def sparkle_score(now, old, style="gold"):
    """Number of small, NEW, star-like blobs in the enemy area (stars appearing out of nowhere).

    Two kinds of new pixel count:
      - gold stars: yellow pixels where the blue channel just dropped (Gen 3 stars are gold on a
        near-white background, so they are darker than what they cover and a brightness rise misses them)
      - bright stars: pixels that just got much brighter (white/blue sparkles)
    style "gold" only counts white/yellow as bright; style "any" counts any bright colour.
    """
    b, g, r = [c.astype(np.int16) for c in cv2.split(now)]
    bo = cv2.split(old)[0].astype(np.int16)
    gn = cv2.cvtColor(now, cv2.COLOR_BGR2GRAY).astype(np.int16)
    go = cv2.cvtColor(old, cv2.COLOR_BGR2GRAY).astype(np.int16)
    if style == "any":
        bright = gn > 185
    else:
        bright = (r > 200) & (g > 185)
    if (go > 235).mean() > 0.5:          # the earlier frame was a white flash: everything "reappearing" is not new
        return 0
    bright_new = bright & ((gn - go) > 50)
    gold_new = (r > 200) & (g > 170) & (b < 150) & ((r - b) > 90) & ((bo - b) > 50)
    new = bright_new | gold_new
    frac = new.mean()
    if frac > 0.05:                      # whole-area flash / transition, not stars
        return 0
    n, _, stats, _ = cv2.connectedComponentsWithStats(new.astype(np.uint8), connectivity=8)
    blobs = [s for s in stats[1:] if 6 <= s[cv2.CC_STAT_AREA] <= 160
             and s[cv2.CC_STAT_WIDTH] <= 22 and s[cv2.CC_STAT_HEIGHT] <= 22]
    return len(blobs)


# ---------------------------------------------------------------- manual game regions
def parse_regions(text):
    """Lines of 'x, y, width, height' in percent of the video frame -> list of (x, y, w, h) fractions."""
    out = []
    for n, line in enumerate((text or "").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p for p in re.split(r"[,\s]+", line.replace("%", "")) if p]
        try:
            x, y, w, h = [float(p) for p in parts]
        except ValueError:
            raise ValueError(f"Line {n} should be four numbers: x, y, width, height (percent). Got: {line}")
        if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > 100.5 or y + h > 100.5:
            raise ValueError(f"Line {n} goes outside the video (all values are percent, 0 to 100).")
        out.append((x / 100.0, y / 100.0, w / 100.0, h / 100.0))
    return out


def regions_to_screens(regions, W, H):
    rects = [(int(x * W), int(y * H), int(w * W), int(h * H)) for x, y, w, h in regions]
    return _order(rects)


def grab_frame(src, t=30.0):
    """One frame from the video at t seconds (used to preview the layout)."""
    w, h, dur = probe(src)
    if dur:
        t = min(t, max(0.0, dur - 1.0))
    cmd = [_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", *_net_args(src), "-ss", str(t), "-i", src,
           "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    out = subprocess.run(cmd, capture_output=True, timeout=120).stdout
    if len(out) < w * h * 3:
        raise RuntimeError("could not grab a frame from the video")
    return np.frombuffer(out[:w * h * 3], np.uint8).reshape(h, w, 3).copy()


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

    def __init__(self, threshold, style="gold"):
        self.threshold = threshold
        self.style = style
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
            hit = len(q) == self.back and sparkle_score(cur, q[0], self.style) >= self.threshold
            fl.append((t, f.copy() if hit else None))
            q.append(cur)
            recent = [a for a in fl if a[1] is not None]
            if len(recent) >= 2 and t - self.last_ev.get(s["id"], -999) > 45:
                self.last_ev[s["id"]] = t
                self.events.append({"screen": s["id"], "row": s["row"], "col": s["col"],
                                    "t": recent[0][0], "n_screens": len(screens),
                                    "frame": draw_layout(recent[-1][1], [s])})


def scan_video(src, progress=None, threshold=3, duration=None, regions=None, style="gold", on_preview=None, ignore=None):
    """src: a direct stream address (or a local file). Reads it once, in order, saving nothing.

    regions: optional list of (x, y, w, h) fractions of the frame. If given, those boxes are used as
    the game screens for the whole video instead of finding them automatically.
    """
    w, h, dur = probe(src)
    dur = dur or duration
    tracker = _Tracker(threshold, style)
    fixed = regions_to_screens(regions, w, h) if regions else None
    layouts, preview = {}, None
    cur_ci, layout, buf, prev_layout = -1, None, [], []
    layout_frames = int(LAYOUT_SECONDS * SAMPLE_FPS)

    methods = {}

    def decide(ci):
        nonlocal layout, buf, preview, prev_layout, first_look
        n = len(buf)
        idx = sorted({min(n - 1, int(n * q)) for q in (0.05, 0.2, 0.35, 0.5, 0.65, 0.8, 0.95)}) if n >= 3 else []
        pick = [buf[i][1] for i in idx]
        found, how = find_screens(pick) if pick else ([], "none")
        if how in ("motion", "whole frame") and prev_layout:
            found, how = prev_layout, "kept from earlier"
        if ignore:
            found = [x for x in found if x["id"] not in ignore]
        layout = found
        layouts[ci] = found
        methods[ci] = how
        mid = buf[n // 2][1].copy() if n else None
        if found:
            prev_layout = found
        # always keep a picture of what was seen, even when nothing was found
        if mid is not None and (first_look is None or (found and len(found) > len(first_look[1]))):
            first_look = (mid, found)
        if first_look is not None:
            preview = first_look
            if on_preview:
                try:
                    on_preview(first_look[0], first_look[1], how)
                except Exception:
                    pass
        for tb, fb in buf:
            tracker.feed(tb, fb, layout)
        buf = []

    first_look = None
    last_t = 0.0
    if fixed:
        layouts[0] = fixed
        for k, f in read_frames(src, w, h):
            t = k / float(SAMPLE_FPS)
            last_t = t
            if preview is None:
                preview = (f.copy(), fixed)
                if on_preview:
                    try:
                        on_preview(preview[0], fixed, "marked by you")
                    except Exception:
                        pass
            tracker.feed(t, f, fixed)
            if progress and k % (SAMPLE_FPS * 10) == 0:
                progress(t, dur)
    else:
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
    how = "marked by you" if fixed else (Counter(methods[c] for c, v in layouts.items() if v).most_common(1)[0][0]
                                          if any(layouts.values()) else "none")

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
            "preview": preview, "method": how, "chunks_without_layout": sum(1 for v in layouts.values() if not v),
            "chunks": max(1, len(layouts))}
