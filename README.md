<div align="center">

# 🐾 桌面宠物小摆件

**一个 PySide6 的 Windows 桌面宠物：透明无边框、点击弹性、能真的用 DeepSeek 聊天，还带亲密值养成和番茄钟。**

纯本地运行 · 无后端 · 单文件主程序 · 音效零素材依赖

<img src="assets/demo.png" width="660" alt="桌面宠物效果预览">

</div>

---

## ✨ 项目特点

### 1. 真·透明无边框 + 高清渲染

用 `Qt.WA_TranslucentBackground` + `FramelessWindowHint` 做**逐像素透明**，不是抠像色 hack：

- 透明区域**自动鼠标穿透**，不挡桌面操作
- **按物理像素渲染**：素材用 LANCZOS 重采样到 `逻辑尺寸 × devicePixelRatio`，再 `setDevicePixelRatio()`，让 Qt 1:1 直贴 —— 高分屏（125% / 150% 缩放）下不会发虚
- DPI 变化时自动重渲染

### 2. 真的能聊天（DeepSeek）

- 左键点一下角色 → 气泡说一句傲娇开场白 → **角色下方弹出输入框**
- 回车发送；网络请求跑在 **`QThread`** 里，**界面绝不卡死**（实测请求耗时 1.5 秒期间界面心跳照常跳动）
- 回复以**打字机效果逐字蹦出**（`QTimer` 驱动，每字 45ms）
- 没填 API Key 会友好提示，不会崩

**省 token 的做法：**

| 手段 | 说明 |
|---|---|
| 极短系统提示词 | 89 字，强制「1~2 句、40 字以内」—— 最大的省钱点 |
| 滚动窗口上下文 | 只保留最近 **3 轮 / 6 条**消息，最旧的直接丢弃 |
| 不做二次摘要 | 不额外调一次 API 去总结历史 |
| 输入截断 | 用户输入最长 300 字 |
| 输出上限 | `max_tokens: 160`、`stream: false` |

实测单轮请求约 **2 条消息 / 100 tokens 上下**。

### 3. 亲密值养成系统

| 行为 | 变化 |
|---|---|
| 每天第一次点击角色 | **+1** |
| 每天第一次和我说话 | **+2** |
| 一整天完全没互动 | **-1**（跳过的整天也扣，单次启动最多扣 10，防止一次归零） |

- 范围 0–100，默认 50
- **≥ 70 时**启动 1.2 秒后会主动关心你一句（随机 6 条，例如「今天也要好好喝水哦。」）
- 右键菜单里直接可见：`亲密值 73 / 100` 与 `今日：已点击 · 未对话`
- 按天结算，同一天重复启动不会重复加减

### 4. 番茄钟：必须点一下才关得掉

```
IDLE → 专注 25min → 🔔 响铃 → 点击角色 → 休息 10min → 🔔 响铃 → 点击角色 → 专注 …
```

- 到点后提示音**每隔 1.4 秒响一次，永不自动停**，只有**点击角色**才关
- 关掉立刻进入下一阶段，气泡自动切成 `🍅 休息中 10:00`
- 只有菜单「停止番茄钟」或退出程序能终止整个循环
- 倒计时按 `time.monotonic()` 真实时间差推进，定时器抖动不会累积误差

### 5. 点击手感

左键点击 → **`QPropertyAnimation` 弹跳**：520ms `OutQuad`，关键帧 `0 → -34px → 0 → -12px → 0`（主跳 + 小回弹），同时播放按下 / 松开两个音效。

常态下角色**完全静止**，不会自己上下浮动。

### 6. 音效完全本地合成

仓库里没有任何音频素材，三个音效都是**运行时用数学算出来**再写成 WAV：

- `press` / `release`：线性扫频 + 指数衰减包络 + 起手噪声瞬态
- `chime`：A5–C#6–E6 上行琶音
- 合成总耗时约 56ms，按当前音量生成对应版本并缓存
- 播放用标准库 `winsound`，**不需要 pygame 之类的依赖**

菜单里可直接调音量（0 / 25 / 50 / 75 / 100%），切换即时试听。

### 7. 状态持久化 + 干净退出

大小、不透明度、音量、屏幕位置、亲密值都会存进 `pet_config.json`，下次打开回到原地。
退出时依次停掉动画 / 定时器 / 音效 → 存配置 → `QApplication.quit()`，不留后台残留。

---

## 🚀 快速开始

```bash
git clone https://github.com/yum0ooo/anime-desk-pet.git
cd anime-desk-pet
pip install -r requirements.txt
python desktop_pet.py
```

