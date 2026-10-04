# -*- coding: utf-8 -*-
"""生成 README 用的演示图。合成一张假的「桌面」场景，不暴露真实桌面内容。

用法：  python tools/make_demo.py
产物：  assets/demo.png（静态）  assets/demo.gif（气泡弹出 + 逐字打字 + 点击弹跳）
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
W, H = 1080, 620
NAVY = (32, 49, 112)
CARD = (255, 255, 255)
BORDER = (216, 222, 232)
TEXT = (24, 34, 48)
MUTED = (150, 160, 175)
ACCENT = (84, 174, 255)


def font(size, bold=False):
    for name in (("msyhbd.ttc",) if bold else ()) + ("msyh.ttc", "simhei.ttf", "simsun.ttc"):
        p = Path(r"C:\Windows\Fonts") / name
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                pass
    return ImageFont.load_default()


def backdrop():
    bg = Image.new("RGB", (W, H), (24, 34, 58))
    d = ImageDraw.Draw(bg)
    for y in range(H):
        k = y / H
        d.line([(0, y), (W, y)], fill=(int(28 + 40 * k), int(38 + 26 * k), int(70 + 46 * k)))
    for i in range(0, W + H, 46):
        d.line([(i, 0), (i - H, H)], fill=(40, 52, 84))

    card = Image.new("RGBA", (430, 320), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    cd.rounded_rectangle([0, 0, 429, 319], radius=14, fill=(255, 255, 255, 236))
    cd.rounded_rectangle([0, 0, 429, 44], radius=14, fill=(240, 243, 250, 255))
    cd.rectangle([0, 30, 429, 44], fill=(240, 243, 250, 255))
    for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        cd.ellipse([18 + i * 20, 15, 30 + i * 20, 27], fill=c)
    cd.text((22, 70), "今天的任务", font=font(15), fill=(40, 52, 78))
    for i in range(5):
        y = 106 + i * 32
        cd.rounded_rectangle([22, y, 22 + (280 - i * 32), y + 11], radius=5, fill=(206, 214, 230, 255))
    cd.rounded_rectangle([22, 276, 190, 300], radius=7, fill=ACCENT)
    bg.paste(card, (60, 150), card)
    d.text((62, 500), "透明背景 → 直接贴在桌面上，没有窗口边框",
           font=font(17), fill=(178, 194, 224))
    return bg.convert("RGBA")


def bubble_img(text, width=250):
    """把文字画进气泡底图的白色椭圆内部（和程序里同一套比例）。"""
    b = Image.open(ASSETS / "bubble.png").convert("RGBA")
    b = b.resize((width, int(b.height * width / b.width)), Image.LANCZOS)
    d = ImageDraw.Draw(b)
    px, py = int(b.width * 0.10), int(b.height * 0.09)
    cx = b.width / 2
    cy = (py + b.height * 0.60) / 2
    d.multiline_text((cx, cy), text, font=font(13), fill=NAVY,
                     anchor="mm", align="center", spacing=4)
    return b


MENU_ITEMS = [
    ("亲密值 73 / 100", "hint"),
    ("今日：已点击 · 未对话", "hint"),
    ("-", "sep"),
    ("番茄钟", "sub"),
    ("窗口大小", "sub"),
    ("音效音量", "sub"),
    ("窗口置顶", "check"),
    ("-", "sep"),
    ("退出", "cmd"),
]


def menu_img(width=200):
    f = font(15)
    row_h, sep_h, pad = 34, 13, 8
    height = pad * 2 + sum(sep_h if t == "sep" else row_h for _, t in MENU_ITEMS)
    card = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([0, 0, width - 1, height - 1], radius=12,
                        fill=CARD + (255,), outline=BORDER + (255,), width=1)
    y = pad
    for label, kind in MENU_ITEMS:
        if kind == "sep":
            d.line([(12, y + sep_h // 2), (width - 13, y + sep_h // 2)], fill=BORDER, width=1)
            y += sep_h
            continue
        if kind == "hint":                      # 灰色信息行
            d.text((20, y + 9), label, font=f, fill=MUTED)
        else:
            hover = (label == "番茄钟")
            if hover:
                d.rounded_rectangle([8, y, width - 9, y + row_h], radius=6, fill=(243, 245, 248))
            if kind == "check":          # 对勾用折线画（中文字体缺 U+2713）
                cy = y + row_h // 2
                d.line([(8, cy), (12, cy + 4), (18, cy - 5)], fill=NAVY, width=2, joint="curve")
            d.text((20, y + 9), label, font=f, fill=ACCENT if hover else TEXT)
            if kind == "sub":
                cy = y + row_h // 2
                d.polygon([(width - 22, cy - 4), (width - 22, cy + 4), (width - 14, cy)], fill=NAVY)
        y += row_h
    return card


CHAR = Image.open(ASSETS / "pet_character.png").convert("RGBA")


def pet_at(canvas, size, x, y, squash=1.0):
    w = max(1, int(size * (2.0 - squash)))
    h = max(1, int(size * squash))
    im = CHAR.resize((w, h), Image.LANCZOS)
    canvas.paste(im, (int(x + (size - w) / 2), int(y + (size - h))), im)


def make_png():
    canvas = backdrop()
    pet_at(canvas, 300, 250, 250)
    b = bubble_img("哼，才不是特意在这里等你的呢。")
    canvas.paste(b, (250 + 150 - b.width // 2, 250 - 18 - b.height), b)
    m = menu_img()
    canvas.paste(m, (680, 80), m)
    ImageDraw.Draw(canvas).text((686, 80 + m.height + 12), "自绘圆角菜单，跟随系统深浅色",
                                font=font(15), fill=(178, 194, 224))
    canvas.convert("RGB").save(ASSETS / "demo.png")
    print("saved assets/demo.png", canvas.size)


def make_gif():
    base = backdrop()
    m = menu_img(190)
    base.paste(m, (720, 70), m)
    line = "有什么事要和我说吗？"
    frames = []
    squash_curve = [1.0, 0.94, 0.88, 0.86, 0.95, 1.04, 1.0]
    for i in range(26):
        canvas = base.copy()
        squash = squash_curve[i] if i < len(squash_curve) else 1.0
        pet_at(canvas, 280, 300, 250, squash)
        if i >= 6:
            p = min(1.0, (i - 6) / 9.0)
            shown = line[:max(1, int(len(line) * p))]
            b = bubble_img(shown)
            s = 0.7 + 0.3 * p
            b = b.resize((max(1, int(b.width * s)), max(1, int(b.height * s))), Image.LANCZOS)
            a = b.getchannel("A").point(lambda v: int(v * min(1.0, p * 1.6)))
            b.putalpha(a)
            canvas.paste(b, (300 + 140 - b.width // 2, 250 - 16 - b.height), b)
        frames.append(canvas.convert("P", palette=Image.ADAPTIVE, colors=128))
    out = ASSETS / "demo.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=110, loop=0, optimize=True, disposal=2)
    print("saved assets/demo.gif", out.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    make_png()
    make_gif()
