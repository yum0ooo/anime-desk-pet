# -*- coding: utf-8 -*-
"""
桌面宠物小摆件 · PySide6 版  Desktop Pet (Qt)
================================================
Tkinter 版 desktop_pet.py 的 1:1 功能移植 + AI 聊天 / 亲密值 / 双阶段番茄钟。

--------------------------------------------------------------------------
★ 点击优先级规则（唯一权威实现见 DesktopPet.handle_click，改这里必须同步改注释）
--------------------------------------------------------------------------
左键单击角色时，严格按下面的顺序判断，命中即返回：

  1. 番茄钟正在响铃（state ∈ {FOCUS_RINGING, BREAK_RINGING}）
     → 只做「关掉铃声 + 立刻进入下一阶段」，并弹跳 + 按下/松开音效。
       **绝不打开 AI 输入框，绝不把气泡改成聊天提示。**
  2. AI 输入框已经打开
     → 只是把它重新聚焦（activateWindow + setFocus），不重复开第二个。
  3. 番茄钟某个阶段正在倒计时（state ∈ {FOCUS, BREAK}）
     → 只弹跳，气泡继续显示倒计时，**不劫持成聊天提示**。
  4. 其它情况（IDLE）
     → 走 AI 聊天流程：弹跳 → 气泡傲娇提示 → 角色下方弹出输入框。

附带：任何一次左键点击都会先结算「今天的第一次点击」（+1 亲密值，每天一次）。

--------------------------------------------------------------------------
★ 番茄钟状态机（两阶段循环，只能靠点击或菜单停止）
--------------------------------------------------------------------------
    IDLE ──开始专注──► FOCUS(25min) ──倒计时归零──► FOCUS_RINGING
                                                       │ 左键点击
                                                       ▼
                    BREAK_RINGING ◄──倒计时归零── BREAK(10min)
                          │ 左键点击
                          └──────────► FOCUS ...

  · *_RINGING 状态下铃声每 ALARM_REPEAT_MS 重复一次，**不会自己停**。
  · 只有左键点击角色（或菜单「停止番茄钟」/退出程序）才能结束响铃。
  · 菜单「停止番茄钟」结束整个循环：停铃、取消所有定时器、隐藏气泡。

--------------------------------------------------------------------------
其它要点
--------------------------------------------------------------------------
· 真·逐像素透明（Qt.WA_TranslucentBackground + FramelessWindowHint）。
· 角色图 / 气泡图一律按 **物理像素** 渲染：先用 PIL Image.LANCZOS 放大到
  size * devicePixelRatioF()，再 pixmap.setDevicePixelRatio(dpr)，
  这样 Qt 是 1:1 贴图，不再被 DPR 二次重采样 —— 高分屏下不再发虚。
· 空闲时窗口 **纹丝不动**（没有呼吸/漂浮动画）；只有左键点击的弹跳动画。
· 台词气泡是 QLabel 子类窗口，背景 bubble.png，文字画在白椭圆内部，鼠标穿透。
· AI 请求在 QThread 里跑，GUI 线程永不阻塞；回复用 QTimer 逐字打字机输出。
· API Key 只放在同目录的 config.json，绝不写进 pet_config.json、绝不硬编码。
· 音效沿用本地正弦合成 + winsound 播放 + sounds/ 目录 WAV 缓存。
· 右键菜单用 QMenu + Qt Style Sheets 圆角卡片，跟随系统深浅色。
"""
import array
import ctypes
import json
import math
import os
import random
import sys
import time
import urllib.error
import urllib.request
import wave
from datetime import date
from pathlib import Path

from PySide6.QtCore import (
    Property, QAbstractAnimation, QEasingCurve, QEvent, QPoint,
    QPropertyAnimation, QRect, Qt, QThread, QTimer, Signal,
)
from PySide6.QtGui import (
    QColor, QFont, QGuiApplication, QImage, QPainter, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QLabel, QLineEdit, QMenu, QMessageBox,
)

from PIL import Image

try:
    import winsound
except ImportError:            # 非 Windows 平台静音运行
    winsound = None

try:
    import winreg
except ImportError:
    winreg = None

# ============================================================
#  ★ 素材路径（角色图 / 气泡图，改成你自己的图片即可，透明 PNG）
#    默认取本文件同级的同名文件，所以整个文件夹可以随便搬。
# ============================================================
HERE = Path(__file__).resolve().parent
IMAGE_PATH = str(HERE / "assets" / "pet_character.png")
BUBBLE_PATH = str(HERE / "assets" / "bubble.png")

# ---------------- 可调参数 ----------------
BUBBLE_MS = 2500              # 气泡停留时间（毫秒）
MIN_SCALE, MAX_SCALE = 0.25, 2.0
DRAG_THRESHOLD = 4            # 位移小于该像素视为“点击”
CLICK_MAX_SECONDS = 0.6
MIN_OPACITY = 0.20

# ---------------- 弹跳（唯一的动画；空闲不呼吸、不漂浮）----------------
JUMP_MS = 520                 # 单击弹跳总时长
JUMP_KEYS = ((0.0, 0), (0.28, -34), (0.62, 0), (0.82, -12), (1.0, 0))  # 跳一下 + 小回弹

# ---------------- 气泡文字排版（白色椭圆内部，避开下面两个小尾巴圆点）----------------
BUBBLE_TEXT_FAMILY = "Microsoft YaHei"
BUBBLE_TEXT_SIZE = 13.5       # pt
BUBBLE_TEXT_RATIO = 0.62      # 椭圆正文区高度占整张气泡图的比例
BUBBLE_TEXT_INSET = 0.09      # 左右各内缩 9%
BUBBLE_TEXT_COLOR = "#203170"  # 气泡描边那种深海军蓝
BUBBLE_MIN_SCALE = 0.55       # 气泡相对于原图的最小缩放
BUBBLE_MAX_SCALE = 1.30
BUBBLE_TAIL_OFFSET = 6        # 尾巴圆点正下方那一点点留白
BUBBLE_ANIM_MS = 180          # 弹出时的淡入时长
BUBBLE_FADE_MS = 140          # 消失时的淡出时长

# ---------------- 菜单外观（BongoCat 自绘菜单的深/浅色表）----------------
MENU_FONT_SIZE = 10           # pt
MENU_RADIUS = 12
MENU_MIN_W = 200
MENU_ROW_H = 30
MENU_PAD_Y = 6
THEME_DARK = {
    "surface": "#21242b", "field": "#2a2e37", "border": "#3b424f",
    "text": "#f4f7fb", "muted": "#9aa4b2", "accent": "#54aeff",
}
THEME_LIGHT = {
    "surface": "#ffffff", "field": "#f3f5f8", "border": "#d8dee8",
    "text": "#182230", "muted": "#667085", "accent": "#54aeff",
}
SCALE_PRESETS = (("迷你", 0.50), ("小", 0.70), ("标准", 0.90), ("大", 1.10), ("超大", 1.30))
OPACITY_PRESETS = (100, 90, 80, 70, 60, 50, 40, 30, 20)

# ============================================================
#  ★ 番茄钟 / 音效参数（改这里就行）
# ============================================================
POMODORO_MINUTES = 25          # ★ 专注时长（分钟）。测试时可临时改成 1
BREAK_MINUTES = 10             # ★ 休息时长（分钟）
POMODORO_TICK_MS = 200         # QTimer 间隔，只影响刷新频率，不影响计时精度
ALARM_REPEAT_MS = 1400         # 响铃重复间隔（毫秒）——响铃不会自己停，只能点击/菜单停
SOUND_VOLUME_DEFAULT = 65      # 默认音量 0-100
VOLUME_PRESETS = (0, 25, 50, 75, 100)
SAMPLE_RATE = 44100

# 番茄钟状态常量
POMO_IDLE = "IDLE"
POMO_FOCUS = "FOCUS"
POMO_FOCUS_RINGING = "FOCUS_RINGING"
POMO_BREAK = "BREAK"
POMO_BREAK_RINGING = "BREAK_RINGING"
POMO_RINGING_STATES = (POMO_FOCUS_RINGING, POMO_BREAK_RINGING)
POMO_RUNNING_STATES = (POMO_FOCUS, POMO_BREAK)

POMO_TEXT_FOCUS = "🍅 专注中 {clock}"
POMO_TEXT_BREAK = "🍅 休息中 {clock}"
POMO_TEXT_FOCUS_DONE = "🍅 时间到！点我一下"
POMO_TEXT_BREAK_DONE = "🍅 休息结束，点我一下"

