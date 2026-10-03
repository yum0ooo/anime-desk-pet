# -*- coding: utf-8 -*-
"""生成仓库自带的占位角色 assets/pet.gif（原创、可随 MIT 协议一起分发）。

一个会轻轻上下浮动的圆润小家伙，20 帧循环、透明背景。
你自己的角色图可以直接覆盖这个文件。
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SIZE = 300
FRAMES = 20
BODY = (255, 226, 214, 255)
BODY_EDGE = (226, 168, 152, 255)
CHEEK = (255, 150, 162, 200)
EYE = (58, 44, 58, 255)
ACCENT = (126, 178, 255, 255)


def draw_frame(t: float) -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bob = math.sin(t * 2 * math.pi) * 7           # 上下浮动
    squash = 1.0 + math.sin(t * 2 * math.pi) * 0.025
    cx, cy = SIZE / 2, 196 + bob
    rx, ry = 96 * squash, 88 / squash

    # 影子
    shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse(
        [cx - rx * 0.8, 268, cx + rx * 0.8, 292], fill=(40, 50, 80, 70))
    img = Image.alpha_composite(img, shadow)
    d = ImageDraw.Draw(img)

    # 头顶小天线
    d.line([(cx, cy - ry + 6), (cx + 6, cy - ry - 34)], fill=BODY_EDGE, width=7)
    d.ellipse([cx - 8, cy - ry - 54, cx + 20, cy - ry - 26], fill=ACCENT)

    # 身体
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=BODY, outline=BODY_EDGE, width=4)

    # 腮红
    d.ellipse([cx - 66, cy + 6, cx - 30, cy + 30], fill=CHEEK)
    d.ellipse([cx + 30, cy + 6, cx + 66, cy + 30], fill=CHEEK)

    # 眼睛（会眨）
    blink = t > 0.86
    for sign in (-1, 1):
        ex = cx + sign * 34
        if blink:
            d.line([(ex - 13, cy - 16), (ex + 13, cy - 16)], fill=EYE, width=6)
        else:
            d.ellipse([ex - 13, cy - 30, ex + 13, cy - 2], fill=EYE)
            d.ellipse([ex - 4, cy - 26, ex + 5, cy - 17], fill=(255, 255, 255, 235))

    # 嘴
    d.arc([cx - 14, cy + 36, cx + 14, cy + 60], start=15, end=165, fill=EYE, width=4)
    return img


def save_transparent_gif(frames, path: Path, duration=60):
    """RGBA -> 带透明索引的 GIF（255 号索引作为透明色）。"""
    palette_frames = []
    for f in frames:
        alpha = f.getchannel("A")
        p = f.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=255)
        p.paste(255, alpha.point(lambda v: 255 if v < 128 else 0))
        palette_frames.append(p)
    palette_frames[0].save(
        path, save_all=True, append_images=palette_frames[1:],
        duration=duration, loop=0, transparency=255, disposal=2, optimize=False,
    )


def main():
    (ROOT / "assets").mkdir(exist_ok=True)
    frames = [draw_frame(i / FRAMES) for i in range(FRAMES)]
    out = ROOT / "assets" / "pet.gif"
    save_transparent_gif(frames, out)
    frames[0].save(ROOT / "assets" / "preview.png")

    # 回读校验：透明区必须真的是透明的
    check = Image.open(out)
    total = check.n_frames
    check.seek(0)
    rgba = check.convert("RGBA")
    a = rgba.getchannel("A")
    xs = list(a.getdata())
    transparent = sum(1 for v in xs if v < 128)
    opaque = sum(1 for v in xs if v >= 128)
    print(f"saved {out}  frames={total}  size={out.stat().st_size // 1024}KB")
    print(f"透明像素 {transparent} / 不透明 {opaque}  (角点 alpha={rgba.getpixel((2, 2))[3]})")


if __name__ == "__main__":
    main()
