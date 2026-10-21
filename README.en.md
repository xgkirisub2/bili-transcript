# bili-transcript

[中文](README.md) | [English](README.en.md)

Fetch and convert Bilibili videos into local transcripts: metadata, subtitles, optional audio, and timestamped `transcript.txt/json/srt`.

The tool only handles **fetching and conversion**. What you do next — summarize, take notes, index, or feed another agent — is up to you.

- Subtitle-first: a 20-minute video is usually processed in about one second.
- Audio-only fallback with local [faster-whisper](https://github.com/SYSTRAN/faster-whisper) when no subtitle exists.
- No full-video download, no frame extraction by default.
- Ships with Claude Code / Codex skills and one-time install commands.

> Unofficial project built on Bilibili web APIs. Interfaces may change. Use it for personal study and research, and comply with Bilibili's terms and local copyright law.

## Easiest way: send the repo URL to your agent

No manual commands needed. Send this to Claude Code / Codex:

> Install the bili-transcript skill from this repository and configure it as described in README / AGENTS.md:
> https://github.com/xgkirisub2/bili-transcript

The agent reads the repository instructions and installs the CLI and skill. It may ask you to approve a few commands.

Then ask:

> Transcribe this Bilibili video: <link>

<details>
<summary>Manual install (if the agent cannot do it)</summary>

**Claude Code** (v2.1.292+)

```bash
uv tool install "bili-transcript[cuda] @ git+https://github.com/xgkirisub2/bili-transcript.git"
claude plugin install bili-transcript --marketplace xgkirisub2/bili-transcript
```

> Reload with `/reload-plugins` or restart Claude Code. Older Claude Code: run `claude plugin marketplace add xgkirisub2/bili-transcript`, then `claude plugin install bili-transcript@bili-transcript --scope user`.

**Codex**

```bash
uv tool install "bili-transcript[cuda] @ git+https://github.com/xgkirisub2/bili-transcript.git"
bili-transcript install-skill --codex
```

> Start a new Codex session after installation.

Install [uv](https://docs.astral.sh/uv/) first. On first use, run `bili-transcript login` and scan the QR code. Drop `[cuda]` on CPU/macOS. If `bili-transcript` is not on PATH, run `uv tool update-shell`.

</details>

## How it works

```
link / BV / av / b23.tv
        │
        ▼
  metadata + subtitle tracks (logged-in WBI)
        │
        ├── subtitle exists ──► download subtitle JSON ──► transcript.txt / .json / .srt
        │
        └── no subtitle ──► Bilibili AI conclusion (if any)
                              │
                              └──► download audio only ──► faster-whisper ──► transcript
```

## Requirements

| Item | Requirement |
|---|---|
| Python | 3.10+, 3.12 recommended |
| Package manager | [uv](https://docs.astral.sh/uv/) (recommended) or pip |
| OS | Windows 10/11, Linux, macOS |
| GPU | Optional. NVIDIA GPU with CUDA 12 + cuDNN 9 greatly speeds up ASR |
| Disk | About 3.9 GB for the GPU setup (2.3 GB deps + 1.6 GB model); less on CPU |
| Account | Recommended. Bilibili gates AI subtitles and AI summaries behind login |

`ffmpeg` is not required for the main path; it is only needed for the yt-dlp fallback or manual transcoding.

## Install

### Global CLI (recommended)

```bash
# NVIDIA GPU
uv tool install "bili-transcript[cuda] @ git+https://github.com/xgkirisub2/bili-transcript.git"

# CPU / macOS
uv tool install "bili-transcript @ git+https://github.com/xgkirisub2/bili-transcript.git"
```

Then:

```bash
bili-transcript --version
bili-transcript doctor
```

If `bili-transcript` is not on PATH, run `uv tool update-shell` or add uv's bin directory to PATH.

### From a clone

```bash
git clone https://github.com/xgkirisub2/bili-transcript.git
cd bili-transcript
uv sync --extra cuda   # NVIDIA GPU
# or: uv sync            # CPU / macOS
uv run python -m bili_transcript doctor
```

You can also use the local `./bili` (macOS/Linux) or `bili.cmd` (Windows) wrapper.

### pip

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
# NVIDIA GPU extras: pip install -r requirements-cuda.txt
python -m bili_transcript doctor
```

## Login

Bilibili requires a logged-in session for AI subtitles and AI summaries. The tool stores cookies locally; it never asks for your password.

```bash
bili-transcript login
```

Scan the QR code with the Bilibili mobile app and confirm on your phone. Cookies are written to `~/.bili-transcript/config/credentials.json`.

Split flow:

```bash
bili-transcript login --qr-only
bili-transcript login --poll
```

Cookie fallback:

```bash
bili-transcript login --cookie "SESSDATA=...; bili_jct=...; DedeUserID=..."
```

Cookies usually last weeks to months. Run `login` again when they expire. Treat them like a password.

## Usage

```bash
bili-transcript info "BV1xx411c7mD"
bili-transcript fetch "https://www.bilibili.com/video/BV1xx411c7mD/"
bili-transcript fetch "BV1xx411c7mD" --json
bili-transcript fetch "BV1xx411c7mD" -p 2
bili-transcript fetch "BV1xx411c7mD" --force
```

Flags: `--keep-audio` (default deletes audio after ASR), `--no-asr`, `--no-ai-summary`, `--model`, `--device`, `--language`.

Input formats: full URL, `BV` id, `av` id, `b23.tv` short link, and `?p=N` for multi-page videos.

### Output

```
~/.bili-transcript/
  config/
    credentials.json      # sensitive; never share
    login_qr.png
  data/
    BV1xx411c7mD/
      p1/
        meta.json
        transcript.txt    # [mm:ss] paragraphs
        transcript.json   # segment-level start/end/text
        transcript.srt
        ai_conclusion.json
        audio.m4a         # only with --keep-audio
```

## More install options

Select one or more skill targets:

```bash
bili-transcript install-skill --claude
bili-transcript install-skill --codex
bili-transcript install-skill --all
bili-transcript install-skill --project
bili-transcript install-skill --dir /path/to/skills
```

> Neither Claude Code nor Codex silently installs a skill just because a URL was pasted. The user must ask the agent to install it and approve the commands. See `AGENTS.md` for the full agent workflow.

## Performance and storage

Measured on Windows 11 + RTX 4070 Ti 12 GB:

| Scenario | Time |
|---|---:|
| 19:42 video with subtitles | ~1.1 s |
| Same video, cache hit | ~0.66 s |
| 21:35 video without subtitles | ~37.5 s (ASR 35.3 s + audio 1.1 s) |
| 96 s audio, no subtitles | 4.1 s |
| 10 min audio, GPU (estimate) | ~17 s |
| 10 min audio, CPU (estimate) | ~1–2 min |

- Fixed install: about 3.9 GB for GPU (2.3 GB deps + 1.6 GB model).
- Per video: about 0.17–0.25 MB after the default audio cleanup.
- With `--keep-audio`: about 11 MB for a 21-minute video.
- No paid API; local GPU electricity is roughly ¥0.001 per video.

See [docs/cost-analysis.md](docs/cost-analysis.md) for details (Chinese).

## Troubleshooting

- **No subtitles / login required**: run `status`, then `login`.
- **412 / -352 / -101**: expired cookies or rate limiting. Re-login and avoid aggressive batch requests.
- **GPU not used**: run `doctor`; install with `uv sync --extra cuda` or the `[cuda]` extra.
- **First ASR is slow**: the `large-v3-turbo` model (~1.6 GB) is downloaded on first use. In mainland China set `BILI_HF_MIRROR=1`.
- **`metadata_errors` / PyAV error**: `av` is pinned to 16.x; do not upgrade to 19.x.
- **VAD returns nothing**: the code retries once without VAD.
- **Multi-page videos**: page 1 is the default; use `-p N`.

## Security and compliance

- Cookies are credentials. `~/.bili-transcript/config/credentials.json` is outside the repository and must never be shared.
- Unofficial tool built on Bilibili web APIs; interfaces may change.
- Personal study and research only. Do not redistribute copyrighted content.
- MIT License, no warranty.

## License

[MIT](LICENSE) © 2026 xgkiri

## References

- [bilibili-api-python](https://github.com/Nemo2011/bilibili-api)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect) (archived)
- [Bilibili QR login docs](https://sessionhu.github.io/bilibili-API-collect/docs/login/login_action/QR.html)
