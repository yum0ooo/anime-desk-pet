# -*- coding: utf-8 -*-
"""
桌面宠物小摆件  Desktop Pet
------------------------------------------------
· 透明无边框、始终置顶
· 左键拖动，单击弹台词气泡，右键菜单调大小/退出
· 纯本地运行，不联网、无后端依赖
"""
import array
import ctypes
import json
import math
import os
import random
import sys
import time
import tkinter as tk
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageTk

try:
    import winsound
except ImportError:            # 非 Windows 平台静音运行
    winsound = None

try:
    from PySide6.QtCore import QCoreApplication, QTimer
except ImportError:            # 没装 PySide6 时番茄钟会自动禁用，其余功能照常
    QCoreApplication = None
    QTimer = None

# ============================================================
#  ★ 角色图片路径（支持 GIF / PNG）
#    默认取本文件同级的 assets/pet.gif，也可以直接写绝对路径，
#    或用环境变量 DESKTOP_PET_IMAGE / pet_config.json 里的 image 覆盖。
# ============================================================
IMAGE_PATH = str(Path(__file__).resolve().parent / "assets" / "pet.gif")

# ---------------- 可调参数 ----------------
TRANSPARENT_KEY = "#ff00fe"   # 抠像用的键控色（图片里不含该颜色）
BUBBLE_MS = 2500              # 气泡停留时间（毫秒）
MIN_SCALE, MAX_SCALE = 0.25, 2.0
BUBBLE_MAX_TEXT_W = 240       # 气泡文字最大宽度
BUBBLE_FONT_SIZE = 15
DRAG_THRESHOLD = 4            # 位移小于该像素视为“点击”
CLICK_MAX_SECONDS = 0.6

# 气泡样式：几何沿用 BongoCat 卡片，配色与弹出方式借用 DeepSeek 鲸鱼挂件
BUBBLE_RADIUS = 12
BUBBLE_BG = "#ffffff"
BUBBLE_BORDER = "#e8ebf1"
BUBBLE_TEXT = "#536ba9"          # ← 鲸鱼挂件的正文色
BUBBLE_HINT = "#9fb0d9"          # ← 鲸鱼挂件的次要文字色
BUBBLE_PAD_X, BUBBLE_PAD_Y = 16, 11
BUBBLE_TAIL_W, BUBBLE_TAIL_H = 16, 8
BUBBLE_ANIM_MS, BUBBLE_ANIM_STEPS = 200, 8   # 鲸鱼：scale(.7→1) + 淡入，200ms ease
BUBBLE_FADE_MS = 140                          # 消失时快速淡出
BUBBLE_START_SCALE = 0.7                      # ← 鲸鱼泡泡的起始缩放

# ---------------- 菜单配色（取自 BongoCat 自绘菜单的深/浅色表）----------------
MENU_FONT_SIZE = 15
MENU_ROW_H, MENU_SEP_H, MENU_PAD_Y = 34, 13, 8
MENU_TEXT_X, MENU_MIN_W, MENU_RADIUS = 20, 200, 12
THEME_DARK = {
    "surface": "#21242b", "field": "#2a2e37", "border": "#3b424f",
    "text": "#f4f7fb", "muted": "#9aa4b2", "accent": "#54aeff",
}
THEME_LIGHT = {
    "surface": "#ffffff", "field": "#f3f5f8", "border": "#d8dee8",
    "text": "#182230", "muted": "#667085", "accent": "#54aeff",
}
SCALE_PRESETS = (("迷你", 0.40), ("小", 0.60), ("标准", 0.80), ("大", 1.00), ("超大", 1.30))
OPACITY_PRESETS = (100, 90, 80, 70, 60, 50, 40, 30, 20)
MIN_OPACITY = 0.20

# ============================================================
#  ★ 番茄钟 / 音效参数（改这里就行）
# ============================================================
POMODORO_MINUTES = 25          # ★ 专注时长（分钟）。测试时可临时改成 1
POMODORO_TICK_MS = 200         # QTimer 间隔，只影响刷新频率，不影响计时精度
ALARM_SECONDS = 10             # 到点后提示音持续多少秒
SOUND_VOLUME_DEFAULT = 65      # 默认音量 0-100
VOLUME_PRESETS = (0, 25, 50, 75, 100)
SAMPLE_RATE = 44100

# 点击弹性：直接借 DeepSeek 鲸鱼挂件的参数
# （按下 scaleY(.88) scaleX(1.05)，松开回 1，转换 220ms cubic-bezier(.34,1.56,.64,1)，
#   变换原点 50% 100% —— 也就是脚踩在地上、从底部中心压缩）
SQUISH_MS = 220
SQUISH_STEPS = 8
SQUISH_DOWN = (0.88, 1.05)     # (scaleY, scaleX)
SQUISH_UP = (1.0, 1.0)

# ---------------- 台词库 ----------------
LINES = [
    "点我干嘛，陪我玩吗？",
    "哼，才不是特意在这里等你的呢。",
    "喂，摸鱼时间到了吗？",
    "再点一下试试看，我可要生气了哦。",
    "你今天有好好喝水吗？",
    "别戳了别戳了，好痒的！",
    "我才没有偷看你，是你在看我吧。",
    "唔……被你发现了，我刚在发呆。",
    "说好的，摸我一下要给一颗糖。",
    "屏幕是不是有点脏？不是我蹭的。",
    "差不多该休息一下啦，眼睛会坏的。",
    "我在这儿站了一整天，你终于理我了。",
    "哼，你今天怎么才来找我。",
    "偷偷告诉你，右键可以把我变大变小哦。",
    "别把我拖到屏幕外面去，我会害怕的。",
    "有本事你就一直盯着我看。",
    "再摸头，头发要乱了啦！",
    "事情做完了吗？没做完就先别摸我。",
    "我也没在等你，只是刚好站在这里。",
    "今天也要元气满满哦，笨蛋。",
    "给你三秒钟把手拿开……三、二……算了。",
    "我可不是摆件，我是有脾气的。",
    "你是不是又熬夜了？脸色好差。",
    "诶，你点我，是不是想我了？",
    "好无聊啊，陪我聊聊天嘛。",
    "夸我一句，我就原谅你。",
    "别老盯着屏幕看，也看看我呀。",
    "天气不错，可惜你不出门。",
]

# ---------------- 路径工具 ----------------
def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


CONFIG_PATH = app_dir() / "pet_config.json"


def enable_dpi_awareness() -> None:
    """让窗口在高分屏下保持清晰、坐标不缩放。"""
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def make_click_through(win: tk.Toplevel) -> None:
    """让气泡窗口不接收鼠标事件、不抢焦点。"""
    try:
        win.update_idletasks()
        GWL_EXSTYLE = -20
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_TOOLWINDOW = 0x00000080
        user32 = ctypes.windll.user32
        for hwnd in {int(win.winfo_id()), user32.GetParent(int(win.winfo_id()))}:
            if not hwnd:
                continue
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                style | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
            )
    except Exception:
        pass


