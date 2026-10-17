#!/usr/bin/env python3
"""L'Artisan KANOYA — 「ある日のディナーより」京鴨ロース Instagram リール (1080x1920 / 30秒)

使い方:
  python3 video/make_kyogamo_reel.py --fonts <フォントのディレクトリ> [--out video/kyogamo_reel.mp4]

必要なフォント (Google Fonts, OFL):
  ShipporiMincho-Regular.ttf / ShipporiMincho-Medium.ttf
  Cormorant.ttf (CormorantGaramond[wght]) / CormorantItalic.ttf (CormorantGaramond-Italic[wght])
"""
import argparse
import math
import os
import subprocess
import sys
import unicodedata
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS, DURATION = 1080, 1920, 30, 30.0
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(ROOT, "images")
GOLD = (214, 186, 132)
WHITE = (250, 246, 238)
TR = 0.8  # トランジションの長さ(秒)


def img_path(num):
    for f in os.listdir(IMG_DIR):
        if unicodedata.normalize("NFC", f).endswith(f"{num}.jpg"):
            return os.path.join(IMG_DIR, f)
    raise FileNotFoundError(num)


# ---------------------------------------------------------------- easing
def clamp01(x):
    return max(0.0, min(1.0, x))


def ease_io(x):
    x = clamp01(x)
    return x * x * (3 - 2 * x)


