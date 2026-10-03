# -*- coding: utf-8 -*-
"""生成 README 用的演示图 / 演示动图。

用法：
    python tools/make_demo.py                 # 用 assets/pet.gif
    python tools/make_demo.py 路径/角色.gif    # 用指定图片

产物：
    assets/demo.png   静态效果图（角色 + 气泡 + 菜单）
    assets/demo.gif   动态演示（点击弹性 + 气泡弹出）
"""
import sys
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont

import desktop_pet as dp

W, H = 1080, 620
KEY = dp.TRANSPARENT_KEY


def key_to_rgba(img):
    """把键控色背景的 RGB 图转成带 alpha 的 RGBA。"""
    rgba = img.convert("RGBA")
    key = dp.hex_rgb(KEY)
    px = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            if px[x, y][:3] == key:
                px[x, y] = (0, 0, 0, 0)
    return rgba


def backdrop():
    """画一张假的「桌面」：渐变壁纸 + 一个半透明文档窗口，用来体现真透明。"""
    bg = Image.new("RGB", (W, H), (24, 34, 58))
    d = ImageDraw.Draw(bg)
    for y in range(H):                                    # 竖向渐变
        k = y / H
        d.line([(0, y), (W, y)],
               fill=(int(28 + 40 * k), int(38 + 26 * k), int(70 + 46 * k)))
    for i in range(0, W + H, 46):                         # 斜向暗纹
        d.line([(i, 0), (i - H, H)], fill=(255, 255, 255, 6))

    card = Image.new("RGBA", (470, 330), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    cd.rounded_rectangle([0, 0, 469, 329], radius=14, fill=(255, 255, 255, 236))
    cd.rounded_rectangle([0, 0, 469, 46], radius=14, fill=(240, 243, 250, 255))
    cd.rectangle([0, 32, 469, 46], fill=(240, 243, 250, 255))
    for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        cd.ellipse([18 + i * 20, 15, 30 + i * 20, 27], fill=c)
    font = dp.find_font(15)
    cd.text((22, 74), "今天的任务", font=font, fill=(40, 52, 78))
    for i in range(5):
        y = 112 + i * 34
        cd.rounded_rectangle([22, y, 22 + (300 - i * 34), y + 11], radius=5,
                             fill=(206, 214, 230, 255))
    cd.rounded_rectangle([22, 288, 200, 312], radius=7, fill=(84, 174, 255, 255))
    bg.paste(card, (70, 150), card)

    tag = dp.find_font(17)
    d.text((72, 574), "角色图透明背景 → 直接贴在桌面上，没有窗口边框",
           font=tag, fill=(178, 194, 224))
    return bg


def pet_frames(path, size):
    frames, _ = dp.load_frames(str(path))
    out = []
    for f in frames:
        r = f.resize((size, size), Image.LANCZOS)
        a = r.getchannel("A").point(lambda v: 255 if v >= 128 else 0)
        out.append((r, a))
    return out


def paste_pet(canvas, frame, xy, sy=1.0, sx=1.0):
    img, _ = frame
    w, h = max(1, int(img.width * sx)), max(1, int(img.height * sy))
    r = img.resize((w, h), Image.LANCZOS)
    a = r.getchannel("A").point(lambda v: 255 if v >= 128 else 0)
    canvas.paste(r, (int(xy[0]), int(xy[1])), a)
    return w, h


def menu_image(items, palette, width=None):
    """直接借用 CatMenu 的渲染函数画一张菜单卡片（不弹真窗口）。"""
    root = tk.Tk()
    root.withdraw()
    menu = dp.CatMenu(root, KEY, palette)
    rows, height = menu._layout(items)
    width = width or menu._width_for(items)
    menu.panels = [{"items": items, "rows": rows, "w": width, "h": height,
                    "win": None, "label": None, "x": 0, "y": 0, "image": None}]
    menu.hover = (0, 3)
    img = menu._render(0)
    root.destroy()
    return key_to_rgba(img)


def bubble_image(text, width_hint=None):
    root = tk.Tk()
    root.withdraw()
    b = dp.Bubble(root, KEY)
    img = b.build(text, 0.32, True)
    root.destroy()
    return img


def build_menu_items():
    return [
        {"type": "command", "label": "暂停动画"},
        {"type": "command", "label": "换一句台词"},
        {"type": "separator"},
        {"type": "submenu", "label": "番茄钟"},
        {"type": "submenu", "label": "窗口大小"},
        {"type": "submenu", "label": "不透明度"},
        {"type": "submenu", "label": "音效音量"},
        {"type": "command", "label": "窗口置顶", "checked": True},
        {"type": "separator"},
        {"type": "command", "label": "退出"},
    ]


def make_png(frames, out: Path):
    canvas = backdrop().convert("RGBA")
    pet_x, pet_y, pet_size = 250, 292, 300
    paste_pet(canvas, frames[12], (pet_x, pet_y - 70))     # 弹起状态，展示形变空间

    bub = bubble_image("哼，才不是特意在这里等你的呢。")
    canvas.paste(bub, (pet_x + pet_size // 2 - bub.width // 2, pet_y - 78 - bub.height), bub)

    menu = menu_image(build_menu_items(), dp.THEME_LIGHT)
    canvas.paste(menu, (640, 108), menu)

    tip = dp.find_font(15)
    ImageDraw.Draw(canvas).text((648, 108 + menu.height + 14),
                                "自绘圆角卡片菜单，跟随系统深浅色", font=tip,
                                fill=(178, 194, 224))
    canvas.convert("RGB").save(out, quality=95)
    print("saved", out, canvas.size)


def make_gif(frames, out: Path):
    """按下压扁 → 松开回弹 → 气泡弹出，循环播放。"""
    pet_x, pet_y, pet_size = 300, 246, 278
    base = backdrop().convert("RGBA")
    menu = menu_image(build_menu_items(), dp.THEME_LIGHT, width=196)
    base.paste(menu, (700, 120), menu)

    curve = [1.0, 0.94, 0.88, 0.88, 0.96, 1.04, 1.10, 1.05, 1.0, 1.0,
             1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    out_frames = []
    for i, k in enumerate(curve):
        canvas = base.copy()
        sy, sx = k, 2.0 - k                        # 压扁时变宽，符合体积守恒的观感
        _, h = paste_pet(canvas, frames[(i * 3) % len(frames)],
                         (pet_x, pet_y + (pet_size - pet_size * sy)), sy, sx)
        if i >= 4:                                  # 回弹之后才弹气泡
            p = min(1.0, (i - 4) / 6.0)
            img = bubble_image("点我干嘛，陪我玩吗？")
            w = int(img.width * (0.7 + 0.3 * p))
            hh = int(img.height * (0.7 + 0.3 * p))
            img = img.resize((w, hh), Image.LANCZOS)
            alpha = img.getchannel("A").point(lambda v: int(v * p))
            img.putalpha(alpha)
            canvas.paste(img, (pet_x + pet_size // 2 - w // 2, pet_y - 96 - hh), img)
        out_frames.append(canvas.convert("P", palette=Image.ADAPTIVE, colors=128))

    out_frames[0].save(out, save_all=True, append_images=out_frames[1:],
                       duration=90, loop=0, optimize=True, disposal=2)
    print("saved", out, "frames", len(out_frames),
          "size", out.stat().st_size // 1024, "KB")


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "assets" / "pet.gif"
    if not path.exists():
        raise SystemExit(f"找不到角色图：{path}")
    dp.enable_dpi_awareness()
    frames = pet_frames(path, 300)
    (ROOT / "assets").mkdir(exist_ok=True)
    make_png(frames, ROOT / "assets" / "demo.png")
    make_gif(frames, ROOT / "assets" / "demo.gif")


if __name__ == "__main__":
    main()