### 🔑 配置 API Key（想用 AI 对话必须做）

复制模板并填入你的 DeepSeek Key：

```bash
cp config.example.json config.json
```

```json
{
  "deepseek_api_key": "sk-你的密钥",
  "deepseek_model": "deepseek-chat",
  "deepseek_base_url": "https://api.deepseek.com"
}
```

> `config.json` 已在 `.gitignore` 中屏蔽，**不会被提交**。不填也能跑，只是点角色聊天时会提示去配置。

### 桌面快捷方式

```powershell
.\install.ps1
```

自动找到 `pythonw.exe`、在桌面创建快捷方式、顺带检查依赖是否齐全。卸载：`.\install.ps1 -Uninstall`。

---

## 🎮 使用说明

| 操作 | 效果 |
|---|---|
| 左键拖动 | 移到任意位置（位移 < 4px 才算点击） |
| 单击角色 | 弹跳 + 音效；空闲时打开 AI 输入框，番茄钟响铃时关铃 |
| 滚轮 | 缩放角色 |
| Ctrl + 滚轮 | 调不透明度 |
| 右键 | 打开卡片菜单 |
| Esc | 收起输入框 / 退出 |

**左键点击的处理优先级**（严格按此顺序）：

1. **番茄钟正在响铃** → 只关铃 + 进入下一阶段（不会打开聊天框、不会改写气泡）
2. **输入框已打开** → 只重新聚焦
3. **番茄钟倒计时中** → 只弹跳，保住倒计时气泡
4. **其他情况** → 进入 AI 对话流程

**15 秒无操作**（不点击、不输入）会自动收起输入框和气泡。

---

## ⚙️ 配置

主程序顶部集中了所有可调项：

```python
IMAGE_PATH  = "assets/pet_character.png"   # 角色图（透明 PNG）
BUBBLE_PATH = "assets/bubble.png"          # 气泡底图

POMODORO_MINUTES = 25      # 专注时长（分钟）
BREAK_MINUTES    = 10      # 休息时长（分钟）
ALARM_REPEAT_MS  = 1400    # 响铃重复间隔

AFFECTION_DEFAULT      = 50    # 亲密值初始值
AFFECTION_GREETING_MIN = 70    # 达到多少会主动关心你

AI_MAX_TOKENS    = 160     # 回复长度上限（省钱关键）
AI_HISTORY_TURNS = 3       # 上下文保留几轮
AI_TYPING_MS     = 45      # 打字机每字间隔
AI_CHAT_IDLE_MS  = 15000   # 无操作多久自动收起
```

---

## 🧩 实现要点

| 问题 | 做法 |
|---|---|
| 透明窗口挡鼠标 | `WA_TranslucentBackground` + 透明区域鼠标穿透 |
| 高分屏发虚 | 按 `devicePixelRatio` 渲染到物理像素，再交给 Qt 1:1 贴图 |
| 网络请求卡界面 | `QThread` + Qt 信号回调，主线程只做 UI |
| 淡入淡出与窗口透明打架 | 用气泡自己的 `fadeOpacity` 属性配合 `painter.setOpacity`，不碰窗口透明度 |
| 定时器抖动累积 | 倒计时按 `time.monotonic()` 真实差值推进 |
| 中文字体缺字形 | 对勾 / 箭头等符号一律用矢量折线绘制，不依赖字体 |
| 中文没有 emoji | 🍅 用 Segoe UI Emoji 以 `embedded_color=True` 混排进气泡 |

主程序约 1900 行，单文件。

---

## ⚠️ 已知限制

- **仅 Windows**：`winsound`、DPI 感知、注册表读取主题都依赖 Win32 API
- 需要 **Python 3.9+** 与 **PySide6**
- 多显示器之间拖动时的 DPR 迁移逻辑已实现，但未实机验证（开发机只有一块屏）
- 不透明度最低锁 20%，防止调太低之后找不到角色、也就调不回来了

---

## 🙏 致谢

UI 的**视觉参数**参考了下面两个开源项目（代码全部自研，仅借用设计数值）：

- [vladelaina/BongoCat](https://github.com/vladelaina/BongoCat) —— 自绘菜单的圆角 / 行高 / 间距 / 深浅色配色表
- [MeteorNOX/DeepSeek-Balance-Whale-Widget](https://github.com/MeteorNOX/DeepSeek-Balance-Whale-Widget) —— 点击弹性的形变比例与 `cubic-bezier(.34,1.56,.64,1)` 曲线

音效未使用上述项目的素材，而是按同样听感方向**本地重新合成**。

---

## 📄 License

MIT —— 见 [LICENSE](LICENSE)。