def ease_cubic(x):
    x = clamp01(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_out(x):
    x = clamp01(x)
    return 1 - (1 - x) ** 3


def lerp(a, b, t):
    return a + (b - a) * t


# ---------------------------------------------------------------- scenes
# kb: (中心x, 中心y, 見える幅[画像幅比]) の開始→終了。テキスト位置は "top" / "bottom" / "center"。
SCENES = [
    dict(img="0240", t0=0.0, t1=4.6, kb=((0.50, 0.50, 0.84), (0.51, 0.60, 0.64)), trans_in="fadeblack",
         text=dict(pos="top", y=400, items=[
             ("chars", "L'ARTISAN KANOYA", "corm", 48, GOLD, 12, 0.7),
             ("line", 150, 1.3),
             ("chars", "ある日のディナーより", "mincho", 64, WHITE, 14, 1.5),
         ])),
    dict(img="0253", t0=3.8, t1=8.4, editorial=True, trans_in="blur",
         text=dict(pos="editorial", y=1150, items=[
             ("chars", "Un dîner, un jour", "cormi", 58, GOLD, 2, 1.0),
             ("chars", "素材の声を、ひと皿に。", "mincho", 48, WHITE, 10, 1.4),
         ])),
    dict(img="0257", t0=7.6, t1=12.2, kb=((0.50, 0.50, 0.72), (0.49, 0.56, 0.54)), trans_in="leak",
         text=dict(pos="top", y=300, ingredient=("Canard de Kyoto", "京鴨ロース", "皮目は香ばしく、身はしっとりと"))),
    dict(img="0259", t0=11.4, t1=16.0, kb=((0.47, 0.60, 0.62), (0.34, 0.70, 0.44)), trans_in="wipe",
         text=dict(pos="top", y=300, ingredient=("Sel de Guérande", "ゲランドの塩", "ブルターニュの海が育む、まろやかな塩"))),
    dict(img="0261", t0=15.2, t1=19.8, kb=((0.48, 0.66, 0.58), (0.42, 0.76, 0.44)), trans_in="push",
         text=dict(pos="bottom", y=1170, ingredient=("Ail noir", "黒にんにく", "熟成が生む、深い甘みとコク"))),
    dict(img="0244", t0=19.0, t1=23.6, kb=((0.52, 0.55, 0.375), (0.62, 0.64, 0.30)), trans_in="zoom",
         text=dict(pos="top", y=300, ingredient=("Riz rouge", "赤米", "噛むほどに広がる、香ばしい余韻"))),
    dict(img="0249", t0=22.8, t1=27.6, kb=((0.50, 0.52, 0.84), (0.50, 0.58, 0.72)), trans_in="leak",
         text=dict(pos="top", y=270, items=[
             ("chars", "ある日のディナーより", "mincho", 40, GOLD, 12, 0.9),
             ("chars", "京鴨ロース", "mincho_m", 86, WHITE, 18, 1.2),
             ("line", 150, 1.8),
             ("chars", "ゲランドの塩、黒にんにく、赤米", "mincho", 42, WHITE, 6, 2.0),
         ])),
    dict(img="0263", t0=26.8, t1=30.0, endcard=True, trans_in="fade",
         text=dict(pos="center", y=760, items=[
             ("chars", "L'Artisan", "cormi", 124, WHITE, 2, 0.5),
             ("chars", "KANOYA", "corm", 62, GOLD, 34, 0.9),
             ("line", 150, 1.2),
             ("chars", "またのお越しを、お待ちしております", "mincho", 34, WHITE, 6, 1.4),
         ])),
]


def ingredient_items(label, title, sub):
    return [
        ("chars", label, "cormi", 54, GOLD, 2, 1.0),
        ("chars", title, "mincho_m", 96, WHITE, 20, 1.2),
        ("line", 130, 1.7),
        ("chars", sub, "mincho", 38, WHITE, 6, 2.0),
    ]


# ---------------------------------------------------------------- resources (各ワーカーで1回だけ)
R = {}


def init_resources(font_dir):
    fonts = {
        "mincho": os.path.join(font_dir, "ShipporiMincho-Regular.ttf"),
        "mincho_m": os.path.join(font_dir, "ShipporiMincho-Medium.ttf"),
        "corm": os.path.join(font_dir, "Cormorant.ttf"),
        "cormi": os.path.join(font_dir, "CormorantItalic.ttf"),
    }
    R["fonts"] = fonts
    R["src"] = {}
    for sc in SCENES:
        im = Image.open(img_path(sc["img"])).convert("RGB")
        long_side = 3000
        s = long_side / max(im.size)
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
        R["src"][sc["img"]] = grade(im)
        if sc.get("editorial") or sc.get("endcard"):
            R.setdefault("bg", {})[sc["img"]] = blurred_bg(R["src"][sc["img"]], 0.42 if sc.get("editorial") else 0.30)
    # ビネット
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H / 2) / (H * 0.62)) ** 2)
    R["vig"] = np.clip(1.0 - 0.38 * np.clip(d - 0.45, 0, None) ** 1.6, 0.55, 1.0)[..., None]
    rng = np.random.default_rng(7)
    R["grain"] = [rng.normal(0, 5.0, (H // 2, W // 2)).astype(np.float32) for _ in range(6)]
    # テキストのレイヤー
    R["text"] = {}
    for i, sc in enumerate(SCENES):
        R["text"][i] = build_text(sc["text"])


def grade(im):
    """暗部を少し持ち上げ、ハイライトをほんのり暖色に。"""
    a = np.asarray(im).astype(np.float32) / 255.0
    a = 0.03 + a * 0.97
    a = a ** np.array([0.98, 1.0, 1.04], dtype=np.float32)  # R少し明るく、B少し沈める
    luma = a.mean(axis=2, keepdims=True)
    a = luma + (a - luma) * 1.06
    return Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8))


def blurred_bg(im, darken):
    s = max(W * 1.15 / im.width, H * 1.15 / im.height)
    bg = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    bg = bg.resize((bg.width // 6, bg.height // 6), Image.LANCZOS).filter(ImageFilter.GaussianBlur(14))
    bg = bg.resize((round(im.width * s), round(im.height * s)), Image.BICUBIC)
    a = np.asarray(bg).astype(np.float32) * darken
    return Image.fromarray(a.astype(np.uint8))


# ---------------------------------------------------------------- text
def font(key, size):
    f = ImageFont.truetype(R["fonts"][key], size)
    if key == "corm":
        f.set_variation_by_axes([500])
    elif key == "cormi":
        f.set_variation_by_axes([450])
    return f


def build_text(spec):
    items = spec.get("items") or ingredient_items(*spec["ingredient"])
    y = spec["y"]
    layers = []
    for it in items:
        if it[0] == "line":
            layers.append(dict(kind="line", y=y + 6, w=it[1], t=it[2]))
            y += 44
            continue
        _, text, fkey, size, color, spacing, t = it
        f = font(fkey, size)
        glyphs = []
        widths = [f.getlength(c) for c in text]
        total = sum(widths) + spacing * (len(text) - 1)
        x = (W - total) / 2
        pad = int(size * 0.6)
        asc, desc = f.getmetrics()
        for c, cw in zip(text, widths):
            if c.strip():
                gw, gh = int(cw + pad * 2), asc + desc + pad * 2
                g = Image.new("L", (gw, gh), 0)
                ImageDraw.Draw(g).text((pad, pad), c, font=f, fill=255)
                glyphs.append((round(x - pad), y - pad, g))
            x += cw + spacing
        layers.append(dict(kind="chars", glyphs=glyphs, color=color, t=t, size=size,
                           stagger=0.07 if len(glyphs) < 12 else 0.035))
        y += int((asc + desc) * (1.25 if size > 70 else 1.45))
    return dict(layers=layers, top=spec["y"] - 40, bottom=y + 20, pos=spec["pos"])


def draw_text(frame, sc, idx, t_rel, dur):
    """frame: RGBA。シーン先頭からの経過 t_rel で文字をアニメーション。"""
    td = R["text"][idx]
    is_end = sc.get("endcard")
    out_t = dur - TR - 0.15
    fade_out = 1.0 if is_end else 1.0 - ease_io((t_rel - (out_t - 0.5)) / 0.5)
    if fade_out <= 0:
        return frame
    # 文字を読みやすくするための柔らかいグラデーション
    first = min(l["t"] for l in td["layers"])
    g_a = ease_io((t_rel - first + 0.4) / 0.8) * fade_out
    if g_a > 0 and td["pos"] in ("top", "bottom"):
        frame.alpha_composite(gradient_band(td, g_a))
    shadow = Image.new("L", frame.size, 0)
    fill = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    for l in td["layers"]:
        if l["kind"] == "line":
            p = ease_out((t_rel - l["t"]) / 0.9)
            if p <= 0:
                continue
            half = l["w"] * p / 2
            a = int(255 * fade_out * min(1, p * 2))
            d = ImageDraw.Draw(fill)
            d.line([(W / 2 - half, l["y"]), (W / 2 + half, l["y"])], fill=GOLD + (a,), width=2)
            continue
        for k, (gx, gy, g) in enumerate(l["glyphs"]):
            p = (t_rel - l["t"] - k * l["stagger"]) / 0.7
            if p <= 0:
                continue
            e = ease_out(p)
            a = e * fade_out
            dy = round((1 - e) * l["size"] * 0.35)
            ga = g.point(lambda v, a=a: int(v * a))
            shadow.paste(255, (gx, gy + dy + 3), ga)
            col = Image.new("RGBA", g.size, l["color"] + (0,))
            col.putalpha(ga)
            fill.alpha_composite(col, (gx, gy + dy))
    sh = shadow.resize((W // 4, H // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(3)).resize((W, H), Image.BILINEAR)
    sh_layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    sh_layer.putalpha(sh.point(lambda v: int(v * 0.8)))
    frame.alpha_composite(sh_layer)
    frame.alpha_composite(fill)
    return frame


_grad_cache = {}


def gradient_band(td, alpha):
    key = (td["top"], td["bottom"], td["pos"])
    if key not in _grad_cache:
        y = np.arange(H, dtype=np.float32)
        if td["pos"] == "top":
            edge = td["bottom"] + 360
            m = np.clip((edge - y) / (edge - 0), 0, 1) ** 1.1
        else:
            edge = td["top"] - 260
            m = np.clip((y - edge) / (H - edge), 0, 1) ** 1.0
            m = np.minimum(m * 1.6, 1.0)
        _grad_cache[key] = (m * 0.78)[:, None]
    m = (_grad_cache[key] * alpha * 255).astype(np.uint8)
    a = np.repeat(m, W, axis=1)
    layer = np.zeros((H, W, 4), np.uint8)
    layer[..., 3] = a
    return Image.fromarray(layer, "RGBA")


# ---------------------------------------------------------------- scene frame
def kb_crop(src, c, out=(W, H), resample=Image.BICUBIC):
    sw, sh = src.size
    cx, cy, wf = c
    w = wf * sw
    h = w * out[1] / out[0]
    if h > sh:
        h = sh
        w = h * out[0] / out[1]
    cx = min(max(cx * sw, w / 2), sw - w / 2)
    cy = min(max(cy * sh, h / 2), sh - h / 2)
    s = w / out[0]
    return src.transform(out, Image.AFFINE, (s, 0, cx - w / 2, 0, s, cy - h / 2), resample=resample)


def scene_frame(idx, t):
    sc = SCENES[idx]
    dur = sc["t1"] - sc["t0"]
    t_rel = t - sc["t0"]
    p = clamp01(t_rel / dur)
    src = R["src"][sc["img"]]
    if sc.get("editorial"):
        bg = R["bg"][sc["img"]]
        frame = kb_crop(bg, (0.5, 0.5, lerp(0.92, 0.84, p)))
        fw, fh = 960, 640
        z = lerp(1.0, 0.9, p)
        fg = kb_crop(src, (0.5, 0.48, z), out=(fw, fh))
        x0, y0 = (W - fw) // 2, 430
        shadow = Image.new("L", (W, H), 0)
        ImageDraw.Draw(shadow).rectangle([x0 + 10, y0 + 24, x0 + fw - 10, y0 + fh + 24], fill=170)
        shadow = shadow.resize((W // 8, H // 8)).filter(ImageFilter.GaussianBlur(4)).resize((W, H), Image.BILINEAR)
        frame.paste((0, 0, 0), (0, 0), shadow)
        frame.paste(fg, (x0, y0))
        ImageDraw.Draw(frame).rectangle([x0 - 14, y0 - 14, x0 + fw + 13, y0 + fh + 13], outline=GOLD, width=1)
    elif sc.get("endcard"):
        frame = kb_crop(R["bg"][sc["img"]], (0.5, 0.5, lerp(0.86, 0.78, p)))
    else:
        (a, b) = sc["kb"]
        frame = kb_crop(src, tuple(lerp(a[i], b[i], p) for i in range(3)))
    frame = frame.convert("RGBA")
    frame = draw_text(frame, sc, idx, t_rel, dur)
    return frame.convert("RGB")


# ---------------------------------------------------------------- transitions
def zoom_img(im, z):
    return kb_crop(im, (0.5, 0.5, 1 / z), resample=Image.BILINEAR)


def blur_img(im, r):
    if r < 0.5:
        return im
    small = im.resize((W // 4, H // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(r / 4))
    return small.resize((W, H), Image.BILINEAR)


_leak = {}


def leak_layer(q):
    """暖色のライトリーク。q: 0→1 で左下から右上へ流れる。"""
    if "xx" not in _leak:
        yy, xx = np.mgrid[0:H // 4, 0:W // 4].astype(np.float32)
        _leak["xx"], _leak["yy"] = xx * 4, yy * 4
    xx, yy = _leak["xx"], _leak["yy"]
    cx = lerp(-0.3 * W, 1.3 * W, q)
    cy = lerp(1.1 * H, 0.1 * H, q)
    d = np.sqrt(((xx - cx) / (W * 0.75)) ** 2 + ((yy - cy) / (H * 0.55)) ** 2)
    m = np.exp(-d * d * 2.2)
    inten = math.sin(math.pi * q) ** 1.2
    col = np.array([255, 170, 95], np.float32)
    small = (m[..., None] * col * inten * 0.9).astype(np.uint8)
    return np.asarray(Image.fromarray(small).resize((W, H), Image.BILINEAR)).astype(np.float32)


def transition(kind, A, B, q):
    e = ease_cubic(q)
    if kind == "blur":
        r = 28 * math.sin(math.pi * q)
        A2, B2 = blur_img(A, r), blur_img(B, r)
        return Image.blend(A2, B2, ease_io((q - 0.25) / 0.5))
    if kind == "leak":
        m = Image.blend(A, B, ease_io((q - 0.2) / 0.6))
        a = np.asarray(m).astype(np.float32)
        L = leak_layer(q)
        a = 255 - (255 - a) * (255 - L) / 255  # スクリーン合成
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    if kind == "wipe":
        # 斜めのソフトエッジ・ワイプ
        if "wd" not in _leak:
            yy, xx = np.mgrid[0:H // 4, 0:W // 4].astype(np.float32)
            _leak["wd"] = (xx * 4 / W) * 0.6 + (1 - yy * 4 / H) * 0.4
        edge = lerp(-0.25, 1.25, e)
        m = np.clip((edge - _leak["wd"]) / 0.22, 0, 1)
        mask = Image.fromarray((m * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)
        A2 = zoom_img(A, 1 + 0.04 * e)
        return Image.composite(B, A2, mask)
    if kind == "push":
        off = round(H * e)
        out = Image.new("RGB", (W, H))
        out.paste(A, (0, -off))
        out.paste(B, (0, H - off))
        # 継ぎ目にうっすら金のライン
        if 0 < off < H:
            ImageDraw.Draw(out).line([(0, H - off), (W, H - off)], fill=GOLD, width=2)
        return out
    if kind == "zoom":
        A2 = zoom_img(A, 1 + 0.35 * ease_io(q))
        A2 = blur_img(A2, 18 * ease_io(q))
        B2 = zoom_img(B, 1.18 - 0.18 * ease_out(q))
        return Image.blend(A2, B2, ease_io((q - 0.15) / 0.7))
    return Image.blend(A, B, ease_io(q))


# ---------------------------------------------------------------- frame
def render(fi):
    t = fi / FPS
    active = [i for i, sc in enumerate(SCENES) if sc["t0"] <= t < sc["t1"] + 1e-9]
    if not active:
        active = [len(SCENES) - 1]
    if len(active) >= 2:
        a, b = active[-2], active[-1]
        q = (t - SCENES[b]["t0"]) / (SCENES[a]["t1"] - SCENES[b]["t0"])
        frame = transition(SCENES[b]["trans_in"], scene_frame(a, t), scene_frame(b, t), q)
    else:
        frame = scene_frame(active[0], t)
    arr = np.asarray(frame).astype(np.float32)
    arr *= R["vig"]
    g = R["grain"][fi % len(R["grain"])]
    arr += np.repeat(np.repeat(g, 2, 0), 2, 1)[..., None]
    # 冒頭はブラックから、ラストはブラックへ
    k = ease_io(t / 1.2) * (1 - ease_io((t - (DURATION - 0.6)) / 0.6))
    arr *= k
    return np.clip(arr, 0, 255).astype(np.uint8).tobytes()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonts", required=True)
    ap.add_argument("--out", default=os.path.join(ROOT, "video", "kyogamo_reel.mp4"))
    ap.add_argument("--stills", help="指定した秒数のフレームをPNGで書き出す (例: 2,6,10)")
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    args = ap.parse_args()

    if args.stills:
        init_resources(args.fonts)
        for s in args.stills.split(","):
            fi = round(float(s) * FPS)
            Image.frombytes("RGB", (W, H), render(fi)).save(f"{args.out}_{s}.png")
        return

    n = round(DURATION * FPS)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
           "-map", "0:v", "-map", "1:a", "-shortest",
           "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-maxrate", "14M", "-bufsize", "28M", "-pix_fmt", "yuv420p",
           "-profile:v", "high", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", args.out]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(args.workers, initializer=init_resources, initargs=(args.fonts,)) as pool:
        for i, buf in enumerate(pool.imap(render, range(n), chunksize=4)):
            ff.stdin.write(buf)
            if i % 60 == 0:
                print(f"frame {i}/{n}", file=sys.stderr, flush=True)
    ff.stdin.close()
    sys.exit(ff.wait())


if __name__ == "__main__":
    main()
