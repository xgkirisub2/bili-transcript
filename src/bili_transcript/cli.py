"""CLI entry point for bili-transcript.

Examples:
    bili-transcript login
    bili-transcript info BV1xx411c7mD
    bili-transcript fetch "https://www.bilibili.com/video/BV1xx411c7mD/" --json
    bili-transcript install-skill --all
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from .auth import cookie_login, nav_status, poll_qr, qr_login, request_qr
from .config import (
    DEFAULT_DEVICE,
    DEFAULT_KEEP_AUDIO,
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL,
    HOME,
    get_credential,
    setup_stdio,
)
from .extract import (
    LoginRequiredError,
    NoTranscriptError,
    fetch_video,
    format_duration,
    get_video_object,
    resolve_input,
)
from .installer import install_skill


def print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


async def show_info(raw: str, page: int) -> int:
    spec, page_from_url = resolve_input(raw)
    if page == 1 and page_from_url != 1:
        page = page_from_url
    video_obj = await get_video_object(spec, get_credential())
    info = await video_obj.get_info()
    pages = info.get("pages") or [
        {"cid": info.get("cid"), "page": 1, "part": info.get("title"), "duration": info.get("duration")}
    ]
    page_info = pages[page - 1]
    cid = int(page_info.get("cid") or info.get("cid"))

    print(f"标题：{info.get('title')}")
    print(f"UP 主：{(info.get('owner') or {}).get('name')}")
    print(f"时长：{format_duration(page_info.get('duration') or info.get('duration'))}")
    print(f"分P：{page}/{len(pages)}  {page_info.get('part') or ''}")
    print(f"BV：{info.get('bvid')}  aid：{info.get('aid')}  cid：{cid}")
    print(f"链接：https://www.bilibili.com/video/{info.get('bvid')}/?p={page}")

    try:
        subtitle_info = await video_obj.get_subtitle(cid=cid)
        tracks = (subtitle_info or {}).get("subtitles") or []
    except Exception as exc:
        print(f"字幕查询失败：{exc}")
        return 0
    if not tracks:
        print("字幕：无（未登录时 AI 字幕会被隐藏）")
    else:
        print("字幕轨道：")
        for track in tracks:
            state = "有 URL" if track.get("subtitle_url") else "无 URL"
            print(
                f"  - {track.get('lan')} / {track.get('lan_doc')} "
                f"(ai_status={track.get('ai_status')}, {state})"
            )
    return 0


async def run_fetch(args: argparse.Namespace) -> int:
    try:
        result = await fetch_video(
            args.url,
            page=args.page,
            force=args.force,
            no_asr=args.no_asr,
            no_ai_summary=args.no_ai_summary,
            model=args.model,
            device=args.device,
            language=args.language,
            keep_audio=args.keep_audio,
        )
    except LoginRequiredError as exc:
        print(f"需要登录：{exc}", file=sys.stderr)
        return 2
    except NoTranscriptError as exc:
        print(f"没有拿到文字稿：{exc}", file=sys.stderr)
        return 3
    except ValueError as exc:
        print(f"输入有误：{exc}", file=sys.stderr)
        return 4

    if args.json:
        print_json(result)
    else:
        print(f"标题：{result['title']}")
        print(f"UP 主：{result['owner']}   时长：{format_duration(result['duration'])}")
        print(f"分P：{result['page']}/{result['pages']}  {result['page_title']}")
        print(f"来源：{result['transcript_source']}   语言：{result['transcript_language']}")
        print(f"缓存：{'是' if result['cached'] else '否'}   段数：{result['segment_count']}")
        print(f"文字稿：{result['transcript_txt']}")
        print(f"文字稿 JSON：{result['transcript_json']}")
        print(f"字幕 SRT：{result['transcript_srt']}")
        print(f"元数据：{result['meta_path']}")
        if str(result.get("transcript_source") or "").startswith("asr:"):
            print(f"音频：{'已保留' if result.get('audio_retained') else '已删除（节省空间）'}")
        if result.get("partial"):
            print("注意：字幕覆盖不完整，使用时请说明。", file=sys.stderr)
    return 0


async def run_login(args: argparse.Namespace) -> int:
    if args.cookie:
        return await cookie_login(args.cookie)
    if args.qr_only:
        return await request_qr()
    if args.poll:
        return await poll_qr()
    return await qr_login(force=args.force)


async def run_doctor(_: argparse.Namespace) -> int:
    print(f"bili-transcript: {__version__}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"解释器: {sys.executable}")
    print(f"数据目录: {HOME}")
    for module_name in ("bilibili_api", "httpx", "faster_whisper", "yt_dlp", "qrcode", "opencc"):
        try:
            module = __import__(module_name)
            version = getattr(module, "__version__", "?")
            print(f"依赖 {module_name}: OK ({version})")
        except Exception as exc:
            print(f"依赖 {module_name}: 缺失或不可用（{exc}）")

    try:
        from .asr import _prepare_cuda_dlls

        _prepare_cuda_dlls()
        import ctranslate2

        count = ctranslate2.get_cuda_device_count()
        print(f"CUDA 设备数: {count}")
        if count:
            print(f"CUDA 计算类型: {sorted(ctranslate2.get_supported_compute_types('cuda'))}")
    except Exception as exc:
        print(f"CUDA 检测失败: {exc}")

    print(f"命令行: {shutil.which('bili-transcript') or '未在 PATH 中找到'}")
    for label, path in _skill_locations().items():
        print(f"Skill {label}: {'已安装' if path.exists() else '未安装'} ({path})")

    return await run_status(argparse.Namespace())


def _skill_locations() -> dict[str, Path]:
    home = Path.home()
    return {
        "Claude Code": home / ".claude" / "skills" / "bili-transcript" / "SKILL.md",
        "Codex (~/.codex)": home / ".codex" / "skills" / "bili-transcript" / "SKILL.md",
        "Codex (~/.agents)": home / ".agents" / "skills" / "bili-transcript" / "SKILL.md",
    }


async def run_status(_: argparse.Namespace) -> int:
    credential = get_credential()
    if credential is None:
        print("登录状态：未登录")
        print("运行 bili-transcript login 扫码登录。")
        return 0
    ok, data = await nav_status(credential)
    if ok:
        print(f"登录状态：已登录（{data.get('uname')}，UID {data.get('mid')}）")
        return 0
    print("登录状态：Cookie 已失效，请重新运行 bili-transcript login")
    return 2


async def run_install_skill(args: argparse.Namespace) -> int:
    targets: set[str] = set()
    if args.all or not any((args.claude, args.codex, args.project, args.dir)):
        targets.update({"claude", "codex"})
    if args.claude:
        targets.add("claude")
    if args.codex:
        targets.add("codex")
    if args.project:
        targets.add("project")

    try:
        destinations = install_skill(
            targets,
            project_dir=Path.cwd() if args.project else None,
            custom_dir=Path(args.dir).expanduser() if args.dir else None,
        )
    except Exception as exc:
        print(f"安装 Skill 失败：{exc}", file=sys.stderr)
        return 1

    for destination in destinations:
        print(f"已安装: {destination / 'SKILL.md'}")
    if shutil.which("bili-transcript") is None:
        print(
            "提示：bili-transcript 不在 PATH 中。运行 `uv tool update-shell` "
            "或把 uv 的 bin 目录加入 PATH，Skill 才能直接调用。",
            file=sys.stderr,
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bilibili video transcript fetching and conversion",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    login_parser = subparsers.add_parser("login", help="扫码登录并保存 Cookie")
    login_parser.add_argument("--force", action="store_true", help="强制重新扫码，即使当前已登录")
    login_parser.add_argument("--qr-only", action="store_true", help="只生成二维码并退出")
    login_parser.add_argument("--poll", action="store_true", help="轮询已生成的二维码")
    login_parser.add_argument(
        "--cookie",
        help="备用登录方式：直接传入 SESSDATA=...; bili_jct=...; DedeUserID=...",
    )
    login_parser.set_defaults(handler=run_login)

    status_parser = subparsers.add_parser("status", help="检查登录状态")
    status_parser.set_defaults(handler=run_status)

    doctor_parser = subparsers.add_parser("doctor", help="检查依赖、CUDA、Skill 和登录状态")
    doctor_parser.set_defaults(handler=run_doctor)

    info_parser = subparsers.add_parser("info", help="查看视频信息和字幕轨道")
    info_parser.add_argument("url", help="BV 号、av 号或视频链接")
    info_parser.add_argument("-p", "--page", type=int, default=1, help="分P 序号，从 1 开始")
    info_parser.set_defaults(handler=info_handler)

    fetch_parser = subparsers.add_parser("fetch", help="抓取文字稿（字幕优先，音频转写兜底）")
    fetch_parser.add_argument("url", help="BV 号、av 号或视频链接")
    fetch_parser.add_argument("-p", "--page", type=int, default=1, help="分P 序号，从 1 开始")
    fetch_parser.add_argument("--force", action="store_true", help="忽略缓存，重新抓取")
    fetch_parser.add_argument("--no-asr", action="store_true", help="没有字幕时直接失败，不下载音频转写")
    fetch_parser.add_argument("--no-ai-summary", action="store_true", help="不请求 B 站官方 AI 总结")
    fetch_parser.add_argument(
        "--keep-audio",
        action="store_true",
        default=DEFAULT_KEEP_AUDIO,
        help="ASR 成功后保留下载的音频（默认删除以节省空间）",
    )
    fetch_parser.add_argument("--model", default=DEFAULT_MODEL, help="faster-whisper 模型")
    fetch_parser.add_argument(
        "--device",
        default=DEFAULT_DEVICE,
        choices=["auto", "cuda", "cpu"],
        help="转写设备，默认自动检测",
    )
    fetch_parser.add_argument(
        "--language",
        default=DEFAULT_LANGUAGE,
        help="转写语言，默认 zh；设为 auto 自动识别",
    )
    fetch_parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    fetch_parser.set_defaults(handler=run_fetch)

    install_parser = subparsers.add_parser(
        "install-skill",
        help="安装 Skill 到 Claude Code / Codex",
    )
    install_parser.add_argument(
        "--all",
        action="store_true",
        help="安装到 Claude Code 和 Codex（默认行为）",
    )
    install_parser.add_argument("--claude", action="store_true", help="安装到 ~/.claude/skills")
    install_parser.add_argument(
        "--codex",
        action="store_true",
        help="安装到 ~/.codex/skills 和 ~/.agents/skills",
    )
    install_parser.add_argument(
        "--project",
        action="store_true",
        help="安装到当前项目的 .claude/.codex/.agents 目录",
    )
    install_parser.add_argument("--dir", help="安装到指定目录（其下创建 bili-transcript/SKILL.md）")
    install_parser.set_defaults(handler=run_install_skill)

    return parser


async def info_handler(args: argparse.Namespace) -> int:
    return await show_info(args.url, args.page)


def main() -> int:
    setup_stdio()
    parser = build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(args.handler(args))
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