# ---------------- 素材加载 ----------------
def load_frames(path: str):
    """读取 GIF/PNG，返回 (RGBA 帧列表, 每帧时长毫秒)。"""
    im = Image.open(path)
    frames, durations = [], []
    total = getattr(im, "n_frames", 1)
    for i in range(total):
        im.seek(i)
        frames.append(im.convert("RGBA"))
        durations.append(max(20, int(im.info.get("duration") or 100)))
    return frames, durations


def content_box(frames):
    """所有帧非透明区域的并集，用于定位“头顶”。"""
    box = None
    for f in frames:
        bb = f.getchannel("A").point(lambda v: 255 if v >= 128 else 0).getbbox()
        if not bb:
            continue
        box = bb if box is None else (
            min(box[0], bb[0]), min(box[1], bb[1]),
            max(box[2], bb[2]), max(box[3], bb[3]),
        )
    return box or (0, 0, frames[0].width, frames[0].height)


def centered_frame_index(frames):
    """找出人物最“居中”的那一帧（重心最接近全程平均），暂停时定格在这一帧。"""
    centers = []
    for f in frames:
        bb = f.getchannel("A").point(lambda v: 255 if v >= 128 else 0).getbbox()
        centers.append((bb[0] + bb[2]) / 2 if bb else f.width / 2)
    if not centers:
        return 0
    target = sum(centers) / len(centers)
    return min(range(len(centers)), key=lambda i: abs(centers[i] - target))


def system_prefers_dark() -> bool:
    """读取 Windows 个性化设置里的“应用模式”，跟随系统深浅色（同 BongoCat 的 dark_theme）。"""
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as k:
            value, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
        return int(value) == 0
    except Exception:
        return False


def find_font(size: int):
    for name in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf", "simsun.ttc", "arial.ttf"):
        p = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name)
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ---------------- emoji 支持（中文字体没有 emoji 字形，要单独混排） ----------------
EMOJI_RANGES = ((0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2B00, 0x2BFF))
_EMOJI_FONTS = {}


def is_emoji(ch: str) -> bool:
    o = ord(ch)
    return any(lo <= o <= hi for lo, hi in EMOJI_RANGES)


def split_runs(text: str):
    """把字符串切成 连续 emoji / 连续普通字符 的片段。"""
    runs = []
    for ch in text:
        kind = "e" if is_emoji(ch) else "t"
        if runs and runs[-1][0] == kind:
            runs[-1] = (kind, runs[-1][1] + ch)
        else:
            runs.append((kind, ch))
    return runs


def find_emoji_font(size: int):
    if size not in _EMOJI_FONTS:
        font = None
        path = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "seguiemj.ttf")
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
            except Exception:
                font = None
        _EMOJI_FONTS[size] = font
    return _EMOJI_FONTS[size]


# ---------------- 音效：本地合成，不依赖任何音频素材文件 ----------------
def _synth_blip(f_start, f_end, duration, decay, gain=0.62, click_level=0.5):
    """一段带噪声瞬态、频率从 f_start 扫到 f_end 的短音。"""
    n = int(SAMPLE_RATE * duration)
    rnd = random.Random(int(f_start * 7 + f_end))
    sweep = (f_end - f_start) / duration
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # 相位 = 瞬时频率的积分（线性扫频）
        phase = 2 * math.pi * (f_start * t + 0.5 * sweep * t * t)
        body = math.sin(phase) * 0.75 + math.sin(phase * 2.0) * 0.16
        click = rnd.uniform(-1.0, 1.0) * max(0.0, 1.0 - t / 0.005) * click_level
        out.append(max(-1.0, min(1.0, body * math.exp(-t * decay) * gain + click)))
    return out


def _synth_press():
    """按下：音高往下掉，闷一点。"""
    return _synth_blip(760.0, 360.0, 0.12, 30.0, gain=0.55)


def _synth_release():
    """松开：音高往上弹，脆一点——对应鲸鱼挂件按下/松开两个音效。"""
    return _synth_blip(420.0, 980.0, 0.17, 22.0, gain=0.62, click_level=0.35)


def _synth_chime():
    """到点提示音：A5-C#6-E6 上行琶音，长衰减，约 1.35 秒。"""
    n = int(SAMPLE_RATE * 1.35)
    out = [0.0] * n
    for freq, delay in ((880.00, 0.00), (1108.73, 0.12), (1318.51, 0.24)):
        start = int(delay * SAMPLE_RATE)
        for i in range(start, n):
            t = (i - start) / SAMPLE_RATE
            env = math.exp(-t * 4.2) * (1.0 - math.exp(-t * 260.0))
            out[i] += (math.sin(2 * math.pi * freq * t) * 0.60
                       + math.sin(2 * math.pi * freq * 2.0 * t) * 0.14
                       + math.sin(2 * math.pi * freq * 3.0 * t) * 0.05) * env * 0.42
    return [max(-1.0, min(1.0, v)) for v in out]


SYNTH = {"press": _synth_press, "release": _synth_release, "chime": _synth_chime}
SOUND_DIR = app_dir() / "sounds"


def write_wav(path, samples, volume):
    data = array.array("h", (
        int(max(-1.0, min(1.0, s * volume)) * 32767) for s in samples
    ))
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(data.tobytes())


class Sound:
    """按音量合成并播放本地音效（winsound，无需额外依赖）。"""

    def __init__(self, volume=SOUND_VOLUME_DEFAULT):
        self.volume = max(0, min(100, int(volume)))
        self._files = {}
        try:
            SOUND_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def set_volume(self, volume):
        self.volume = max(0, min(100, int(volume)))

    def _file(self, name):
        key = (name, self.volume)
        if key in self._files:
            return self._files[key]
        path = SOUND_DIR / f"{name}_v{self.volume:03d}.wav"
        if not path.exists():
            try:
                write_wav(path, SYNTH[name](), self.volume / 100.0)
            except Exception:
                return None
        self._files[key] = path
        return path

    def play(self, name):
        if winsound is None or self.volume <= 0:
            return
        path = self._file(name)
        if path is None:
            return
        try:
            winsound.PlaySound(str(path), winsound.SND_FILENAME
                               | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except Exception:
            pass

    def stop(self):
        if winsound is None:
            return
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass


# ---------------- 缓动：BongoCat 的 cubic-bezier(.34, 1.56, .64, 1) 弹簧曲线 ----------------
def _bezier_table(x1, y1, x2, y2, steps=64):
    table = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1.0 - t
        table.append((
            3 * mt * mt * t * x1 + 3 * mt * t * t * x2 + t ** 3,
            3 * mt * mt * t * y1 + 3 * mt * t * t * y2 + t ** 3,
        ))
    return table


SPRING_TABLE = _bezier_table(0.34, 1.56, 0.64, 1.0)
EASE_TABLE = _bezier_table(0.25, 0.1, 0.25, 1.0)      # CSS 默认的 ease（鲸鱼泡泡用的就是它）


def _eval_table(table, t):
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    for i in range(len(table) - 1):
        x0, y0 = table[i]
        x1, y1 = table[i + 1]
        if x0 <= t <= x1:
            span = x1 - x0
            k = (t - x0) / span if span > 1e-9 else 0.0
            return y0 + (y1 - y0) * k
    return 1.0


def spring_ease(t):
    """BONGO_CAT_UI_EASE_SPRING 的近似求值（点击弹性用）。"""
    return _eval_table(SPRING_TABLE, t)


def ease_out(t):
    """CSS ease（气泡弹出用）。"""
    return _eval_table(EASE_TABLE, t)


def hex_rgb(value):
    v = value.lstrip("#")
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


def hard_round_mask(width, height, radius, supersample=3):
    """超采样画圆角遮罩再阈值化：卡片外一定是纯键控色，不会留半透明描边。"""
    s = supersample
    mask = Image.new("L", (width * s, height * s), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, width * s - 1, height * s - 1], radius=radius * s, fill=255
    )
    return mask.resize((width, height), Image.LANCZOS).point(lambda v: 255 if v >= 128 else 0)