# ============================================================
#  ★ 亲密值系统（持久化在 pet_config.json 里）
# ============================================================
AFFECTION_MIN = 0
AFFECTION_MAX = 100
AFFECTION_DEFAULT = 50                    # 首次运行的默认值
AFFECTION_CLICK_GAIN = 1                  # 每天第一次点击 +1
AFFECTION_CHAT_GAIN = 2                   # 每天第一次发消息 +2
AFFECTION_IDLE_PENALTY = 1                # 一整天没点击也没聊天 -1
AFFECTION_MAX_PENALTY_PER_STARTUP = 10    # 单次结算最多扣 10，防止一次掉到 0
AFFECTION_GREETING_MIN = 70               # ≥ 该值启动时会主动关心一句
AFFECTION_GREETING_DELAY_MS = 1200        # 启动后约 1.2 秒说
AFFECTION_GREETINGS = [
    "今天也要好好喝水哦。",
    "回来啦？我一直在等你。",
    "别老盯着屏幕，眼睛会坏的。",
    "今天也要加油，我在这儿陪着你。",
    "记得按时吃饭，笨蛋。",
    "累的话就靠一会儿，我不吵你。",
]
AFFECTION_KEYS = ("affection", "affection_date", "clicked_today", "chatted_today")

# ============================================================
#  ★ AI 聊天参数（Token 经济：越短越省钱）
# ============================================================
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
AI_MAX_TOKENS = 160                      # 回复上限：很小，够 1~2 句
AI_TEMPERATURE = 1.1
AI_HISTORY_TURNS = 3                     # 内存里最多保留 3 轮（6 条消息）
AI_MAX_INPUT_CHARS = 300                 # 用户输入硬截断
AI_TIMEOUT_S = 20                        # 单次请求超时（秒）
AI_TYPING_MS = 45                        # 打字机：每个字 45ms，由 QTimer 驱动
AI_WAITING_TEXT = "……"
AI_PROMPT_LINE = "有什么事要和我说吗？人家可是很忙的……"
AI_ERROR_NO_KEY = "唔…你还没给我钥匙呢！去 config.json 里填上 deepseek_api_key 吧。"
AI_ERROR_LINE = "唔…信号好像不太好，等下再试一次好不好？"
AI_ERROR_EMPTY = "哼，你就给我这么点东西？再想一句啦。"
AI_CHAT_PLACEHOLDER = "说点什么…（回车发送 / Esc 取消）"
AI_CHAT_IDLE_MS = 15000                  # 点击角色后 15 秒无操作 → 自动收起输入框和气泡

# 紧凑人设提示词：唯一能显著省 token 的地方（< ~120 tokens）
AI_SYSTEM_PROMPT = (
    "你是桌面宠物里的傲娇动漫少女「小宠」。"
    "用中文口语回答，语气傲娇但心里关心对方，偶尔加「哼」「才不是」。"
    "回复必须极短：1~2 句、40 字以内、不要表情、不要换行、不说教、不解释。"
)

# AI Key 配置文件（独立于 pet_config.json，绝不硬编码，绝不混在一起）
# 真正的 CONFIG_PATH 在下面 app_dir() 定义之后绑定
DEFAULT_AI_CONFIG = {
    "deepseek_api_key": "",
    "deepseek_model": DEEPSEEK_MODEL,
    "deepseek_base_url": DEEPSEEK_BASE_URL,
}

# ---------------- 台词库（旧版点击循环台词，现已不再绑定到点击，
#                  仅保留给 say_random() 内部/外部调用者使用）----------------
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
]


# ---------------- 路径工具 ----------------
def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


PET_CONFIG_PATH = app_dir() / "pet_config.json"    # 宠物自己的状态（位置/大小/亲密值）
CONFIG_PATH = app_dir() / "config.json"            # ★ DeepSeek API Key（独立文件）
SOUND_DIR = app_dir() / "sounds"


def enable_dpi_awareness() -> None:
    """让窗口在高分屏下保持清晰、坐标不缩放。必须在 QApplication 之前调用。"""
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


def apply_high_dpi_policy() -> None:
    """DPR 取真实小数（PassThrough），否则 1.25 会被四舍五入成 1.0 → 贴图发虚。
    必须在 QApplication 构造之前调用。"""
    try:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass


def system_prefers_dark() -> bool:
    """读取 Windows 个性化设置里的“应用模式”，跟随系统深浅色。"""
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as k:
            value, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
        return int(value) == 0
    except Exception:
        return False


# ---------------- 素材加载 ----------------
def load_image(path: str) -> Image.Image:
    """读取图片（GIF 取第一帧），返回 RGBA。"""
    im = Image.open(path)
    try:
        im.seek(0)
    except Exception:
        pass
    return im.convert("RGBA")


def content_box(rgba: Image.Image):
    """非透明区域的包围盒，用于定位“头顶”。"""
    bb = rgba.getchannel("A").point(lambda v: 255 if v >= 128 else 0).getbbox()
    return bb or (0, 0, rgba.width, rgba.height)


