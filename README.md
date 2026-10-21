# bili-transcript

[中文](README.md) | [English](README.en.md)

把 B 站视频拉取/转换为本地文字稿：元数据、字幕、可选音频、带时间戳的 `transcript.txt/json/srt`。

它只负责**获取和转换**，不预设分析方式。后续是写总结、做笔记、做检索还是喂给别的 agent，由调用方决定。

- 字幕优先：直接抓 B 站 CC/AI 字幕，20 分钟视频通常 1 秒级完成。
- 无字幕才下载音频，用本地 [faster-whisper](https://github.com/SYSTRAN/faster-whisper) 转写。
- 不为了转写下载完整视频，也不默认抽帧。
- 内置 Claude Code / Codex Skill，提供一次性安装命令。

> 非官方工具，使用 B 站 Web API。接口可能变化；请遵守 B 站用户协议和当地版权法规，仅用于个人学习与研究。

## 最简单的用法：把仓库地址发给 agent

不需要自己复制安装命令。把下面这句话发给 Claude Code / Codex：

> 请安装这个仓库里的 bili-transcript skill，并按 README / AGENTS.md 配置好：
> https://github.com/xgkirisub2/bili-transcript

agent 会读取仓库说明，安装 CLI 和 Skill；安装过程中可能会请你批准几条命令，确认即可。

装好后直接说：

> 转写这个 B 站视频：<链接>

<details>
<summary>手动安装（agent 无法自动完成时）</summary>

**Claude Code**（v2.1.292+）

```bash
uv tool install "bili-transcript[cuda] @ git+https://github.com/xgkirisub2/bili-transcript.git"
claude plugin install bili-transcript --marketplace xgkirisub2/bili-transcript
```

> 装完执行 `/reload-plugins` 或重启 Claude Code。旧版本 Claude Code：先 `claude plugin marketplace add xgkirisub2/bili-transcript`，再 `claude plugin install bili-transcript@bili-transcript --scope user`。

**Codex**

```bash
uv tool install "bili-transcript[cuda] @ git+https://github.com/xgkirisub2/bili-transcript.git"
bili-transcript install-skill --codex
```

> 装完新开一个 Codex 会话。

需要先安装 [uv](https://docs.astral.sh/uv/)。首次使用运行一次 `bili-transcript login`，用手机 B 站 App 扫码。没有 NVIDIA GPU 或使用 macOS 时，把 `[cuda]` 去掉；如果 `bili-transcript` 不在 PATH，运行 `uv tool update-shell`。

</details>

## 工作原理

```
链接 / BV / av / b23.tv
        │
        ▼
  元数据 + 字幕轨道（登录态 WBI）
        │
        ├── 有字幕 ──► 下载字幕 JSON ──► transcript.txt / .json / .srt
        │
        └── 无字幕 ──► B 站官方 AI 总结（如有）
                        │
                        └──► 下载音频（仅音频流）──► faster-whisper ──► 文字稿
```

## 环境要求

| 项目 | 要求 |
|---|---|
| Python | 3.10+，推荐 3.12 |
| 包管理器 | [uv](https://docs.astral.sh/uv/)（推荐）或 pip |
| 操作系统 | Windows 10/11、Linux、macOS |
| GPU | 可选。NVIDIA GPU + CUDA 12 + cuDNN 9 可大幅加速 |
| 磁盘 | GPU 版约 3.9 GB（依赖 2.3 GB + 模型 1.6 GB）；CPU 版更小 |
| 网络 | 能访问 B 站；首次 ASR 需下载模型（约 1.6 GB） |
| 账号 | 推荐登录 B 站账号；AI 字幕和官方总结需要登录态 |

> `ffmpeg` 不是主流程的硬依赖：字幕路径不需要，音频走 B 站直链；只有 yt-dlp 兜底或手动转码时才需要。

## 安装

### 方式一：全局安装 CLI（推荐）

```bash
# NVIDIA GPU
uv tool install "bili-transcript[cuda] @ git+https://github.com/xgkirisub2/bili-transcript.git"

# CPU / macOS
uv tool install "bili-transcript @ git+https://github.com/xgkirisub2/bili-transcript.git"
```

仓库地址：<https://github.com/xgkirisub2/bili-transcript>。安装后：

```bash
bili-transcript --version
bili-transcript doctor
```

如果提示 `bili-transcript` 不在 PATH，运行 `uv tool update-shell`，或把 uv 的 bin 目录加入 PATH。

### 方式二：克隆后本地开发

```bash
git clone https://github.com/xgkirisub2/bili-transcript.git
cd bili-transcript
uv sync --extra cuda   # NVIDIA GPU
# 或：uv sync            # CPU / macOS
uv run python -m bili_transcript doctor
```

本地运行时也可以用仓库根目录的 `./bili`（macOS/Linux）或 `bili.cmd`（Windows）。

### pip 用户

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
# NVIDIA GPU 额外执行：pip install -r requirements-cuda.txt
python -m bili_transcript doctor
```

## 登录

B 站对 AI 字幕和官方 AI 总结做了登录限制；匿名请求通常拿不到字幕列表，或触发 412 风控。

```bash
bili-transcript login
```

1. 显示二维码；
2. 用手机 B 站 App 扫码并确认；
3. Cookie 保存到 `~/.bili-transcript/config/credentials.json`。

拆开执行：

```bash
bili-transcript login --qr-only
bili-transcript login --poll
```

检查状态：

```bash
bili-transcript status
```

备用方式（从已登录浏览器复制 Cookie）：

```bash
bili-transcript login --cookie "SESSDATA=...; bili_jct=...; DedeUserID=..."
```

> `credentials.json` 等同于登录凭证，位于用户目录、不在仓库里。不要提交、分享或发给他人。Cookie 通常能维持几周到几个月；失效后重新 `login`。

## 使用

```bash
# 查看视频信息和字幕轨道
bili-transcript info "BV1xx411c7mD"

# 抓取文字稿（默认配置）
bili-transcript fetch "https://www.bilibili.com/video/BV1xx411c7mD/"

# 机器可读输出
bili-transcript fetch "BV1xx411c7mD" --json

# 多 P 视频第 2 P
bili-transcript fetch "BV1xx411c7mD" -p 2

# 强制重新抓取
bili-transcript fetch "BV1xx411c7mD" --force
```

| 参数 | 说明 |
|---|---|
| `-p, --page N` | 多 P 视频指定第 N P，默认 1 |
| `--force` | 忽略缓存，重新抓取 |
| `--no-asr` | 没有字幕时直接失败，不下载音频 |
| `--keep-audio` | ASR 成功后保留音频；默认删除以节省空间 |
| `--no-ai-summary` | 不请求 B 站官方 AI 总结 |
| `--model NAME` | faster-whisper 模型，默认 `large-v3-turbo` |
| `--device auto\|cuda\|cpu` | 转写设备，默认自动检测 |
| `--language zh\|auto` | 转写语言，默认 `zh` |
| `--json` | 输出机器可读 JSON，包含 `timings` |

**输入格式**：完整视频链接、`BV` 号、`av` 号、`b23.tv` 短链接、多 P 的 `?p=N`。

**默认配置**：字幕优先、`large-v3-turbo`、自动检测 CUDA、中文、音频流 30216、ASR 后删除音频、开启官方 AI 总结、开启缓存。默认值在 `src/bili_transcript/config.py`，由单元测试锁定。

## 输出

所有运行数据默认放在 `~/.bili-transcript/`：

```
~/.bili-transcript/
  config/
    credentials.json      # 登录 Cookie（敏感，勿分享）
    login_qr.png          # 最近一次登录二维码
  data/
    BV1xx411c7mD/
      p1/
        meta.json         # 标题、UP 主、时长、来源、timings
        transcript.txt    # 带 [mm:ss] 的分段文字稿
        transcript.json   # 逐段 start/end/text + 段落
        transcript.srt    # 字幕文件
        ai_conclusion.json# B 站官方 AI 总结（有内容时才保存）
        audio.m4a         # 仅在 --keep-audio 时保留
```

`transcript_source` 的可能值：

- `subtitle:zh-CN` / `subtitle:zh-Hans`：UP 主上传的 CC 字幕，质量通常最好。
- `subtitle:ai-zh`：B 站 AI 字幕，可能有专有名词识别错误。
- `ai-conclusion`：从官方 AI 总结接口中的字幕数据提取。
- `asr:large-v3-turbo`：本地语音转写，可能有同音字错误；中文结果会自动繁转简。

## 更多安装方式

`install-skill` 可以只装某一个目标：

```bash
bili-transcript install-skill --claude
bili-transcript install-skill --codex
bili-transcript install-skill --all
bili-transcript install-skill --project
bili-transcript install-skill --dir /path/to/skills
```

> Claude Code / Codex 没有“粘贴 URL 就静默安装”的内置能力；需要用户明确说“安装这个 skill”，并批准 agent 执行的命令。`AGENTS.md` 里是给 agent 的完整步骤。

## 性能与存储

Windows 11 + RTX 4070 Ti 12GB 实测：

| 场景 | 耗时 |
|---|---:|
| 有字幕，19:42 视频 | 约 1.1 秒 |
| 同视频再次运行（缓存） | 约 0.66 秒 |
| 无字幕，21:35 视频 | 约 37.5 秒（ASR 35.3 秒 + 音频 1.1 秒） |
| 无字幕，96 秒音频 | 4.1 秒 |
| 无字幕，10 分钟音频（估算） | 约 17 秒 |
| CPU 转写，10 分钟音频（估算） | 约 1–2 分钟 |

- 固定安装：GPU 版约 3.9 GB（依赖 2.3 GB + 模型 1.6 GB）。
- 每条视频：默认删除音频后约 **0.17–0.25 MB**。
- `--keep-audio`：21 分钟视频约 **11 MB**。
- API/转写费用：0；本地 GPU 推理，电费约 ¥0.001/条。

详细测算见 [docs/cost-analysis.md](docs/cost-analysis.md)。

## 常见问题

**字幕列表为空 / 提示需要登录？**

先 `status` 确认已登录。仍未拿到，可能是视频确实没有字幕，或字幕还在生成中；工具会自动走音频转写。

**412 / -352 / -101？**

通常是登录态失效或风控。重新 `login`；不要高频批量请求。

**GPU 没被用上？**

`doctor` 看 CUDA 设备数。安装时确认用了 `uv sync --extra cuda` 或 `uv tool install ".[cuda]"`。Windows 下会自动把 pip 安装的 cuBLAS/cuDNN DLL 加入搜索路径。

**首次转写很慢？**

首次要下载 `large-v3-turbo` 模型（约 1.6 GB）。中国大陆用户可以设置 `BILI_HF_MIRROR=1` 使用 HuggingFace 镜像，或设置 `HF_ENDPOINT`。

**`metadata_errors` / PyAV 不兼容？**

依赖已把 `av` 锁定在 16.x；不要升级到 19.x。

**VAD 过滤后没有文字？**

工具会自动关闭 VAD 重试一次，适用于歌曲、轻声或背景音较重的视频。

**多 P 视频？**

默认第 1 P；用 `-p N` 指定其他分P。

**Cookie 多久失效？**

通常几周到几个月。`status` 会检测；失效后重新扫码。

**音频下载很慢 / 超时？**

默认优先 30216 音频流，已避开实测较慢的 30232。如果仍慢，通常是 CDN/网络问题，重试即可。

## 项目结构

```
.
├── src/bili_transcript/
│   ├── cli.py        # CLI 入口 + install-skill
│   ├── auth.py       # 扫码登录、Cookie 处理
│   ├── config.py     # 用户数据目录、默认配置、凭证
│   ├── extract.py    # 元数据、字幕、AI 总结、音频下载
│   ├── asr.py        # faster-whisper 封装
│   └── installer.py  # 安装 Skill 到 Claude Code / Codex
├── skills/bili-transcript/SKILL.md
├── .claude-plugin/   # Claude Code plugin marketplace 清单 + 图标
├── AGENTS.md         # agent 安装说明（Codex 等）
├── CLAUDE.md         # Claude Code 项目上下文
├── tests/            # 单元测试（不依赖网络）
├── docs/cost-analysis.md
├── docs/analysis-prompt.md  # 可选的分析提示词示例
├── pyproject.toml
├── requirements.txt
├── requirements-cuda.txt
├── bili             # macOS/Linux 本地入口
└── bili.cmd         # Windows 本地入口
```

## 开发

```bash
uv sync
uv run python -m unittest discover -s tests -v
uv run python -m bili_transcript --help
```

测试不需要网络，也不会下载模型。提交前确保测试全部通过。

## 安全与合规

- `~/.bili-transcript/config/credentials.json` 是登录凭证；不要提交、分享或截图。
- 非官方工具，使用 B 站 Web API，接口可能变化；不保证长期可用。
- 仅用于个人学习、研究和分析；不要批量抓取、再分发受版权保护的内容。
- 按 MIT License 提供，作者不对使用后果负责。

## License

[MIT](LICENSE) © 2026 xgkiri

## 参考

- [bilibili-api-python](https://github.com/Nemo2011/bilibili-api)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect)（已归档，仅作参考）
- [B 站扫码登录接口文档](https://sessionhu.github.io/bilibili-API-collect/docs/login/login_action/QR.html)
