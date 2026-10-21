---
name: bili-transcript
description: 拉取 B 站视频的元数据和带时间戳文字稿（字幕优先，无字幕时本地 ASR）。Use when the user provides a Bilibili/BV/av/b23.tv link and asks to fetch, transcribe, extract, or convert the video to text. Does not impose an analysis or summary format.
when_to_use: B站视频, Bilibili, BV号, av号, b23.tv, 字幕, 转写, 文字稿, transcript, subtitle
argument-hint: "[url]"
allowed-tools: Read Bash(command -v bili-transcript) Bash(bili-transcript *) Bash(uv tool run bili-transcript *)
---

# bili-transcript

把 B 站视频拉取/转换为本地文字稿。核心职责是**获取**：元数据、字幕、音频（可选）和带时间戳的文字稿。后续如何分析、总结、做笔记，由调用方或用户决定，本 Skill 不预设分析模板。

## 默认配置（已锁定）

直接运行 `fetch "<链接>" --json`，不要额外加参数：

- 字幕优先；无字幕才下载音频。
- ASR：`large-v3-turbo`，`device=auto`（优先 CUDA），`language=zh`。
- 音频流优先 `30216`（约 66 kbps）；实测 30232 流慢且会超时，已避开。
- ASR 成功后默认删除音频；只有用户明确要求保留时才加 `--keep-audio`。
- 有字幕时仍请求 B 站官方 AI 总结作为辅助；不需要时加 `--no-ai-summary`。
- 按 BV/分P 缓存；`--json` 返回 `timings`。

默认值定义在 `bili_transcript/config.py` 的 `DEFAULT_*` / `AUDIO_STREAM_PRIORITY`，有单元测试锁定。不要为了“优化”随意改模型或设备，除非用户明确要求，或默认配置在机器上不可用。

## 数据目录

所有运行数据都在 `~/.bili-transcript/`：

- `~/.bili-transcript/config/credentials.json`：登录 Cookie（敏感）
- `~/.bili-transcript/config/login_qr.png`：二维码
- `~/.bili-transcript/data/<BV>/p<N>/`：文字稿、元数据、可选音频

可以用 `BILI_TRANSCRIPT_HOME` 覆盖根目录。

## 标准流程

### 0. 确认 CLI 可用

```bash
bili-transcript --version
```

如果命令不存在，说明 CLI 还没安装。告诉用户按仓库 README 的安装命令执行（通常是）：

```bash
uv tool install "bili-transcript[cuda] @ git+<repo-url>"   # NVIDIA GPU
# 或
uv tool install "bili-transcript @ git+<repo-url>"         # CPU / macOS
```

也可以临时用 `uv tool run bili-transcript ...`。安装后运行一次：

```bash
bili-transcript doctor
```

### 1. 检查登录

```bash
bili-transcript status
```

- 输出「已登录」→ 继续。
- 输出「未登录」或「Cookie 已失效」→ 扫码：
  1. `bili-transcript login --qr-only`
  2. 用 Read 工具读取 `~/.bili-transcript/config/login_qr.png`，展示给用户，请用户用手机 B 站 App 扫码并确认。
  3. 用户确认后运行 `bili-transcript login --poll`（最长等待 180 秒）。
  4. 登录成功后继续。

> B 站字幕接口对 AI 字幕强制登录；本工具统一在登录态下抓字幕。未登录时会退化为音频转写，速度和覆盖都会下降。

> 如果用户看不到对话里的二维码图片，把 `~/.bili-transcript/config/login_qr.png` 复制成一张单独的 JPG 并告诉用户路径；也可以让用户直接看终端里的二维码。

### 2. 抓取文字稿

```bash
bili-transcript fetch "<视频链接或 BV 号>" --json
```

常用参数（都是覆盖项，默认不要加）：

- `-p/--page N`：多 P 视频指定第 N P（从 1 开始）。
- `--force`：忽略缓存重新抓取；只在用户明确要求时用。
- `--no-asr`：没有字幕就直接失败，不下载音频；只在需要快速失败时用。
- `--keep-audio`：ASR 后保留音频；只在用户明确要求时用，默认删除。
- `--model` / `--device` / `--language`：默认 `large-v3-turbo` / `auto` / `zh`；只在默认配置不可用或用户明确要求时修改。

退出码：

- `0` 成功。
- `2` 需要登录：执行上面的扫码流程后重试。
- `3` 没有拿到文字稿：向用户说明原因（视频无字幕且音频不可用/转写失败）。
- `4` 输入无法识别：请用户提供 BV 号或完整链接。

`--json` 返回的关键字段：

- `transcript_txt`：带 `[mm:ss]` 时间戳的分段文字稿，**主要产物**。
- `transcript_json`：逐段 `start/end/text`，需要精确引用时读它。
- `transcript_srt`：字幕文件。
- `meta_path`：`meta.json`，含标题、UP 主、时长、发布时间、来源、`timings`。
- `transcript_source`：`subtitle:ai-zh`、`subtitle:zh-CN`、`ai-conclusion` 或 `asr:...`。
- `partial`：文字稿是否只覆盖了视频的一部分。
- `timings`：metadata/subtitle/ai_conclusion/audio_download/asr/write/total。
- `audio_retained`：ASR 音频是否保留（默认 false）。

### 3. 汇报

给用户的回复包含：

1. 视频标题、UP 主、时长。
2. `transcript_txt` / `transcript_json` / `transcript_srt` 的路径。
3. 文字稿来源与质量提示（CC/AI 字幕/ASR、是否完整）。
4. 如果 `partial=true` 或来源是 ASR，明确说明局限。

**不要把完整文字稿直接倒进聊天窗口**，除非用户明确要求；给出路径即可。

### 4. 可选分析

本 Skill **不默认生成 `summary.md`**，也不强制任何分析模板。

- 如果用户只是要文字稿：到第 3 步结束。
- 如果用户要求分析/总结：读取 `transcript_txt`（必要时读 `transcript_json`），然后按用户要求的方式分析。分析结构和篇幅由调用方决定。
- 引用原话时以文字稿为准；ASR 可能有同音字错误，AI 字幕可能有专有名词错误，必要时结合上下文校正并说明。
- 仓库里的 `docs/analysis-prompt.md` 只是一个可选示例，不是默认流程。

## 常见问题

- **多 P 视频**：用户没指定时默认第 1 P，并在汇报中说明；需要其他 P 用 `-p N`。
- **缓存**：同一 BV/分P 再次运行会复用 `~/.bili-transcript/data/<BV>/p<N>/`；用户要求重新抓取时加 `--force`。
- **登录过期**：重新执行 `login --qr-only` + `login --poll`。
- **视频没有字幕**：脚本会自动下载音频并用 GPU 转写；没有 NVIDIA GPU 时回退 CPU，会明显变慢。
- **不要在总结阶段用 yt-dlp 下载完整视频**；本工具只需要字幕或音频。
- **存储**：默认 ASR 后删除音频；需要保留时用 `--keep-audio`。