# ---------------- 台词气泡 ----------------
class Bubble:
    """头顶台词气泡：BongoCat 卡片样式（圆角 12 + 1px 描边）+ spring 弹入。"""

    def __init__(self, master: tk.Tk, key: str):
        self.key = key
        self.key_rgb = hex_rgb(key)
        self.probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        self._emoji_font = find_emoji_font(BUBBLE_FONT_SIZE + 1)
        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-transparentcolor", key)
        except tk.TclError:
            pass
        self.win.configure(bg=key)
        self.label = tk.Label(self.win, bd=0, highlightthickness=0, bg=key)
        self.label.pack()
        self.win.withdraw()
        self._img = None
        self._job = None
        self._ready = False
        self._master = None
        self._step = 0
        self._tail_ratio = 0.5
        self._on_timeout = None
        self._persistent = False

    # ---------- 绘制 ----------
    def _measure(self, text, font):
        """按 emoji / 普通字符混排量宽度。"""
        total = 0.0
        for kind, run in split_runs(text):
            f = self._emoji_font if (kind == "e" and self._emoji_font) else font
            total += self.probe.textlength(run, font=f)
        return total

    def _draw_runs(self, draw, x, y, text, font, fill):
        """按 emoji / 普通字符混排绘制，返回结束时的 x。"""
        cursor = x
        for kind, run in split_runs(text):
            if kind == "e" and self._emoji_font:
                draw.text((cursor, y), run, font=self._emoji_font, embedded_color=True)
                cursor += self.probe.textlength(run, font=self._emoji_font)
            else:
                draw.text((cursor, y), run, font=font, fill=fill)
                cursor += self.probe.textlength(run, font=font)
        return cursor

    def build(self, text: str, tail_ratio: float = 0.5, tail_down: bool = True) -> Image.Image:
        """生成气泡的 RGBA 图（卡片内不透明，卡片外 alpha=0）。"""
        font = find_font(BUBBLE_FONT_SIZE)

        lines, cur = [], ""
        for ch in text:
            if self._measure(cur + ch, font) <= BUBBLE_MAX_TEXT_W:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
        lines = [ln for ln in lines if ln] or [text]

        ascent, descent = font.getmetrics()
        line_h = ascent + descent + 4
        text_w = max(self._measure(ln, font) for ln in lines)

        body_w = int(max(56, text_w + BUBBLE_PAD_X * 2))
        body_h = int(line_h * len(lines) + BUBBLE_PAD_Y * 2)
        W = body_w
        H = body_h + BUBBLE_TAIL_H

        mask = hard_round_mask(body_w, body_h, BUBBLE_RADIUS)
        full = Image.new("L", (W, H), 0)
        full.paste(mask, (0, BUBBLE_TAIL_H if not tail_down else 0))

        cx = int(min(max(tail_ratio, (BUBBLE_RADIUS + 10) / W),
                     1 - (BUBBLE_RADIUS + 10) / W) * W)
        half = BUBBLE_TAIL_W // 2
        S = 4
        tri = Image.new("L", (W * S, H * S), 0)
        td = ImageDraw.Draw(tri)
        if tail_down:
            base = BUBBLE_TAIL_H + body_h - 6
            td.polygon([((cx - half) * S, base * S), ((cx + half) * S, base * S),
                        (cx * S, (BUBBLE_TAIL_H + body_h) * S - 1)], fill=255)
        else:
            base = BUBBLE_TAIL_H + 6
            td.polygon([((cx - half) * S, base * S), ((cx + half) * S, base * S),
                        (cx * S, 1)], fill=255)
        tri = tri.resize((W, H), Image.LANCZOS).point(lambda v: 255 if v >= 128 else 0)
        mask = Image.composite(Image.new("L", (W, H), 255), full, tri)

        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        img.paste(hex_rgb(BUBBLE_BG) + (255,), (0, 0), mask)

        # 边框与文字画在遮罩内，再用遮罩裁一次，保证不会溢出卡片
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        top = 0 if tail_down else BUBBLE_TAIL_H
        d.rounded_rectangle([0, top, body_w - 1, top + body_h - 1],
                            radius=BUBBLE_RADIUS, outline=hex_rgb(BUBBLE_BORDER) + (255,))
        for i, ln in enumerate(lines):
            self._draw_runs(d, BUBBLE_PAD_X, top + BUBBLE_PAD_Y + i * line_h + 1,
                            ln, font, hex_rgb(BUBBLE_TEXT) + (255,))
        img = Image.alpha_composite(img, Image.composite(
            layer, Image.new("RGBA", (W, H), (0, 0, 0, 0)), mask))
        return img

    def _to_photo(self, rgba: Image.Image) -> ImageTk.PhotoImage:
        alpha = rgba.getchannel("A").point(lambda v: 255 if v >= 128 else 0)
        bg = Image.new("RGB", rgba.size, self.key_rgb)
        bg.paste(rgba, (0, 0), alpha)
        return ImageTk.PhotoImage(bg)

    def _prepare(self):
        if not self._ready:
            self.win.update_idletasks()
            # 气泡现在要能被点击（点一下换台词），所以不再做穿透
            self._ready = True

    # ---------- 显示 / 动画 ----------
    def cancel(self):
        if self._job:
            try:
                self.win.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def bind_click(self, handler):
        for w in (self.win, self.label):
            w.bind("<Button-1>", handler)

    def show(self, master: Image.Image, x: int, y: int, on_timeout=None,
             persistent: bool = False, tail_ratio: float = 0.5):
        self.cancel()
        self._master = master
        self._x, self._y = int(x), int(y)
        self._on_timeout = on_timeout
        self._persistent = persistent
        self._tail_ratio = tail_ratio
        self._step = 0
        self.win.deiconify()
        self.win.lift()
        self._prepare()
        try:
            self.win.attributes("-alpha", 0.03)
        except tk.TclError:
            pass
        self._animate()

    def update_in_place(self, master: Image.Image, x: int, y: int, tail_ratio: float = 0.5):
        """原地换内容：不重播弹入动画、不移动窗口锚点（番茄钟每秒刷新用）。"""
        self._master = master
        self._x, self._y = int(x), int(y)
        self._tail_ratio = tail_ratio
        self._img = self._to_photo(master)
        self.label.configure(image=self._img)
        self.win.geometry(f"{master.width}x{master.height}+{self._x}+{self._y}")
        self.win.deiconify()
        try:
            self.win.attributes("-alpha", 1.0)
        except tk.TclError:
            pass

    def _animate(self):
        if self._master is None:
            return
        W0, H0 = self._master.size
        if self._step > BUBBLE_ANIM_STEPS:
            self._settle(W0, H0)
            return
        p = ease_out(self._step / BUBBLE_ANIM_STEPS)
        s = BUBBLE_START_SCALE + (1.0 - BUBBLE_START_SCALE) * p   # 鲸鱼：scale .7 → 1
        w, h = max(1, int(W0 * s)), max(1, int(H0 * s))
        frame = self._master.resize((w, h), Image.LANCZOS) if s < 0.999 else self._master
        self._img = self._to_photo(frame)
        self.label.configure(image=self._img)
        tail_x = self._x + self._tail_ratio * W0
        self.win.geometry(
            f"{w}x{h}+{int(round(tail_x - self._tail_ratio * w))}"
            f"+{int(round(self._y + H0 - h - 12 * (1 - p)))}"
        )
        try:
            self.win.attributes("-alpha", max(0.03, min(1.0, p)))
        except tk.TclError:
            pass
        self._step += 1
        self._job = self.win.after(max(16, BUBBLE_ANIM_MS // BUBBLE_ANIM_STEPS), self._animate)

    def _settle(self, W0, H0):
        self._img = self._to_photo(self._master)
        self.label.configure(image=self._img)
        self.win.geometry(f"{W0}x{H0}+{self._x}+{self._y}")
        try:
            self.win.attributes("-alpha", 1.0)
        except tk.TclError:
            pass
        if self._persistent or self._on_timeout is None:
            return                               # 常驻气泡：不排自动消失的定时器
        self._job = self.win.after(BUBBLE_MS, self._on_timeout)   # 2.5 秒后自动消失

    def hide(self):
        self.cancel()
        self._fade(BUBBLE_FADE_MS // 35)

    def _fade(self, steps):
        if self._master is None or steps <= 0:
            self._master = None
            try:
                self.win.attributes("-alpha", 1.0)
                self.win.withdraw()
            except tk.TclError:
                pass
            return
        try:
            self.win.attributes("-alpha", max(0.0, steps / 5.0))
        except tk.TclError:
            pass
        self._job = self.win.after(35, lambda: self._fade(steps - 1))

    def is_visible(self) -> bool:
        return self._master is not None

    def destroy(self):
        self.cancel()
        try:
            self.win.destroy()
        except Exception:
            pass


# ---------------- 仿 BongoCat 自绘菜单 ----------------
class CatMenu:
    """圆角卡片菜单：悬停高亮、勾选前缀、灰色提示行、二级子菜单，跟随系统深浅色。"""

    def __init__(self, master: tk.Tk, key: str, palette: dict):
        self.master = master
        self.key = key
        self.palette = palette
        self.font = find_font(MENU_FONT_SIZE)
        self.probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        self.panels = []
        self.items = []
        self.hover = None
        self.sub_owner = None
        self.opened = False

    # ---- 布局 ----
    @staticmethod
    def _text(item):
        return item.get("label", "")

    def _width_for(self, items):
        width = 0
        for it in items:
            if it["type"] == "separator":
                continue
            width = max(width, self.probe.textlength(self._text(it), font=self.font))
            if it["type"] == "submenu":
                width += 28
        return int(max(MENU_MIN_W, width + MENU_TEXT_X * 2))

    def _layout(self, items):
        rows, y = [], MENU_PAD_Y
        for i, it in enumerate(items):
            h = MENU_SEP_H if it["type"] == "separator" else MENU_ROW_H
            rows.append((i, y, y + h, it))
            y += h
        return rows, y + MENU_PAD_Y

    def _render(self, index):
        panel = self.panels[index]
        items, rows, width, height = panel["items"], panel["rows"], panel["w"], panel["h"]
        p = self.palette
        mask = hard_round_mask(width, height, MENU_RADIUS)
        img = Image.new("RGB", (width, height), hex_rgb(self.key))
        img.paste(hex_rgb(p["surface"]), (0, 0), mask)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, width - 1, height - 1], radius=MENU_RADIUS,
                            outline=hex_rgb(p["border"]))
        for (idx, y0, y1, it) in rows:
            if it["type"] == "separator":
                yl = y0 + MENU_SEP_H // 2
                d.line([(12, yl), (width - 13, yl)], fill=hex_rgb(p["border"]), width=1)
                continue
            # 子菜单展开时，父行保持高亮（BongoCat 同样如此）
            hovered = (self.hover == (index, idx)) or (index == 0 and self.sub_owner == idx)
            hovered = hovered and it["type"] != "hint"
            if hovered:      # BongoCat: 高亮条 (8, y, w-16, row_h)
                d.rectangle([8, y0, width - 9, y1], fill=hex_rgb(p["field"]))
            color = p["muted"] if it["type"] == "hint" else (p["accent"] if hovered else p["text"])
            text = self._text(it)
            bbox = d.textbbox((0, 0), text, font=self.font)
            ty = y0 + (MENU_ROW_H - (bbox[3] - bbox[1])) // 2 - bbox[1]
            d.text((MENU_TEXT_X, ty), text, font=self.font, fill=hex_rgb(color))
            if it.get("checked"):       # 对勾用折线画，避免字体缺字变成方框
                cy = y0 + MENU_ROW_H // 2
                d.line([(MENU_TEXT_X - 12, cy), (MENU_TEXT_X - 8, cy + 4),
                        (MENU_TEXT_X - 3, cy - 5)], fill=hex_rgb(color), width=2,
                       joint="curve")
            if it["type"] == "submenu":     # 用多边形画箭头，不依赖字体是否有该字形
                cy = y0 + MENU_ROW_H // 2
                d.polygon([(width - 22, cy - 4), (width - 22, cy + 4), (width - 14, cy)],
                          fill=hex_rgb(color))
        return img

    def _refresh(self):
        for i, panel in enumerate(self.panels):
            panel["image"] = ImageTk.PhotoImage(self._render(i))
            panel["label"].configure(image=panel["image"])

    def _make_panel(self, index, items, width, height, rows):
        win = tk.Toplevel(self.master)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-transparentcolor", self.key)
        except tk.TclError:
            pass
        win.configure(bg=self.key)
        label = tk.Label(win, bd=0, highlightthickness=0, bg=self.key)
        label.pack()
        panel = {"win": win, "label": label, "items": items, "rows": rows,
                 "w": width, "h": height, "x": 0, "y": 0, "image": None}
        self.panels.insert(index, panel)
        panel["image"] = ImageTk.PhotoImage(self._render(index))
        label.configure(image=panel["image"])
        return panel

    # ---- 弹出 / 关闭 ----
    def popup(self, x, y, items):
        self.close()
        self.items = items
        self.hover = None
        self.sub_owner = None
        width = self._width_for(items)
        rows, height = self._layout(items)
        panel = self._make_panel(0, items, width, height, rows)
        sw, sh = self.master.winfo_screenwidth(), self.master.winfo_screenheight()
        panel["x"] = min(max(int(x), 4), max(4, sw - width - 4))
        panel["y"] = min(max(int(y), 4), max(4, sh - height - 4))
        panel["win"].geometry(f"{width}x{height}+{panel['x']}+{panel['y']}")
        panel["win"].deiconify()
        panel["win"].lift()
        self.opened = True
        win = panel["win"]
        win.bind("<Motion>", self._on_motion)
        win.bind("<ButtonPress-1>", self._on_click)
        win.bind("<ButtonPress-3>", self._on_click)
        win.bind("<Escape>", lambda e: self.close())
        win.update_idletasks()
        try:
            win.grab_set_global()      # 全局抓取：面板外点击也能收到，用来关闭菜单
        except tk.TclError:
            pass
        try:
            win.focus_force()
        except tk.TclError:
            pass

    def close(self):
        self.opened = False
        self.hover = None
        self.sub_owner = None
        for panel in self.panels:
            try:
                panel["win"].grab_release()
            except Exception:
                pass
            try:
                panel["win"].destroy()
            except Exception:
                pass
        self.panels = []

    # ---- 命中判定 ----
    def _panel_at(self, xr, yr):
        for i in range(len(self.panels) - 1, -1, -1):
            p = self.panels[i]
            if p["x"] <= xr < p["x"] + p["w"] and p["y"] <= yr < p["y"] + p["h"]:
                return i
        return None

    def _row_at(self, index, yr):
        ry = yr - self.panels[index]["y"]
        for (idx, y0, y1, _it) in self.panels[index]["rows"]:
            if y0 <= ry < y1:
                return idx
        return None

    def _set_hover(self, value):
        if value == self.hover:
            return
        self.hover = value
        self._refresh()

    def _open_submenu(self, owner):
        if self.sub_owner == owner and len(self.panels) > 1:
            return
        self._close_submenu()
        sub_items = self.items[owner]["items"]
        width = self._width_for(sub_items)
        rows, height = self._layout(sub_items)
        panel = self._make_panel(1, sub_items, width, height, rows)
        parent = self.panels[0]
        row = next(r for r in parent["rows"] if r[0] == owner)
        sw, sh = self.master.winfo_screenwidth(), self.master.winfo_screenheight()
        x = parent["x"] + parent["w"] + 2
        if x + width > sw - 4:
            x = parent["x"] - width - 2
        y = parent["y"] + row[1]
        panel["x"] = min(max(x, 4), max(4, sw - width - 4))
        panel["y"] = min(max(y, 4), max(4, sh - height - 4))
        panel["win"].geometry(f"{width}x{height}+{panel['x']}+{panel['y']}")
        panel["win"].deiconify()
        panel["win"].lift()
        self.sub_owner = owner

    def _close_submenu(self):
        while len(self.panels) > 1:
            panel = self.panels.pop()
            try:
                panel["win"].destroy()
            except Exception:
                pass
        self.sub_owner = None

    # ---- 事件 ----
    def _on_motion(self, e):
        if not self.opened:
            return
        index = self._panel_at(e.x_root, e.y_root)
        if index is None:
            return                       # 面板之间的空隙：保持现状，避免子菜单闪烁
        idx = self._row_at(index, e.y_root)
        item = self.panels[index]["items"][idx] if idx is not None else None
        if index == 0 and item and item["type"] == "submenu":
            self._set_hover((0, idx))
            self._open_submenu(idx)
            return
        self._set_hover((index, idx) if idx is not None else None)
        if index == 0 and self.sub_owner is not None and idx != self.sub_owner:
            self._close_submenu()

    def _on_click(self, e):
        if not self.opened:
            return
        index = self._panel_at(e.x_root, e.y_root)
        if index is None:
            self.close()
            return
        idx = self._row_at(index, e.y_root)
        if idx is None:
            return
        item = self.panels[index]["items"][idx]
        if item["type"] in ("separator", "hint", "submenu"):
            return
        command = item.get("command")
        self.close()
        if command:
            self.master.after(10, command)


# ---------------- 番茄钟：倒计时由 PySide6 的 QTimer 驱动 ----------------
class Pomodoro:
    """QTimer 负责倒计时，但 Qt 事件循环不自己跑，
    而是由 Tk 的 after 定期调用 pump()（processEvents）带动。
    两个框架共用同一个线程、谁都不阻塞谁，所以界面绝不会卡死。
    """

    def __init__(self, qt_app, on_tick, on_finish):
        self.qt_app = qt_app
        self.on_tick = on_tick
        self.on_finish = on_finish
        self.running = False
        self.remaining = 0.0
        self._stamp = 0.0
        self.timer = QTimer()
        self.timer.setInterval(POMODORO_TICK_MS)
        self.timer.timeout.connect(self._tick)

    def start(self, minutes):
        self.remaining = float(minutes) * 60.0
        self._stamp = time.monotonic()
        self.running = True
        self.timer.start()
        self._emit()

    def stop(self):
        self.running = False
        try:
            self.timer.stop()
        except Exception:
            pass

    def _tick(self):
        now = time.monotonic()
        # 用真实时间差推进，定时器抖动/晚点都不会让倒计时跑偏
        self.remaining -= (now - self._stamp)
        self._stamp = now
        if self.remaining <= 0.0:
            self.remaining = 0.0
            self.stop()
            self._emit()
            self.on_finish()
            return
        self._emit()

    def _emit(self):
        self.on_tick(self.remaining)

    def pump(self):
        """在 Tk 的 after 回调里调用，让 QTimer 有机会触发。"""
        self.qt_app.processEvents()


def format_clock(seconds):
    seconds = max(0, int(math.ceil(seconds)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


# ---------------- 主程序 ----------------
class DesktopPet:
    def __init__(self, root: tk.Tk, frames, durations, box):
        self.root = root
        self.frames = frames
        self.durations = durations
        self.base_w, self.base_h = frames[0].size

        # 角色在图片中的实际位置（用于把气泡放到头顶）
        self.head_cx = ((box[0] + box[2]) / 2) / self.base_w
        self.head_top_ratio = box[1] / self.base_h

        self.key_rgb = tuple(int(TRANSPARENT_KEY.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))

        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-transparentcolor", TRANSPARENT_KEY)
            root.attributes("-toolwindow", True)
        except tk.TclError:
            pass
        root.configure(bg=TRANSPARENT_KEY)
        root.title("DesktopPet")

        self.label = tk.Label(root, bd=0, highlightthickness=0, bg=TRANSPARENT_KEY)
        self.label.pack()

        self.bubble = Bubble(root, TRANSPARENT_KEY)

        self.images = []
        self.idx = 0
        self.scale = 1.0
        self.anim_job = None
        self.press = None
        self.moved = False
        self.last_line = None
        self.paused = False
        self.rest_idx = centered_frame_index(frames)   # 人物居中那一帧
        self.palette = THEME_DARK if system_prefers_dark() else THEME_LIGHT
        self.opacity = 1.0
        self.topmost = True

        # 弹性 / 音效 / 番茄钟状态
        self.bouncing = False
        self._squish = [1.0, 1.0]
        self._squish_plan = None
        self._squish_frame = None
        self._squish_img = None
        self._squish_anchor_cx = 0
        self._squish_anchor_bottom = 0
        self.bounce_job = None
        self.alarm_job = None
        self.pump_job = None
        self.alarm_left = 0
        self.pomo_visible = False

        cfg = self._load_config()
        self.scale = float(cfg.get("scale") or self._default_scale())
        self.opacity = min(max(float(cfg.get("opacity") or 1.0), MIN_OPACITY), 1.0)
        self.sound = Sound(int(cfg.get("volume", SOUND_VOLUME_DEFAULT)))
        self._rebuild()
        self._place_window(cfg.get("x"), cfg.get("y"))
        self._apply_opacity()

        qt_app = None
        if QCoreApplication is not None:
            qt_app = QCoreApplication.instance() or QCoreApplication([])
        self.pomodoro = Pomodoro(qt_app, self._on_pomodoro_tick, self._on_pomodoro_finish) \
            if qt_app is not None else None

        self.menu = CatMenu(root, TRANSPARENT_KEY, self.palette)
        self.bubble.bind_click(self.on_bubble_click)
        for w in (root, self.label):
            w.bind("<ButtonPress-1>", self.on_press)
            w.bind("<B1-Motion>", self.on_drag)
            w.bind("<ButtonRelease-1>", self.on_release)
            w.bind("<Button-3>", self.on_right_click)
            w.bind("<MouseWheel>", self.on_wheel)
        root.bind("<Escape>", lambda e: self.quit())

        self.tick()

    # ---------- 配置 ----------
    def _default_scale(self):
        h = self.root.winfo_screenheight()
        target = min(max(h * 0.30, 160), 340)
        return min(max(target / self.base_h, MIN_SCALE), MAX_SCALE)

    def _load_config(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_config(self):
        try:
            data = self._load_config()      # 先读回来，保留用户自己写的键（例如 image）
            data.update({
                "scale": round(self.scale, 4),
                "opacity": round(self.opacity, 3),
                "volume": int(self.sound.volume),
                "x": self.root.winfo_x(),
                "y": self.root.winfo_y(),
            })
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------- 尺寸 ----------
    def _rebuild(self):
        w = max(24, int(round(self.base_w * self.scale)))
        h = max(24, int(round(self.base_h * self.scale)))
        images = []
        for f in self.frames:
            r = f.resize((w, h), Image.LANCZOS)
            alpha = r.getchannel("A").point(lambda v: 255 if v >= 128 else 0)
            bg = Image.new("RGB", (w, h), self.key_rgb)
            bg.paste(r, (0, 0), alpha)
            images.append(ImageTk.PhotoImage(bg))
        self.images = images
        if self.idx >= len(images):
            self.idx = 0
        self.label.configure(image=self.images[self.idx])
        self.root.geometry(f"{w}x{h}")

    def set_scale(self, scale, keep_center=True):
        scale = min(max(scale, MIN_SCALE), MAX_SCALE)
        if abs(scale - self.scale) < 1e-4:
            return
        old_w, old_h = self.root.winfo_width(), self.root.winfo_height()
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.scale = scale
        self._rebuild()
        if keep_center:
            new_w, new_h = self.root.winfo_width(), self.root.winfo_height()
            x += (old_w - new_w) // 2
            y += (old_h - new_h)      # 底部对齐，像站原地长高
        self._move(x, y)
        self._reposition_pomodoro()   # 大小变了，番茄钟气泡重新贴回头顶

    def _move(self, x, y):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        x = min(max(int(x), -w // 3), sw - w // 2)
        y = min(max(int(y), -h // 4), sh - h // 3)
        self.root.geometry(f"+{x}+{y}")

    def _place_window(self, x, y):
        self.root.update_idletasks()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        if x is None or y is None:
            x, y = sw - w - 60, sh - h - 90
        self._move(x, y)

    # ---------- 动画 ----------
    def tick(self):
        if self.paused:                     # 暂停后不再排新的定时器
            self.anim_job = None
            return
        if self.images:
            self.idx = (self.idx + 1) % len(self.images)
            if not self._squish_locked():   # 形变期间由弹性动画接管画面
                self.label.configure(image=self.images[self.idx])
            delay = self.durations[self.idx] if self.idx < len(self.durations) else 60
        else:
            delay = 100
        self.anim_job = self.root.after(delay, self.tick)

    # ---------- 点击弹性：按下压缩 → 松开回弹（鲸鱼挂件的做法） ----------
    def _squish_locked(self):
        return (self.bouncing
                or abs(self._squish[0] - 1.0) > 0.004
                or abs(self._squish[1] - 1.0) > 0.004)

    def squish(self, target):
        """把当前形变以 220ms 弹簧过渡到 target=(scaleY, scaleX)。"""
        if not self.images:
            return
        if self.bounce_job:
            try:
                self.root.after_cancel(self.bounce_job)
            except Exception:
                pass
            self.bounce_job = None
        if abs(target[0] - self._squish[0]) < 1e-3 and abs(target[1] - self._squish[1]) < 1e-3:
            return
        self.root.update_idletasks()
        self._squish_frame = self.frames[self.idx % len(self.frames)]
        self._squish_anchor_cx = self.root.winfo_x() + self.root.winfo_width() // 2
        self._squish_anchor_bottom = self.root.winfo_y() + self.root.winfo_height()
        self.bouncing = True
        self._squish_plan = (tuple(self._squish), tuple(target), 0)
        self._squish_tick()

    def _squish_tick(self):
        if not self._squish_plan:
            self.bouncing = False
            return
        start, target, step = self._squish_plan
        if step > SQUISH_STEPS:
            self._squish = [target[0], target[1]]
            self._squish_plan = None
            self._end_squish()
            return
        p = spring_ease(step / SQUISH_STEPS)      # 同一条 cubic-bezier(.34,1.56,.64,1)
        sy = start[0] + (target[0] - start[0]) * p
        sx = start[1] + (target[1] - start[1]) * p
        self._squish = [sy, sx]
        self._show_squished(self._squish_frame, sy, sx)
        self._squish_plan = (start, target, step + 1)
        self.bounce_job = self.root.after(max(16, SQUISH_MS // SQUISH_STEPS), self._squish_tick)

    def _show_squished(self, frame, sy, sx):
        w = max(24, int(round(self.base_w * self.scale * sx)))
        h = max(24, int(round(self.base_h * self.scale * sy)))
        r = frame.resize((w, h), Image.LANCZOS)
        alpha = r.getchannel("A").point(lambda v: 255 if v >= 128 else 0)
        bg = Image.new("RGB", (w, h), self.key_rgb)
        bg.paste(r, (0, 0), alpha)
        self._squish_img = ImageTk.PhotoImage(bg)   # 必须留引用，否则被 GC
        self.label.configure(image=self._squish_img)
        # transform-origin: 50% 100% —— 底部中心不动
        self.root.geometry(
            f"{w}x{h}+{self._squish_anchor_cx - w // 2}+{self._squish_anchor_bottom - h}"
        )

    def _end_squish(self):
        self.bouncing = False
        self.bounce_job = None
        if self._squish_locked():          # 还压着（按住不放）→ 保持形变
            return
        self._restore_normal_frame()

    def _restore_normal_frame(self):
        self._squish = [1.0, 1.0]
        w = max(24, int(round(self.base_w * self.scale)))
        h = max(24, int(round(self.base_h * self.scale)))
        self.label.configure(image=self.images[self.idx])
        self.root.geometry(f"{w}x{h}+{self._squish_anchor_cx - w // 2}"
                           f"+{self._squish_anchor_bottom - h}")

    def reset_squish(self):
        """拖动前先恢复原状，免得缩放和位移互相打架。"""
        if self.bounce_job:
            try:
                self.root.after_cancel(self.bounce_job)
            except Exception:
                pass
            self.bounce_job = None
        self._squish_plan = None
        self.bouncing = False
        if self.images and self._squish_locked():
            self._restore_normal_frame()
        self._squish = [1.0, 1.0]

    # ---------- 暂停 / 继续 ----------
    def toggle_pause(self):
        self.resume() if self.paused else self.pause()

    def pause(self):
        """定格在人物居中的那一帧，同时取消后台动画定时器。"""
        if self.paused or len(self.images) <= 1:
            return
        if self.anim_job:
            try:
                self.root.after_cancel(self.anim_job)
            except Exception:
                pass
            self.anim_job = None
        self.paused = True
        self.idx = self.rest_idx % len(self.images)
        self.reset_squish()
        self.label.configure(image=self.images[self.idx])

    def resume(self):
        if not self.paused:
            return
        self.paused = False
        self.tick()

    # ---------- 鼠标 ----------
    def on_press(self, e):
        self.press = (e.x_root, e.y_root, self.root.winfo_x(), self.root.winfo_y(), time.monotonic())
        self.moved = False
        self.sound.play("press")            # 鲸鱼挂件：按下先响一声
        self.squish(SQUISH_DOWN)            # 按下 → 压扁（底部中心为原点）

    def on_drag(self, e):
        if not self.press:
            return
        px, py, wx, wy, _ = self.press
        dx, dy = e.x_root - px, e.y_root - py
        if not self.moved and (abs(dx) > DRAG_THRESHOLD or abs(dy) > DRAG_THRESHOLD):
            self.moved = True
            self.reset_squish()             # 开始拖了就先恢复原状
            if not self.pomo_visible:
                self.bubble.hide()
        if self.moved:
            self._move(wx + dx, wy + dy)
            self._reposition_pomodoro()     # 番茄钟气泡跟着角色走

    def on_release(self, e):
        if not self.press:
            return
        _, _, _, _, t0 = self.press
        quick = (time.monotonic() - t0) <= CLICK_MAX_SECONDS
        self.press = None
        self.sound.play("release")          # 松开回弹音
        self.squish(SQUISH_UP)              # 松开 → 弹回原状
        if not self.moved and quick:
            self.on_pet_click()

    def on_pet_click(self):
        """点角色：换台词；番茄钟没在跑的时候才换，避免和倒计时打架。"""
        if not self.pomo_visible:
            self.say_random()

    def on_bubble_click(self, _event=None):
        """点气泡：换下一句台词。番茄钟期间保持显示剩余时间，不乱变。"""
        if self.pomo_visible:
            return
        self.sound.play("release")
        self.say_random()

    def on_right_click(self, e):
        self.bubble.hide()
        self.menu.popup(e.x_root, e.y_root, self._menu_items())

    def on_wheel(self, e):
        if e.state & 0x0004:        # Ctrl + 滚轮 → 调不透明度
            self.set_opacity(self.opacity + (0.05 if e.delta > 0 else -0.05))
        else:                       # 滚轮 → 调大小
            self.set_scale(self.scale * (1.08 if e.delta > 0 else 1 / 1.08))

    # ---------- 台词气泡 ----------
    def say_random(self):
        if self.pomo_visible:      # 番茄钟期间气泡属于倒计时，不能被台词顶掉
            return
        pool = [ln for ln in LINES if ln != self.last_line] or LINES
        self.last_line = random.choice(pool)
        self.say(self.last_line)

    def say(self, text):
        master, x, y, tail_ratio = self._layout_bubble(text)
        self.bubble.show(master, x, y, self.bubble.hide, tail_ratio=tail_ratio)

    def _layout_bubble(self, text):
        """算出气泡该摆在哪（头顶优先，放不下自动翻到下方/贴边），返回成品图与坐标。"""
        root = self.root
        root.update_idletasks()
        pw, ph = root.winfo_width(), root.winfo_height()
        px, py = root.winfo_x(), root.winfo_y()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()

        head_cx = px + pw * self.head_cx
        head_top = py + ph * self.head_top_ratio

        # 先按“尾巴朝下”量一遍尺寸，再按实际落点重画尾巴位置
        probe = self.bubble.build(text, 0.5, True)
        W, H = probe.size

        x = head_cx - W / 2
        y = head_top - 8 - H
        tail_down = True
        if y < 4:                     # 头顶放不下 → 改到角色下方，尾巴朝上
            tail_down = False
            y = py + ph + 6
            if y + H > sh - 4:
                y = max(4, sh - H - 4)

        x = min(max(x, 4), max(4, sw - W - 4))
        y = min(max(y, 4), max(4, sh - H - 4))

        tail_ratio = (head_cx - x) / W if W else 0.5
        return self.bubble.build(text, tail_ratio, tail_down), int(x), int(y), tail_ratio

    # ---------- 番茄钟 ----------
    def start_pomodoro(self):
        if self.pomodoro is None or self.pomodoro.running:
            return
        self.pomo_visible = True
        self._pomo_first = True
        self.pomodoro.start(POMODORO_MINUTES)
        self._pump_qt()

    def stop_pomodoro(self):
        self._cancel_alarm()
        if self.pomodoro is not None:
            self.pomodoro.stop()
        self.pomo_visible = False
        self.bubble.hide()

    def _pump_qt(self):
        """让 QTimer 有机会触发；番茄钟跑着的时候才需要泵。"""
        if self.pomodoro is not None and self.pomodoro.running:
            self.pomodoro.pump()
            self.pump_job = self.root.after(30, self._pump_qt)
        else:
            self.pump_job = None

    def _pomodoro_text(self, remaining):
        return f"🍅 专注中 {format_clock(remaining)}"

    def _on_pomodoro_tick(self, remaining):
        if not self.pomo_visible:
            return
        self._show_pomodoro_bubble(self._pomodoro_text(remaining))

    def _on_pomodoro_finish(self):
        self.sound.play("chime")
        self.alarm_left = ALARM_SECONDS
        self._show_pomodoro_bubble("🍅 时间到啦，休息一下～")
        self._alarm_tick()

    def _alarm_tick(self):
        if self.alarm_left <= 0:
            self.alarm_job = None
            self.pomo_visible = False
            self.bubble.hide()
            return
        if self.alarm_left < ALARM_SECONDS:      # 第一声已经在完成时播过
            self.sound.play("chime")
        self.alarm_left -= 1
        self.alarm_job = self.root.after(1000, self._alarm_tick)

    def _cancel_alarm(self):
        if self.alarm_job:
            try:
                self.root.after_cancel(self.alarm_job)
            except Exception:
                pass
            self.alarm_job = None
        self.alarm_left = 0
        self.sound.stop()

    def _show_pomodoro_bubble(self, text, first=False):
        master, x, y, tail_ratio = self._layout_bubble(text)
        if first or self._pomo_first:
            self._pomo_first = False
            self.bubble.show(master, x, y, None, persistent=True, tail_ratio=tail_ratio)
        else:
            self.bubble.update_in_place(master, x, y, tail_ratio)

    def _reposition_pomodoro(self):
        """角色被拖动时，让番茄钟气泡重新贴回头顶。"""
        if not self.pomo_visible or not self.bubble.is_visible():
            return
        if self.pomodoro is not None and self.pomodoro.running:
            text = self._pomodoro_text(self.pomodoro.remaining)
        else:
            text = "🍅 时间到啦，休息一下～"
        self._show_pomodoro_bubble(text)

    # ---------- 菜单 ----------
    def _menu_items(self):
        """按 BongoCat 的菜单逻辑组织：勾选态 + 子菜单 + 灰色提示行。"""
        cur = self.scale * 100
        sizes = [
            {"type": "command", "label": "放大　(+)",
             "command": lambda: self.set_scale(self.scale * 1.12)},
            {"type": "command", "label": "缩小　(-)",
             "command": lambda: self.set_scale(self.scale / 1.12)},
            {"type": "separator"},
        ]
        for name, value in SCALE_PRESETS:
            pct = int(round(value * 100))
            sizes.append({
                "type": "command", "label": f"{name}　{pct}%",
                "checked": abs(cur - pct) < 5,
                "command": (lambda v=value: self.set_scale(v)),
            })
        sizes += [
            {"type": "separator"},
            {"type": "command", "label": "恢复默认大小",
             "command": lambda: self.set_scale(self._default_scale())},
            {"type": "hint", "label": "滚轮也可以调整大小"},
        ]

        cur_op = round(self.opacity * 100)
        opacity = [
            {"type": "command", "label": f"{pct}%", "checked": abs(cur_op - pct) < 5,
             "command": (lambda v=pct: self.set_opacity(v / 100.0))}
            for pct in OPACITY_PRESETS
        ]
        opacity += [
            {"type": "separator"},
            {"type": "hint", "label": "Ctrl + 滚轮 也可以调整"},
        ]

        # ---- 番茄钟 ----
        if self.pomodoro is None:
            tomato = [{"type": "hint", "label": "需要 PySide6（pip install PySide6）"}]
        elif self.pomodoro.running:
            tomato = [
                {"type": "command",
                 "label": f"专注中 {format_clock(self.pomodoro.remaining)}", "checked": True,
                 "command": None},
                {"type": "command", "label": "停止番茄钟", "command": self.stop_pomodoro},
            ]
        else:
            tomato = [
                {"type": "command", "label": f"开始专注（{POMODORO_MINUTES} 分钟）",
                 "command": self.start_pomodoro},
                {"type": "hint", "label": "停止番茄钟"},
            ]

        # ---- 音量 ----
        volume = [
            {"type": "command", "label": f"{pct}%", "checked": self.sound.volume == pct,
             "command": (lambda v=pct: self.set_volume(v))}
            for pct in VOLUME_PRESETS
        ]
        volume += [
            {"type": "separator"},
            {"type": "hint", "label": "点击角色和气泡都会响"},
        ]

        line_item = ({"type": "hint", "label": "换一句台词（番茄钟中不可用）"}
                     if self.pomo_visible else
                     {"type": "command", "label": "换一句台词", "command": self.say_random})

        return [
            {"type": "command", "label": "继续动画" if self.paused else "暂停动画",
             "command": self.toggle_pause},
            line_item,
            {"type": "separator"},
            {"type": "submenu", "label": "番茄钟", "items": tomato},
            {"type": "submenu", "label": "窗口大小", "items": sizes},
            {"type": "submenu", "label": "不透明度", "items": opacity},
            {"type": "submenu", "label": "音效音量", "items": volume},
            {"type": "command", "label": "窗口置顶", "checked": self.topmost,
             "command": self.toggle_topmost},
            {"type": "separator"},
            # 延后一点再退出，先让菜单收起，避免 Tcl 报错
            {"type": "command", "label": "退出",
             "command": lambda: self.root.after(10, self.quit)},
        ]

    # ---------- 音量 ----------
    def set_volume(self, volume):
        self.sound.set_volume(volume)
        self.sound.play("release")       # 立即试听

    # ---------- 置顶 / 不透明度 ----------
    def toggle_topmost(self):
        self.topmost = not self.topmost
        self.root.attributes("-topmost", self.topmost)

    def _apply_opacity(self):
        try:
            self.root.attributes("-alpha", self.opacity)
        except tk.TclError:
            pass

    def set_opacity(self, value):
        value = min(max(value, MIN_OPACITY), 1.0)
        if abs(value - self.opacity) < 1e-3:
            return
        self.opacity = value
        self._apply_opacity()

    # ---------- 退出 ----------
    def quit(self):
        for job in (self.anim_job, self.bounce_job, self.alarm_job, self.pump_job):
            if job:
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass
        self.anim_job = self.bounce_job = self.alarm_job = self.pump_job = None
        if self.pomodoro is not None:
            self.pomodoro.stop()
        self.sound.stop()
        self._save_config()
        try:
            self.menu.close()
        except Exception:
            pass
        self.bubble.destroy()
        try:
            self.root.quit()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
        os._exit(0)


def pick_image_path():
    """按优先级挑角色图：环境变量 > pet_config.json 的 image > 顶部 IMAGE_PATH。"""
    candidates = [os.environ.get("DESKTOP_PET_IMAGE")]
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            candidates.append(json.load(f).get("image"))
    except Exception:
        pass
    candidates.append(IMAGE_PATH)
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return candidates[-1]


def main():
    enable_dpi_awareness()

    image_path = pick_image_path()
    if not os.path.exists(image_path):
        r = tk.Tk()
        r.withdraw()
        from tkinter import messagebox
        messagebox.showerror(
            "桌面宠物 / Desktop Pet",
            f"找不到角色图片：\n{image_path}\n\n"
            "请把你的 GIF/PNG 放到 assets/pet.gif，\n"
            "或修改 desktop_pet.py 顶部的 IMAGE_PATH。",
        )
        r.destroy()
        return

    frames, durations = load_frames(image_path)
    box = content_box(frames)

    root = tk.Tk()
    DesktopPet(root, frames, durations, box)
    root.mainloop()


if __name__ == "__main__":
    main()