def pil_to_pixmap(rgba: Image.Image) -> QPixmap:
    data = rgba.tobytes("raw", "RGBA")
    img = QImage(data, rgba.width, rgba.height, rgba.width * 4,
                 QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(img)


def render_physical(source: Image.Image, logical_w: int, logical_h: int,
                    dpr: float) -> QPixmap:
    """★ 清晰度的核心：按「物理像素」渲染，再把 DPR 告诉 Qt。

    PIL 用 LANCZOS 高质量重采样到 logical * dpr，然后 pixmap.setDevicePixelRatio(dpr)，
    Qt 就会 1:1 直接 blit 到屏幕，不会再用 DPR 二次放大（那才是发虚的根因）。
    """
    dpr = float(dpr) if dpr and dpr > 0 else 1.0
    pw = max(1, int(round(logical_w * dpr)))
    ph = max(1, int(round(logical_h * dpr)))
    pm = pil_to_pixmap(source.resize((pw, ph), Image.LANCZOS))
    pm.setDevicePixelRatio(dpr)
    return pm


# ============================================================
#  config.json（DeepSeek API Key）读写
# ============================================================
def ensure_ai_config(path: Path = None) -> Path:
    """config.json 不存在（或坏了）就自动补一份空 Key 的，让用户知道该填哪儿。"""
    path = Path(path or CONFIG_PATH)
    need = True
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                merged = dict(DEFAULT_AI_CONFIG)
                merged.update({k: v for k, v in data.items() if k in merged})
                if merged != data:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(merged, f, ensure_ascii=False, indent=2)
                need = False
        except Exception:
            need = True
    if need:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_AI_CONFIG, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    return path


def load_ai_config(path: Path = None) -> dict:
    """读取 config.json（缺字段自动补默认值）。读不到就返回一份默认值，绝不抛异常。"""
    path = ensure_ai_config(path)
    data = dict(DEFAULT_AI_CONFIG)
    try:
        with open(path, "r", encoding="utf-8") as f:
            got = json.load(f)
        if isinstance(got, dict):
            for key in data:
                if key in got and got[key] is not None:
                    data[key] = got[key]
    except Exception:
        pass
    return data


# ============================================================
#  亲密值：纯函数，方便测试直接调用
# ============================================================
def _today_str(today=None) -> str:
    if today:
        return str(today)
    return date.today().isoformat()


def clamp_affection(value) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = AFFECTION_DEFAULT
    return max(AFFECTION_MIN, min(AFFECTION_MAX, v))


def settle_affection(cfg: dict, today=None) -> int:
    """按“天”结算亲密值，就地在 cfg 里改，返回本次扣除的点数。

    规则：
      · 同一天重复调用 → 什么都不改（幂等，重启再调也安全）。
      · 日期翻篇 → 上一记录日若「既没点击也没聊天」扣 1；中间每整整跳过一天再扣 1；
        单次结算总扣分封顶 AFFECTION_MAX_PENALTY_PER_STARTUP，且最终钳在 0..100。
      · 首次运行（没有 affection_date）→ 不扣分，只落地默认值。
    """
    if not isinstance(cfg, dict):
        return 0
    today = _today_str(today)
    aff = clamp_affection(cfg.get("affection", AFFECTION_DEFAULT))
    last = cfg.get("affection_date")

    if last == today:                      # 同一天，幂等：一个字节都不动
        cfg["affection"] = aff
        return 0

    penalty = 0
    if isinstance(last, str) and last.strip():
        try:
            d_last = date.fromisoformat(last.strip())
            d_today = date.fromisoformat(today)
        except ValueError:
            d_last = d_today = None
        if d_last is not None and d_last < d_today:
            interacted = bool(cfg.get("clicked_today")) or bool(cfg.get("chatted_today"))
            missed = 0 if interacted else 1                 # 上一记录日本身
            missed += max(0, (d_today - d_last).days - 1)   # 中间整段跳过的日子
            penalty = min(missed, AFFECTION_MAX_PENALTY_PER_STARTUP)

    cfg["affection"] = clamp_affection(aff - penalty * AFFECTION_IDLE_PENALTY)
    cfg["affection_date"] = today
    cfg["clicked_today"] = False
    cfg["chatted_today"] = False
    return penalty


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
    """松开：音高往上弹，脆一点。"""
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
        self.played = []          # 记录最近播放的名字，方便测试断言（不影响运行）
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
        self.played.append(name)
        del self.played[:-64]
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


# ============================================================
#  AI：DeepSeek 调用 + 后台线程
# ============================================================
class AIError(Exception):
    """带错误码的 AI 异常：code ∈ {no_key, network, http, bad_response}。"""

    def __init__(self, code, detail=""):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


def deepseek_chat(messages, *, api_key, base_url=DEEPSEEK_BASE_URL,
                  model=DEEPSEEK_MODEL, timeout=AI_TIMEOUT_S) -> str:
    """一次非流式 chat/completions 调用。只用标准库 urllib，无第三方依赖。

    这个函数 **必须在工作线程里被调用**（GUI 线程调用会阻塞界面）。
    测试里会把它整个 monkey-patch 掉，所以它保持模块级、按名字查找。
    """
    key = str(api_key or "").strip()
    if not key:
        raise AIError("no_key", "deepseek_api_key is empty")
    url = str(base_url or DEEPSEEK_BASE_URL).rstrip("/") + "/chat/completions"
    payload = {
        "model": model or DEEPSEEK_MODEL,
        "messages": messages,
        "stream": False,
        "max_tokens": AI_MAX_TOKENS,
        "temperature": AI_TEMPERATURE,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        raise AIError("http", f"HTTP {exc.code} {detail}") from exc
    except Exception as exc:                       # URLError / timeout / DNS / 断网
        raise AIError("network", repr(exc)) from exc
    try:
        data = json.loads(raw.decode("utf-8"))
        text = data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise AIError("bad_response", repr(exc)) from exc
    return str(text or "").strip()


class ChatThread(QThread):
    """★ 把 HTTP 请求扔到 GUI 线程之外。信号回主线程，界面全程不卡。"""

    replied = Signal(str)
    failed = Signal(str, str)          # (code, detail)

    def __init__(self, messages, api_key, base_url, model, parent=None):
        super().__init__(parent)
        self.messages = messages
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def run(self):                      # 在子线程执行
        try:
            text = deepseek_chat(
                self.messages, api_key=self.api_key,
                base_url=self.base_url, model=self.model,
            )
        except AIError as exc:
            self.failed.emit(exc.code, exc.detail)
            return
        except Exception as exc:        # 兜底：绝不让异常掀翻线程
            self.failed.emit("network", repr(exc))
            return
        if not text:
            self.failed.emit("bad_response", "empty content")
            return
        self.replied.emit(text)


# ============================================================
#  台词气泡：QLabel 子类，背景是 bubble.png，文字画在白色椭圆中间
# ============================================================
class BubbleLabel(QLabel):
    """无边框透明气泡窗口（背景按物理像素渲染，不发虚）。

    背景绘制 bubble.png（按 devicePixelRatio 渲染到物理分辨率），文字用
    QPainter.drawText 居中画在上面那个白色椭圆内部（整图顶部 ~62% 高度、
    左右各内缩 9%），这样绝不会压到下面两个小尾巴圆点。
    窗口设置 WA_TransparentForMouseEvents，点气泡等于点在桌面上。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._source = QPixmap(BUBBLE_PATH)
        try:
            self._source_img = load_image(BUBBLE_PATH)
        except Exception:
            self._source_img = None
        self._text = ""
        self._font = QFont(BUBBLE_TEXT_FAMILY, BUBBLE_TEXT_SIZE)
        self._color = QColor(BUBBLE_TEXT_COLOR)
        self._fade = 1.0
        self._render_dpr = 0.0
        self._bubble_pm = None
        self._bubble_w = max(120, self._source.width() if not self._source.isNull() else 224)
        self._bubble_h = int(round(self._bubble_w * (
            (self._source.height() / self._source.width())
            if (not self._source.isNull() and self._source.width()) else (196 / 224)
        )))
        self._render()
        self.set_text("")
        self.hide()

    # ---------- 尺寸 / 文本 ----------
    def _dpr(self) -> float:
        try:
            d = float(self.devicePixelRatioF())
        except Exception:
            d = 1.0
        return d if d > 0 else 1.0

    def _render(self):
        """按物理分辨率渲染气泡背景（LANCZOS + setDevicePixelRatio）。"""
        if self._source_img is None:
            return
        dpr = self._dpr()
        self._bubble_pm = render_physical(
            self._source_img, self._bubble_w, self._bubble_h, dpr)
        self._render_dpr = dpr

    def rerender(self):
        """DPR 变了 / 需要重建时调用。"""
        if abs(self._render_dpr - self._dpr()) > 1e-6 or self._bubble_pm is None:
            self._render()
        self.update()

    def set_bubble_width(self, width: int) -> None:
        """按角色头部宽度自适应气泡大小（保持原图比例）。"""
        width = int(max(120, min(520, width)))
        if self._source.isNull():
            return
        ratio = self._source.height() / self._source.width()
        self._bubble_w = width
        self._bubble_h = max(60, int(round(width * ratio)))
        self._render()
        self.resize(self._bubble_w, self._bubble_h)

    def set_text(self, text: str) -> None:
        self._text = text or ""
        self.setToolTip(self._text)
        self.update()

    def text(self) -> str:
        return self._text

    def showEvent(self, event):          # noqa: N802
        super().showEvent(event)
        self.rerender()

    def ellipse_rect(self) -> QRect:
        """文字要被画进去的矩形（白色椭圆内部）。"""
        w, h = self._bubble_w, self._bubble_h
        inset = int(round(w * BUBBLE_TEXT_INSET))
        top = int(round(h * 0.055))
        height = int(round(h * BUBBLE_TEXT_RATIO)) - top
        return QRect(inset, top, max(10, w - inset * 2), max(10, height))

    # ---------- 淡入淡出（画在画布里，窗口本身始终不透明，截屏/置顶都稳） ----------
    def _get_fade(self):
        return self._fade

    def _set_fade(self, value):
        self._fade = min(max(float(value), 0.0), 1.0)
        self.setWindowOpacity(1.0)      # 窗口不透明度永远满，避免和动画互相覆盖
        self.update()

    fadeOpacity = Property(float, _get_fade, _set_fade)

    # ---------- 绘制 ----------
    def paintEvent(self, event):        # noqa: N802 (Qt 命名)
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        painter.setOpacity(self._fade)
        pm = self._bubble_pm
        if pm is not None and not pm.isNull():
            painter.drawPixmap(0, 0, pm)     # 已经是物理分辨率，1:1 贴图
        if self._text:
            painter.setPen(self._color)
            painter.setFont(self._font)
            painter.drawText(
                self.ellipse_rect(),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
                    | Qt.TextFlag.TextWordWrap),
                self._text,
            )
        painter.end()


# ============================================================
#  AI 输入框：无边框半透明圆角卡片式顶层 QLineEdit
# ============================================================
class ChatInput(QLineEdit):
    """角色下方的聊天输入框（无边框、半透明、圆角白卡片 + 海军蓝描边）。

    · 顶层窗口，能真正拿到键盘焦点：show() 之后 activateWindow() + setFocus()。
    · 回车 = 发送（submitted 信号），Esc = 取消（cancelled 信号）。
    """

    submitted = Signal(str)
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setFont(QFont(BUBBLE_TEXT_FAMILY, 11))
        self.setPlaceholderText(AI_CHAT_PLACEHOLDER)
        self.setMaxLength(AI_MAX_INPUT_CHARS)
        self.setMinimumHeight(38)
        self.setStyleSheet(f"""
        QLineEdit {{
            background-color: rgba(255, 255, 255, 0.96);
            border: 2px solid {BUBBLE_TEXT_COLOR};
            border-radius: 14px;
            padding: 7px 14px;
            color: {BUBBLE_TEXT_COLOR};
            selection-background-color: #b9cdf5;
            selection-color: {BUBBLE_TEXT_COLOR};
        }}
        QLineEdit:focus {{
            border: 2px solid #3a55a8;
            background-color: rgba(255, 255, 255, 1.0);
        }}
        """)
        self.hide()

    def keyPressEvent(self, event):     # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.submitted.emit(self.text())
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self.cancelled.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def focus_now(self):
        """抢焦点：无边框透明窗口必须先 activateWindow 再 setFocus 才吃得到键盘。"""
        try:
            self.show()
            self.raise_()
            self.activateWindow()
            self.setFocus(Qt.FocusReason.OtherFocusReason)
        except Exception:
            pass


# ============================================================
#  番茄钟：主线程里的普通 QTimer，按真实时间差倒计时
# ============================================================
class Pomodoro:
    """QTimer 驱动，但剩余时间用 time.monotonic() 的真实增量扣减，
    定时器抖动 / 晚点都不会让倒计时跑偏。Qt 事件循环天然转着，不用再泵。"""

    def __init__(self, on_tick, on_finish, parent=None):
        self.on_tick = on_tick
        self.on_finish = on_finish
        self.running = False
        self.remaining = 0.0
        self._stamp = 0.0
        self.timer = QTimer(parent)
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


def format_clock(seconds):
    seconds = max(0, int(math.ceil(seconds)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


# 需要触发「重新按物理分辨率渲染」的 Qt 事件
_DPR_EVENTS = {QEvent.Type.ScreenChangeInternal}
for _name in ("DevicePixelRatioChange", "ScreenChange"):
    _val = getattr(QEvent.Type, _name, None)
    if _val is not None:
        _DPR_EVENTS.add(_val)


# ============================================================
#  主窗口：无边框、逐像素透明的桌面宠物
# ============================================================
class DesktopPet(QLabel):
    """角色本体。

    · basePos   —— 拖动 / 换大小只改这个（角色“站”的位置）
    · jumpOffset —— 唯一的动画：左键点击时的弹跳（空闲时恒为 0，窗口纹丝不动）

    位置永远 = basePos + (0, bounceOffset + jumpOffset)；没有呼吸动画，
    所以不做任何操作时窗口是绝对静止的（A1 要求）。
    """

    def __init__(self, image_path: str = IMAGE_PATH):
        super().__init__(None)

        # ---------- 窗口：真·逐像素透明 ----------
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setWindowTitle("DesktopPet")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)

        # ---------- 素材 ----------
        self.source = load_image(image_path)
        self.base_w, self.base_h = self.source.size
        box = content_box(self.source)
        self.head_cx = ((box[0] + box[2]) / 2) / self.base_w     # 头顶中心（比例）
        self.head_top_ratio = box[1] / self.base_h

        # ---------- 状态 ----------
        self.scale = 1.0
        self.opacity = 1.0
        self.topmost = True
        self.paused = False                 # 保留字段（菜单项已移除），不再影响空闲位置
        self.moved = False
        self.last_line = None
        self.press = None
        self._jump = 0.0
        self._teardown = False
        self.menu = None
        self.palette = THEME_DARK if system_prefers_dark() else THEME_LIGHT
        self._screen_connected = False

        # 番茄钟状态机
        self.pomo_state = POMO_IDLE
        self.pomo_visible = False           # True ⇔ 番茄钟未处于 IDLE（气泡归倒计时）
        self._pomo_first = True

        # AI 聊天状态
        self.ai_typing_ms = AI_TYPING_MS
        self.chat_open = False
        self._chat_thread = None
        self._history = []                  # 滚动窗口：最多 AI_HISTORY_TURNS 轮
        self._type_full = ""
        self._type_pos = 0

        # ---------- 点击弹跳动画（唯一的动画） ----------
        self.jump_anim = QPropertyAnimation(self, b"jumpOffset", self)
        self.jump_anim.setDuration(JUMP_MS)
        self.jump_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        for pos, value in JUMP_KEYS:
            self.jump_anim.setKeyValueAt(pos, float(value))

        # ---------- 配置（pet_config.json） ----------
        cfg = self._load_config()
        self.scale = min(max(float(cfg.get("scale") or self._default_scale()),
                             MIN_SCALE), MAX_SCALE)
        self.opacity = min(max(float(cfg.get("opacity") or 1.0), MIN_OPACITY), 1.0)
        self.sound = Sound(int(cfg.get("volume", SOUND_VOLUME_DEFAULT)))
        self.volume = self.sound.volume

        # ---- 亲密值：启动结算（幂等） ----
        self._affection_penalty = settle_affection(cfg)
        self.affection = clamp_affection(cfg.get("affection", AFFECTION_DEFAULT))
        self.affection_date = cfg.get("affection_date")
        self.clicked_today = bool(cfg.get("clicked_today"))
        self.chatted_today = bool(cfg.get("chatted_today"))
        self._chat_last_error = None

        # ---------- AI config.json（只放 Key，和宠物状态分开） ----------
        ensure_ai_config(CONFIG_PATH)
        self.ai_config = load_ai_config(CONFIG_PATH)

        # ---------- 番茄钟 ----------
        self.pomodoro = Pomodoro(self._on_pomodoro_tick, self._on_pomodoro_finish, self)

        # ---------- 气泡 ----------
        self.bubble = BubbleLabel(None)
        self.bubble_fade = QPropertyAnimation(self.bubble, b"fadeOpacity", self)
        self._fade_hides_bubble = False
        self.bubble_fade.finished.connect(self._after_fade)

        # ---------- 定时器 ----------
        self.hide_bubble_job = QTimer(self)
        self.hide_bubble_job.setSingleShot(True)
        self.hide_bubble_job.timeout.connect(self._on_bubble_timeout)

        self.anim_job = QTimer(self)
        self.anim_job.setInterval(120)
        self.anim_job.timeout.connect(self.tick)

        self.alarm_job = QTimer(self)       # 响铃重复（不自停！）
        self.alarm_job.setSingleShot(True)
        self.alarm_job.timeout.connect(self._alarm_tick)

        self.type_job = QTimer(self)        # 打字机：QTimer 驱动，绝不用 time.sleep
        self.type_job.setSingleShot(True)
        self.type_job.timeout.connect(self._type_tick)

        self.chat_idle_job = QTimer(self)   # 输入框长时间没人理 → 自动收起
        self.chat_idle_job.setSingleShot(True)
        self.chat_idle_job.timeout.connect(self.cancel_chat_input)

        # ---------- AI 输入框 ----------
        self.chat_input = ChatInput(None)
        self.chat_input.submitted.connect(self.send_chat_message)
        self.chat_input.cancelled.connect(self.cancel_chat_input)
        # 打字也算「操作」，每次都重置 15 秒空闲计时
        self.chat_input.textChanged.connect(self._on_chat_typed)

        # ---------- 尺寸 / 位置 / 显示 ----------
        self._apply_scale()
        self._place_window(cfg.get("x"), cfg.get("y"))
        self._apply_opacity()
        self._save_config()                 # 把启动结算结果立刻落盘
        self.show()
        self.anim_job.start()

        # ≥70 亲密度：启动约 1.2 秒后主动关心一句
        QTimer.singleShot(AFFECTION_GREETING_DELAY_MS, self._maybe_greet)

    # ============================================================
    #  自定义 Qt Property —— 动画只写这两个浮点，再由它们统一 move()
    # ============================================================
    def _get_breathe(self):
        """保留这个 Property 只为兼容老调用方；恒为 0，空闲时窗口一动不动。"""
        return 0.0

    def _set_breathe(self, _value):
        self._apply_position()

    def _get_jump(self):
        return self._jump

    def _set_jump(self, value):
        self._jump = float(value)
        self._apply_position()

    breatheOffset = Property(float, _get_breathe, _set_breathe)
    jumpOffset = Property(float, _get_jump, _set_jump)

    def _apply_position(self):
        """唯一的落点计算：basePos + (0, jumpOffset)。"""
        if not hasattr(self, "base_pos"):
            return
        offset = int(round(self._jump))
        self.move(self.base_pos.x(), self.base_pos.y() + offset)

    # ---------- 配置（读-改-写，保留用户自定义键） ----------
    def _load_config(self):
        try:
            with open(PET_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_config(self):
        data = self._load_config()          # 先读回来，image 之类的用户键不能被抹掉
        data.update({
            "scale": round(self.scale, 4),
            "opacity": round(self.opacity, 3),
            "volume": int(self.sound.volume),
            "x": self.base_pos.x(),
            "y": self.base_pos.y(),
            "affection": int(self.affection),
            "affection_date": self.affection_date,
            "clicked_today": bool(self.clicked_today),
            "chatted_today": bool(self.chatted_today),
        })
        try:
            with open(PET_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------- 尺寸 / 位置 ----------
    def _default_scale(self):
        screen = self._screen_rect()
        target = min(max(screen.height() * 0.30, 160), 340)
        return min(max(target / self.base_h, MIN_SCALE), MAX_SCALE)

    @staticmethod
    def _screen_rect():
        app = QApplication.instance()
        screen = app.primaryScreen() if app else None
        return screen.availableGeometry() if screen else QRect(0, 0, 1280, 720)

    def _scaled_size(self):
        w = max(24, int(round(self.base_w * self.scale)))
        h = max(24, int(round(self.base_h * self.scale)))
        return w, h

    def _dpr(self) -> float:
        try:
            d = float(self.devicePixelRatioF())
        except Exception:
            d = 1.0
        return d if d > 0 else 1.0

    def _render_character(self):
        """★ 角色图按物理分辨率渲染：PIL LANCZOS 放大到 w*dpr，再 setDevicePixelRatio。"""
        w, h = self._scaled_size()
        self._pixmap = render_physical(self.source, w, h, self._dpr())

    def _apply_scale(self):
        w, h = self._scaled_size()
        self._render_character()
        self._rebuild_faded()
        self.resize(w, h)
        self.update()

    def _rebuild_faded(self):
        """按当前不透明度做一张预乘好的 pixmap（尺寸/DPR 和角色图一致）。"""
        pm = getattr(self, "_pixmap", None)
        if pm is None or pm.isNull():
            self._pixmap_faded = None
            return
        if self.opacity >= 0.999:
            self._pixmap_faded = None
            return
        dpr = pm.devicePixelRatio() or 1.0
        faded = QPixmap(pm.width(), pm.height())
        faded.fill(Qt.GlobalColor.transparent)
        faded.setDevicePixelRatio(dpr)
        p = QPainter(faded)
        p.setRenderHints(QPainter.RenderHint.SmoothPixmapTransform
                         | QPainter.RenderHint.Antialiasing)
        p.setOpacity(self.opacity)
        p.drawPixmap(0, 0, pm)
        p.end()
        self._pixmap_faded = faded

    def set_scale(self, scale, keep_center=True):
        scale = min(max(scale, MIN_SCALE), MAX_SCALE)
        if abs(scale - self.scale) < 1e-4:
            return
        old_w, old_h = self.width(), self.height()
        self.scale = scale
        self._apply_scale()
        self._apply_position()
        if keep_center:
            # 底部中心不动：尺寸变了横向居中、底边对齐，像站原地长高
            w, h = self.width(), self.height()
            self.set_base_pos(self.base_pos.x() + (old_w - w) // 2,
                              self.base_pos.y() + (old_h - h))
        self._reposition_pomodoro()
        self._reposition_chat_input()

    def set_base_pos(self, x, y, clamp=True):
        """拖动唯一入口：只改 basePos，动画偏移由 setter 叠加。"""
        screen = self._screen_rect()
        w, h = self.width(), self.height()
        if clamp:
            x = min(max(int(x), -w // 3), max(4, screen.width() - w // 2))
            y = min(max(int(y), -h // 4), max(4, screen.height() - h // 3))
        self.base_pos = QPoint(int(x), int(y))
        self._apply_position()

    def _place_window(self, x, y):
        screen = self._screen_rect()
        w, h = self.width(), self.height()
        if x is None or y is None:
            x = screen.x() + screen.width() - w - 60
            y = screen.y() + screen.height() - h - 90
        self.set_base_pos(x, y)

    def _apply_opacity(self):
        self._rebuild_faded()
        self.setWindowOpacity(self.opacity)
        self.update()

    def set_opacity(self, value):
        value = min(max(value, MIN_OPACITY), 1.0)
        if abs(value - self.opacity) < 1e-3:
            return
        self.opacity = value
        self._apply_opacity()

    def toggle_topmost(self):
        self.topmost = not self.topmost
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.topmost)
        self.show()               # 改窗口 flag 之后必须重新 show 才生效

    # ---------- DPR / 屏幕变化 → 重新按物理分辨率渲染 ----------
    def _on_dpr_changed(self):
        if self._teardown:
            return
        self._render_character()
        self._rebuild_faded()
        self.update()
        bubble = getattr(self, "bubble", None)
        if bubble is not None:
            bubble.rerender()

    def event(self, e):             # noqa: N802
        try:
            changed = e.type() in _DPR_EVENTS
        except Exception:
            changed = False
        if changed:
            QTimer.singleShot(0, self._on_dpr_changed)
        return super().event(e)

    def showEvent(self, event):     # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self._on_dpr_changed)
        handle = self.windowHandle()
        if handle is not None and not self._screen_connected:
            try:
                handle.screenChanged.connect(lambda *_: self._on_dpr_changed())
                self._screen_connected = True
            except Exception:
                pass

    # ---------- 绘制 ----------
    def paintEvent(self, event):        # noqa: N802
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        pm = getattr(self, "_pixmap_faded", None) or getattr(self, "_pixmap", None)
        if pm is not None and not pm.isNull():
            painter.drawPixmap(0, 0, pm)    # 物理分辨率贴图，1:1 不重采样
        painter.end()

    # ---------- 原动图逐帧播放的位置（静态 PNG 下是空操作，保留接线） ----------
    def tick(self):
        if self.paused or self.anim_job is None:
            return
        # 静态 PNG 只有一帧，没有可推进的画面；空闲时也没有任何漂浮/呼吸动画。

    # ---------- 暂停 / 继续（菜单项已移除，仅保留 API） ----------
    def toggle_pause(self):
        self.resume() if self.paused else self.pause()

    def pause(self):
        """现在没有呼吸动画，pause 只是停掉可能正在跑的弹跳并把状态钉住。"""
        if self.paused:
            return
        self.paused = True
        self.jump_anim.stop()
        self._jump = 0.0
        self._apply_position()
        self.update()

    def resume(self):
        if not self.paused:
            return
        self.paused = False

    # ---------- 点击弹跳（QPropertyAnimation on jumpOffset） ----------
    def hop(self):
        """单击弹跳：唯一的动画，左键点击的反馈。"""
        self.jump_anim.stop()
        self._jump = 0.0
        self._apply_position()
        self.jump_anim.start()

    # ============================================================
    #  鼠标
    # ============================================================
    def mousePressEvent(self, event):        # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.press = (event.globalPosition().toPoint(), self.base_pos, time.monotonic())
            self.moved = False
            self.sound.play("press")
            return
        if event.button() == Qt.MouseButton.RightButton:
            self.on_right_click(event)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):         # noqa: N802
        if not self.press or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        start, base, _ = self.press
        now = event.globalPosition().toPoint()
        dx, dy = now.x() - start.x(), now.y() - start.y()
        if not self.moved and (abs(dx) > DRAG_THRESHOLD or abs(dy) > DRAG_THRESHOLD):
            self.moved = True
            if not self.pomo_visible:
                self.hide_bubble()
        if self.moved:
            self.set_base_pos(base.x() + dx, base.y() + dy)
            self._reposition_pomodoro()
            self._reposition_chat_input()

    def mouseReleaseEvent(self, event):      # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or not self.press:
            super().mouseReleaseEvent(event)
            return
        _, _, t0 = self.press
        quick = (time.monotonic() - t0) <= CLICK_MAX_SECONDS
        self.press = None
        self.sound.play("release")
        if not self.moved and quick:
            self.handle_click()

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        self.mousePressEvent(event)

    def wheelEvent(self, event):             # noqa: N802
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.set_opacity(self.opacity + (0.05 if delta > 0 else -0.05))
        else:
            factor = 1.08 if delta > 0 else 1 / 1.08
            self.set_scale(self.scale * factor)
        event.accept()

    def keyPressEvent(self, event):          # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.quit()
            return
        super().keyPressEvent(event)

    # ============================================================
    #  ★ 点击优先级（详见文件头注释，两者必须保持一致）
    # ============================================================
    def handle_click(self):
        """左键单击的唯一入口，严格按 1→2→3→4 的顺序判断。"""
        self._settle_day_and_credit_click()          # 附带：今日首次点击 +1
        self.hop()                                   # 任何情况下都弹跳

        # 1. 正在响铃 → 只关铃 + 进下一阶段，绝不打开 AI / 改写气泡
        if self.pomo_state in POMO_RINGING_STATES:
            self.dismiss_alarm()
            return

        # 2. 输入框已开 → 只重新聚焦，不再开第二个
        if self.chat_open:
            self.chat_input.focus_now()
            return

        # 3. 番茄钟某个阶段正在倒计时 → 只弹跳，气泡继续显示倒计时
        if self.pomo_state in POMO_RUNNING_STATES:
            return

        # 4. 否则走 AI 聊天流程
        self.open_chat_input()

    # 旧名兼容：老代码 / 老测试调用 on_pet_click 的仍然能用
    def on_pet_click(self):
        self.handle_click()

    def on_bubble_click(self, _event=None):
        """气泡是鼠标穿透的，这个入口留给以后需要在气泡上响应点击时用。"""
        self.sound.play("release")
        self.handle_click()

    def on_right_click(self, event):
        # 右键时先收起输入框，否则菜单弹出来输入框还杵在那儿
        self.close_chat_input()
        self.hide_bubble()
        self.show_menu(event.globalPosition().toPoint())

    # ============================================================
    #  亲密值
    # ============================================================
    def _roll_day(self):
        """跨天（或首次）时先结算，返回本次扣分。"""
        cfg = {
            "affection": self.affection,
            "affection_date": self.affection_date,
            "clicked_today": self.clicked_today,
            "chatted_today": self.chatted_today,
        }
        penalty = settle_affection(cfg)
        self.affection = clamp_affection(cfg.get("affection"))
        self.affection_date = cfg.get("affection_date")
        self.clicked_today = bool(cfg.get("clicked_today"))
        self.chatted_today = bool(cfg.get("chatted_today"))
        if penalty:
            self._affection_penalty = penalty
        return penalty

    def _settle_day_and_credit_click(self):
        self._roll_day()
        if not self.clicked_today:
            self.clicked_today = True
            self.affection = clamp_affection(self.affection + AFFECTION_CLICK_GAIN)
            self._save_config()
        return self.affection

    def credit_chat(self):
        """今日第一条消息 +2（每天只加一次）。"""
        self._roll_day()
        if not self.chatted_today:
            self.chatted_today = True
            self.affection = clamp_affection(self.affection + AFFECTION_CHAT_GAIN)
            self._save_config()
        return self.affection

    def affection_info(self) -> str:
        return f"亲密值 ❤ {self.affection}/{AFFECTION_MAX}"

    def today_status_info(self) -> str:
        clicked = "已点击" if self.clicked_today else "未点击"
        chatted = "已对话" if self.chatted_today else "未对话"
        return f"今日：{clicked} · {chatted}"

    def _maybe_greet(self):
        """亲密度够高时，启动后主动关心一句。"""
        if self._teardown or self.affection < AFFECTION_GREETING_MIN:
            return
        if self.pomo_state != POMO_IDLE or self.chat_open:
            return
        if self.jump_anim.state() != QAbstractAnimation.State.Stopped:
            return
        self.say(random.choice(AFFECTION_GREETINGS))

    # ============================================================
    #  台词气泡
    # ============================================================
    def say_random(self):
        """遗留接口：随机说一句台词库的话（已不再绑定到点击）。"""
        if self.pomo_visible:      # 番茄钟期间气泡属于倒计时，不能被台词顶掉
            return
        pool = [ln for ln in LINES if ln != self.last_line] or LINES
        self.last_line = random.choice(pool)
        self.say(self.last_line)

    def say(self, text):
        x, y = self._bubble_target()
        self._show_bubble(text, x, y, persistent=False)

    # ---------- 气泡窗口的显示 / 隐藏 ----------
    def _bubble_target(self):
        """气泡中心对准头顶中心，尾巴留一点空隙；贴边时自动收进屏幕。"""
        screen = self._screen_rect()
        width = int(max(140, min(360, self.width() * 0.95)))
        self.bubble.set_bubble_width(width)
        bw, bh = self.bubble.width(), self.bubble.height()
        head_cx = self.base_pos.x() + self.width() * self.head_cx
        head_top = self.base_pos.y() + self.height() * self.head_top_ratio
        x = head_cx - bw / 2
        y = head_top - BUBBLE_TAIL_OFFSET - bh
        if y < screen.y() + 4:                       # 头顶放不下 → 挪到角色下方
            y = self.base_pos.y() + self.height() + 6
            if y + bh > screen.y() + screen.height() - 4:
                y = max(screen.y() + 4, screen.y() + screen.height() - bh - 4)
        x = min(max(x, screen.x() + 4),
                max(screen.x() + 4, screen.x() + screen.width() - bw - 4))
        y = min(max(y, screen.y() + 4),
                max(screen.y() + 4, screen.y() + screen.height() - bh - 4))
        return int(x), int(y)

    def show_persistent_bubble(self, text):
        """常驻气泡：已经在显示就原地换字，不重播淡入（打字机/倒计时用）。"""
        x, y = self._bubble_target()
        if self._pomo_first or not self.bubble.isVisible():
            self._pomo_first = False
            self._show_bubble(text, x, y, persistent=True)
        else:
            self.update_bubble_in_place(text, x, y)

    def _show_bubble(self, text, x, y, persistent=False):
        self.hide_bubble_job.stop()
        self.bubble_fade.stop()          # 先停掉可能还在跑的淡出，否则它会把新气泡又拉黑
        self._fade_hides_bubble = False
        fade_in = (not self.bubble.isVisible()) or self.bubble.fadeOpacity < 0.99
        shown = self.bubble.fadeOpacity if self.bubble.isVisible() else 0.05
        self.bubble.set_text(text)
        self.bubble.move(x, y)
        self.bubble.show()
        self.bubble.raise_()
        if fade_in:
            self.bubble_fade.setDuration(BUBBLE_ANIM_MS)
            self.bubble_fade.setStartValue(min(0.95, max(0.05, float(shown))))
            self.bubble_fade.setEndValue(1.0)
            self.bubble_fade.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.bubble_fade.start()
        if not persistent:
            self.hide_bubble_job.start(BUBBLE_MS)

    def _after_fade(self):
        """淡入/淡出动画结束后调用：把值钉死在终点，避免最后一帧被丢掉。"""
        if self._fade_hides_bubble:
            self.bubble._set_fade(0.0)
            self.bubble.hide()
        else:
            self.bubble._set_fade(1.0)

    def update_bubble_in_place(self, text, x, y):
        """原地换内容：不重播弹入动画、不移动窗口锚点（倒计时/打字机用）。"""
        if not self.bubble.isVisible() or self.bubble.fadeOpacity < 0.99:
            self._show_bubble(text, x, y, persistent=True)
            return
        self.hide_bubble_job.stop()
        self.bubble_fade.stop()
        self.bubble.set_text(text)
        self.bubble.move(x, y)
        self.bubble.show()

    def hide_bubble(self):
        self.hide_bubble_job.stop()
        if not self.bubble.isVisible():
            return
        self.bubble_fade.stop()
        self._fade_hides_bubble = True
        self.bubble_fade.setDuration(BUBBLE_FADE_MS)
        self.bubble_fade.setStartValue(float(self.bubble.fadeOpacity))
        self.bubble_fade.setEndValue(0.0)
        self.bubble_fade.setEasingCurve(QEasingCurve.Type.InCubic)
        self.bubble_fade.start()

    def _on_bubble_timeout(self):
        self.hide_bubble()

    # ============================================================
    #  ★ AI 聊天（PART C）
    # ============================================================
    def open_chat_input(self):
        """第 4 优先级：气泡给傲娇提示 + 角色下方弹出输入框。"""
        if self.chat_open:
            self.chat_input.focus_now()
            return
        if self.pomo_state != POMO_IDLE:
            return
        self.chat_open = True
        self._cancel_typing()
        self.chat_input.clear()
        self._reposition_chat_input()
        self.chat_input.focus_now()
        self.show_persistent_bubble(AI_PROMPT_LINE)
        self.chat_idle_job.start(AI_CHAT_IDLE_MS)

    def _on_chat_typed(self, _text=None):
        """输入框里有任何输入都算「操作」，重置 15 秒空闲计时。"""
        if self.chat_open:
            self.chat_idle_job.start(AI_CHAT_IDLE_MS)

    def close_chat_input(self, hide_bubble=False):
        self.chat_idle_job.stop()
        if self.chat_open:
            self.chat_open = False
            try:
                self.chat_input.hide()
            except Exception:
                pass
        if hide_bubble and not self.pomo_visible:
            self.hide_bubble()

    def cancel_chat_input(self):
        """Esc：收起输入框并清空气泡。"""
        self.close_chat_input(hide_bubble=True)

    def _chat_input_target(self):
        screen = self._screen_rect()
        w = int(max(220, min(430, self.width() * 1.05)))
        h = max(38, self.chat_input.sizeHint().height())
        cx = self.base_pos.x() + self.width() / 2
        y = self.base_pos.y() + self.height() + 10
        x = cx - w / 2
        x = min(max(x, screen.x() + 4),
                max(screen.x() + 4, screen.x() + screen.width() - w - 4))
        y = min(max(y, screen.y() + 4),
                max(screen.y() + 4, screen.y() + screen.height() - h - 4))
        return int(x), int(y), w, h

    def _reposition_chat_input(self):
        if not self.chat_open:
            return
        x, y, w, h = self._chat_input_target()
        self.chat_input.setGeometry(x, y, w, h)

    def send_chat_message(self, text=None):
        """回车发送：收输入框 → 后台请求 → 打字机显示回复。"""
        if not self.chat_open:
            return
        if text is None:
            text = self.chat_input.text()
        text = (text or "").strip()[:AI_MAX_INPUT_CHARS]
        self.close_chat_input()
        if not text:
            self.show_persistent_bubble(AI_ERROR_EMPTY)
            self.hide_bubble_job.start(BUBBLE_MS)
            return

        self.credit_chat()                       # 今日首条消息 +2
        self._history.append({"role": "user", "content": text})
        self._history = self._history[-AI_HISTORY_TURNS * 2:]
        messages = [{"role": "system", "content": AI_SYSTEM_PROMPT}] + list(self._history)

        self.chat_idle_job.stop()
        self._cancel_typing()
        self.show_persistent_bubble(AI_WAITING_TEXT)
        self._start_chat_thread(messages)

    def _start_chat_thread(self, messages):
        cfg = self.ai_config or load_ai_config(CONFIG_PATH)
        api_key = str(cfg.get("deepseek_api_key") or "").strip()
        thread = ChatThread(
            messages, api_key,
            str(cfg.get("deepseek_base_url") or DEEPSEEK_BASE_URL),
            str(cfg.get("deepseek_model") or DEEPSEEK_MODEL),
            self,
        )
        thread.replied.connect(self._on_ai_reply)
        thread.failed.connect(self._on_ai_failed)
        thread.finished.connect(self._on_chat_thread_done)
        self._chat_thread = thread
        thread.start()                           # ★ 非阻塞：请求跑在子线程里

    def _on_chat_thread_done(self):
        thread = self._chat_thread
        self._chat_thread = None
        if thread is not None:
            try:
                thread.deleteLater()
            except Exception:
                pass

    def _on_ai_reply(self, text):
        if self._teardown:
            return
        if self._history and self._history[-1].get("role") == "user":
            self._history.append({"role": "assistant", "content": str(text)[:200]})
            self._history = self._history[-AI_HISTORY_TURNS * 2:]
        if self.pomo_visible:           # 番茄钟进行中：气泡留给倒计时
            return
        self.start_typing(str(text))

    def _on_ai_failed(self, code, detail=""):
        if self._teardown:
            return
        # 失败的这一轮不留在上下文里，免得污染下一轮的上下文
        if self._history and self._history[-1].get("role") == "user":
            self._history.pop()
        if code == "no_key":
            message = AI_ERROR_NO_KEY
        else:
            message = AI_ERROR_LINE
        self._chat_last_error = (code, detail)
        self._show_bubble(message, *self._bubble_target(), persistent=False)

    # ---------- 打字机（QTimer 驱动，一个一个字地长出来） ----------
    def start_typing(self, text):
        self._cancel_typing()
        self._type_full = str(text or "")
        self._type_pos = 0
        if not self._type_full:
            return
        self.show_persistent_bubble("")
        self.type_job.start(max(1, int(self.ai_typing_ms)))

    def _type_tick(self):
        if self._teardown:
            return
        if self.pomo_visible:          # 番茄钟气泡归倒计时，打字机让位
            self._cancel_typing()
            return
        if self._type_pos >= len(self._type_full):
            self.type_job.stop()
            if not self.pomo_visible:
                # 回复打完后同样按 15 秒空闲规则收起气泡
                self.hide_bubble_job.start(AI_CHAT_IDLE_MS)
            return
        self._type_pos += 1
        self.update_bubble_in_place(self._type_full[:self._type_pos],
                                    *self._bubble_target())
        self.type_job.start(max(1, int(self.ai_typing_ms)))

    def _cancel_typing(self):
        try:
            self.type_job.stop()
        except Exception:
            pass
        self._type_full = ""
        self._type_pos = 0

    def typing_finished(self) -> bool:
        return bool(self._type_full) and self._type_pos >= len(self._type_full)

    # ============================================================
    #  ★ 番茄钟状态机（PART D）
    # ============================================================
    def start_pomodoro(self):
        if self.pomodoro is None or self.pomo_state != POMO_IDLE:
            return
        self._start_phase(POMO_FOCUS)

    def _start_phase(self, state):
        """进入 FOCUS / BREAK：立刻开盘，气泡显示新倒计时。"""
        self._cancel_alarm()
        self._cancel_typing()          # 气泡归番茄钟，别让打字机抢字
        self.pomo_state = state
        self.pomo_visible = True
        self._pomo_first = True
        minutes = POMODORO_MINUTES if state == POMO_FOCUS else BREAK_MINUTES
        self.pomodoro.start(minutes)

    def stop_pomodoro(self):
        """菜单「停止番茄钟」：停铃、取消定时器、回到 IDLE 并收起气泡。"""
        self._cancel_alarm()
        if self.pomodoro is not None:
            self.pomodoro.stop()
        self.pomo_state = POMO_IDLE
        self.pomo_visible = False
        self._pomo_first = True
        self.hide_bubble()

    def _pomodoro_text(self, remaining):
        if self.pomo_state == POMO_BREAK:
            return POMO_TEXT_BREAK.format(clock=format_clock(remaining))
        return POMO_TEXT_FOCUS.format(clock=format_clock(remaining))

    def _on_pomodoro_tick(self, remaining):
        if not self.pomo_visible:
            return
        self._show_pomodoro_bubble(self._pomodoro_text(remaining))

    def _on_pomodoro_finish(self):
        """倒计时归零 → 进入响铃态（响铃不会自己停）。"""
        if self.pomo_state == POMO_FOCUS:
            self._enter_ringing(POMO_FOCUS_RINGING, POMO_TEXT_FOCUS_DONE)
        elif self.pomo_state == POMO_BREAK:
            self._enter_ringing(POMO_BREAK_RINGING, POMO_TEXT_BREAK_DONE)

    def _enter_ringing(self, state, text):
        self.pomo_state = state
        self.pomo_visible = True
        self._cancel_typing()          # 响铃提示优先于打字机
        self.sound.play("chime")
        self._pomo_first = True
        self._show_pomodoro_bubble(text)
        self.alarm_job.start(ALARM_REPEAT_MS)      # 反复响，直到被点击/菜单停止

    def _alarm_tick(self):
        if self.pomo_state not in POMO_RINGING_STATES:
            return
        self.sound.play("chime")
        self.alarm_job.start(ALARM_REPEAT_MS)

    def dismiss_alarm(self):
        """左键点击响铃中的角色：停铃 + 立刻开始下一阶段。"""
        if self.pomo_state == POMO_FOCUS_RINGING:
            self._start_phase(POMO_BREAK)
        elif self.pomo_state == POMO_BREAK_RINGING:
            self._start_phase(POMO_FOCUS)

    def _cancel_alarm(self):
        if self.alarm_job is not None:
            self.alarm_job.stop()
        self.sound.stop()

    def _show_pomodoro_bubble(self, text):
        """番茄钟气泡：常驻显示（点它也不会改文字）。"""
        self.show_persistent_bubble(text)

    def _reposition_pomodoro(self):
        """角色被拖动时，让番茄钟气泡重新贴回头顶。"""
        if not self.pomo_visible or not self.bubble.isVisible():
            return
        if self.pomo_state == POMO_FOCUS_RINGING:
            text = POMO_TEXT_FOCUS_DONE
        elif self.pomo_state == POMO_BREAK_RINGING:
            text = POMO_TEXT_BREAK_DONE
        elif self.pomodoro is not None and self.pomodoro.running:
            text = self._pomodoro_text(self.pomodoro.remaining)
        else:
            text = POMO_TEXT_FOCUS_DONE
        self.update_bubble_in_place(text, *self._bubble_target())

    # ============================================================
    #  右键菜单
    # ============================================================
    def _menu_style(self) -> str:
        p = self.palette
        return f"""
        QMenu {{
            background-color: {p['surface']};
            border: 1px solid {p['border']};
            border-radius: {MENU_RADIUS}px;
            padding: {MENU_PAD_Y}px 6px;
            color: {p['text']};
        }}
        QMenu::item {{
            background: transparent;
            color: {p['text']};
            padding: 7px 22px 7px 14px;
            border-radius: 8px;
            min-width: {MENU_MIN_W}px;
        }}
        QMenu::item:selected {{
            background-color: {p['field']};
            color: {p['accent']};
        }}
        QMenu::item:disabled {{
            color: {p['muted']};
            background: transparent;
        }}
        QMenu::separator {{
            height: 1px;
            background: {p['border']};
            margin: 5px 10px;
        }}
        QMenu::right-arrow {{
            width: 10px;
            height: 10px;
        }}
        """

    def _make_menu(self, owner: QMenu = None) -> QMenu:
        """每次弹出都重新构建，勾选态 / 可用态一定是最新的。"""
        menu = QMenu(owner)
        menu.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        menu.setStyleSheet(self._menu_style())
        menu.setFont(QFont(BUBBLE_TEXT_FAMILY, MENU_FONT_SIZE))
        return menu

    @staticmethod
    def _add_item(menu: QMenu, label, command=None, checked=False, enabled=True):
        act = menu.addAction(("✓ " if checked else "") + label)
        act.setCheckable(False)
        act.setEnabled(enabled and command is not None)
        if command is not None and enabled:
            act.triggered.connect(lambda *_: command())
        return act

    def _pomodoro_menu_label(self) -> str:
        if self.pomo_state == POMO_FOCUS:
            return f"专注中 {format_clock(self.pomodoro.remaining)}"
        if self.pomo_state == POMO_BREAK:
            return f"休息中 {format_clock(self.pomodoro.remaining)}"
        if self.pomo_state == POMO_FOCUS_RINGING:
            return "🍅 时间到（点我一下）"
        if self.pomo_state == POMO_BREAK_RINGING:
            return "🍅 休息结束（点我一下）"
        return "番茄钟未启动"

    def _menu_items(self) -> dict:
        """保留的兼容入口：返回当前状态快照，方便测试/外部查询。"""
        return {
            "paused": self.paused,
            "pomo_state": self.pomo_state,
            "pomo_visible": self.pomo_visible,
            "pomodoro_running": bool(self.pomodoro and self.pomodoro.running),
            "scale": self.scale,
            "opacity": self.opacity,
            "volume": self.sound.volume,
            "topmost": self.topmost,
            "affection": self.affection,
            "clicked_today": self.clicked_today,
            "chatted_today": self.chatted_today,
            "chat_open": self.chat_open,
        }

    def show_menu(self, global_pos: QPoint):
        root = self._make_menu()

        # 0. 亲密值信息行（两行，都是禁用态，纯展示）
        self._add_item(root, self.affection_info(), None, enabled=False)
        self._add_item(root, self.today_status_info(), None, enabled=False)
        root.addSeparator()

        # 1. 番茄钟 ▸（两阶段循环）
        tomato = self._make_menu(root)
        if self.pomodoro is None:
            self._add_item(tomato, "番茄钟不可用", None, enabled=False)
        elif self.pomo_state == POMO_IDLE:
            self._add_item(tomato, f"开始专注 {POMODORO_MINUTES} 分钟", self.start_pomodoro)
            self._add_item(tomato, "停止番茄钟", None, enabled=False)
        else:
            self._add_item(tomato, self._pomodoro_menu_label(), None,
                           checked=True, enabled=False)
            self._add_item(tomato, "停止番茄钟", self.stop_pomodoro)
        tomato.addSeparator()
        self._add_item(tomato, f"专注 {POMODORO_MINUTES} 分 / 休息 {BREAK_MINUTES} 分",
                       None, enabled=False)
        root.addMenu(tomato).setText("番茄钟")

        # 2. 窗口大小 ▸
        sizes = self._make_menu(root)
        cur_pct = int(round(self.scale * 100))
        self._add_item(sizes, "放大　(+)", lambda: self.set_scale(self.scale * 1.12))
        self._add_item(sizes, "缩小　(-)", lambda: self.set_scale(self.scale / 1.12))
        sizes.addSeparator()
        for name, value in SCALE_PRESETS:
            pct = int(round(value * 100))
            self._add_item(sizes, f"{name}　{pct}%",
                           (lambda v=value: self.set_scale(v)),
                           checked=abs(cur_pct - pct) < 5)
        sizes.addSeparator()
        self._add_item(sizes, "恢复默认大小", lambda: self.set_scale(self._default_scale()))
        self._add_item(sizes, "滚轮也可以调整大小", None, enabled=False)
        root.addMenu(sizes).setText("窗口大小")

        # 3. 不透明度 ▸
        opacity = self._make_menu(root)
        cur_op = int(round(self.opacity * 100))
        for pct in OPACITY_PRESETS:
            self._add_item(opacity, f"{pct}%",
                           (lambda v=pct: self.set_opacity(v / 100.0)),
                           checked=abs(cur_op - pct) < 5)
        opacity.addSeparator()
        self._add_item(opacity, "Ctrl + 滚轮 也可以调整", None, enabled=False)
        root.addMenu(opacity).setText("不透明度")

        # 4. 音效音量 ▸
        volume = self._make_menu(root)
        for pct in VOLUME_PRESETS:
            self._add_item(volume, f"{pct}%",
                           (lambda v=pct: self.set_volume(v)),
                           checked=self.sound.volume == pct)
        volume.addSeparator()
        self._add_item(volume, "点击角色和气泡都会响", None, enabled=False)
        root.addMenu(volume).setText("音效音量")

        # 5. 窗口置顶
        self._add_item(root, "窗口置顶", self.toggle_topmost, checked=self.topmost)
        root.addSeparator()
        # 6. 退出
        self._add_item(root, "退出", self.quit)

        # 圆角菜单必须自己画背景，否则四角会露出方形底色
        root.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        root.popup(global_pos)
        self.menu = root          # 保存引用，避免被 GC 立刻回收

    # ---------- 音量 ----------
    def set_volume(self, volume):
        self.sound.set_volume(volume)
        self.volume = self.sound.volume
        self.sound.play("release")       # 立即试听

    # ---------- 退出 ----------
    def quit(self):
        if self._teardown:
            return
        self._teardown = True
        self._cancel_typing()
        self._cancel_alarm()
        for timer in (self.anim_job, self.hide_bubble_job, self.alarm_job,
                      self.type_job, self.chat_idle_job,
                      getattr(self.pomodoro, "timer", None)):
            if timer is not None:
                try:
                    timer.stop()
                except Exception:
                    pass
        for anim in (self.jump_anim, self.bubble_fade):
            try:
                anim.stop()
            except Exception:
                pass
        if self.pomodoro is not None:
            self.pomodoro.stop()
        thread = self._chat_thread
        if thread is not None and thread.isRunning():
            try:
                thread.wait(1500)
            except Exception:
                pass
        self.sound.stop()
        self._save_config()
        for extra in (getattr(self, "chat_input", None), getattr(self, "bubble", None)):
            if extra is not None:
                try:
                    extra.hide()
                    extra.close()
                except Exception:
                    pass
        menu = getattr(self, "menu", None)
        if menu is not None:
            try:
                menu.close()
            except Exception:
                pass
        self.hide()
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()


# ---------------- 入口 ----------------
def main():
    enable_dpi_awareness()          # 必须在 QApplication 之前（Win32）
    apply_high_dpi_policy()         # 再设 Qt 的 PassThrough，最后才建 QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("DesktopPet")
    app.setQuitOnLastWindowClosed(False)

    if not os.path.exists(IMAGE_PATH):
        QMessageBox.critical(None, "桌面宠物", f"找不到角色图片：\n{IMAGE_PATH}")
        return 1
    if not os.path.exists(BUBBLE_PATH):
        QMessageBox.critical(None, "桌面宠物", f"找不到气泡图片：\n{BUBBLE_PATH}")
        return 1

    ensure_ai_config(CONFIG_PATH)   # 没有 config.json 就生成一份空 Key 的
    pet = DesktopPet(IMAGE_PATH)
    pet.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
