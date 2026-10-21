"""Fetch Bilibili metadata, subtitles and transcripts.

Design goals:
- never download the video unless audio-only transcription is needed;
- reuse a local cache per BV/page;
- fall back in this order: platform subtitle -> AI conclusion -> audio ASR.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from bilibili_api import video

from .asr import transcribe
from .config import (
    AUDIO_STREAM_PRIORITY,
    BASE_HEADERS,
    DATA_DIR,
    DEFAULT_DEVICE,
    DEFAULT_KEEP_AUDIO,
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL,
    get_credential,
)


class LoginRequiredError(RuntimeError):
    """Raised when Bilibili requires a logged-in session."""


class NoTranscriptError(RuntimeError):
    """Raised when neither subtitles nor ASR produced a transcript."""


BV_RE = re.compile(r"(BV[0-9A-Za-z]{10})")
AV_RE = re.compile(r"av(\d+)", re.IGNORECASE)
PAGE_RE = re.compile(r"[?&]p=(\d+)")
SHORT_RE = re.compile(r"https?://b23\.tv/[0-9A-Za-z]+")


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def resolve_input(raw: str) -> tuple[dict[str, int | str], int]:
    """Turn a BV/av/short/full URL into Video() kwargs plus a page number."""
    text = raw.strip()
    page_match = PAGE_RE.search(text)
    page = int(page_match.group(1)) if page_match else 1

    bv_match = BV_RE.search(text)
    if bv_match:
        return {"bvid": bv_match.group(1)}, page

    av_match = AV_RE.search(text)
    if av_match:
        return {"aid": int(av_match.group(1))}, page

    short_match = SHORT_RE.search(text)
    if short_match:
        log(f"解析短链接：{short_match.group(0)}")
        try:
            with httpx.Client(headers=BASE_HEADERS, follow_redirects=True, timeout=15) as client:
                response = client.get(short_match.group(0))
                final_url = str(response.url)
        except Exception as exc:
            raise ValueError(f"短链接解析失败：{exc}") from exc
        bv_match = BV_RE.search(final_url)
        if bv_match:
            page_match = PAGE_RE.search(final_url)
            return {"bvid": bv_match.group(1)}, int(page_match.group(1)) if page_match else page
        raise ValueError(f"短链接没有指向视频：{final_url}")

    raise ValueError(
        "无法识别输入。请提供 BV 号、av 号或 B 站视频链接，例如："
        "https://www.bilibili.com/video/BV1xx411c7mD/"
    )


def format_duration(seconds: float | int | None) -> str:
    if not seconds:
        return "未知"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_timestamp(seconds: float, srt: bool = False) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    if srt:
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def subtitle_score(track: dict[str, Any]) -> int:
    lan = str(track.get("lan") or "").lower()
    score = 0
    if lan in {"zh-hans", "zh-cn", "zh"}:
        score += 30
    elif lan.startswith("ai-zh"):
        score += 22
    elif lan.startswith("zh"):
        score += 20
    elif lan.startswith("ai-"):
        score += 8
    elif lan.startswith("en"):
        score += 4
    if not lan.startswith("ai-"):
        score += 5
    if track.get("subtitle_url"):
        score += 10
    return score


def normalize_subtitle_url(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://"):
        return "https://" + url[len("http://") :]
    return url


def download_subtitle(track: dict[str, Any], referer: str) -> list[dict[str, Any]]:
    url = normalize_subtitle_url(str(track.get("subtitle_url") or ""))
    if not url:
        return []
    headers = {
        **BASE_HEADERS,
        "Referer": referer,
        "Origin": "https://www.bilibili.com",
    }
    with httpx.Client(headers=headers, follow_redirects=True, timeout=30) as client:
        response = client.get(url)
        response.raise_for_status()
        payload = response.json()

    body = payload.get("body") or []
    segments: list[dict[str, Any]] = []
    for item in body:
        text = str(item.get("content") or "").strip()
        if not text:
            continue
        segments.append(
            {
                "start": round(float(item.get("from") or 0), 3),
                "end": round(float(item.get("to") or 0), 3),
                "text": text,
            }
        )
    return segments


def segments_from_ai_conclusion(payload: dict[str, Any]) -> list[dict[str, Any]]:
    model = payload.get("model_result") or payload.get("data", {}).get("model_result") or {}
    parts = model.get("subtitle") or []
    segments: list[dict[str, Any]] = []
    for part in parts:
        for item in part.get("part_subtitle") or []:
            text = str(item.get("content") or "").strip()
            if not text:
                continue
            start = item.get("start_timestamp")
            end = item.get("end_timestamp")
            if start is None:
                continue
            segments.append(
                {
                    "start": round(float(start), 3),
                    "end": round(float(end if end is not None else start), 3),
                    "text": text,
                }
            )
    return segments


CJK_PUNCTUATION = ("。", "！", "？", "；", "，", "、", "：", "”", "》", "）", ".", "!", "?", ";", ",", ":")


def join_texts(items: list[dict[str, Any]], language: str) -> str:
    """Join segments readably.

    Chinese AI subtitles often have no punctuation, so keep a space at segment
    boundaries. If the previous segment already ends with punctuation, avoid
    inserting a space before the next sentence.
    """
    is_chinese = "zh" in str(language).lower()
    text = ""
    for item in items:
        part = item["text"].strip()
        if not part:
            continue
        if not text:
            text = part
        elif is_chinese and (text.endswith(CJK_PUNCTUATION) or part.startswith(CJK_PUNCTUATION)):
            text += part
        else:
            text += " " + part
    return text


def group_segments(
    segments: list[dict[str, Any]],
    language: str,
    max_gap: float = 2.0,
    max_duration: float = 30.0,
    max_chars: int = 300,
) -> list[dict[str, Any]]:
    if not segments:
        return []
    paragraphs: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        paragraphs.append(
            {
                "start": current[0]["start"],
                "end": current[-1]["end"],
                "text": join_texts(current, language),
            }
        )
        current = []

    for segment in segments:
        if not current:
            current = [segment]
            continue
        gap = segment["start"] - current[-1]["end"]
        duration = segment["end"] - current[0]["start"]
        chars = sum(len(item["text"]) for item in current) + len(segment["text"])
        if gap > max_gap or duration > max_duration or chars > max_chars:
            flush()
            current = [segment]
        else:
            current.append(segment)
    flush()
    return paragraphs


def simplify_chinese(segments: list[dict[str, Any]], source: str, language: str) -> None:
    """Convert Whisper's traditional Chinese output to simplified in place."""
    if not source.startswith("asr:") or not str(language).lower().startswith("zh"):
        return
    try:
        from opencc import OpenCC
    except ImportError:
        return
    converter = OpenCC("t2s")
    for segment in segments:
        segment["text"] = converter.convert(segment["text"])


def write_transcript(
    cache_dir: Path,
    meta: dict[str, Any],
    segments: list[dict[str, Any]],
    source: str,
    language: str,
    partial: bool,
) -> dict[str, Any]:
    simplify_chinese(segments, source, language)
    paragraphs = group_segments(segments, language)
    transcript_json = cache_dir / "transcript.json"
    transcript_txt = cache_dir / "transcript.txt"
    transcript_srt = cache_dir / "transcript.srt"

    payload = {
        "title": meta["title"],
        "page_title": meta["page_title"],
        "url": meta["url"],
        "source": source,
        "language": language,
        "duration": meta["duration"],
        "partial": partial,
        "segments": segments,
        "paragraphs": paragraphs,
    }
    transcript_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    header = [
        f"# {meta['title']}",
        f"# 分P：{meta['page_title']}",
        f"# 链接：{meta['url']}",
        f"# 来源：{source} | 语言：{language} | 时长：{format_duration(meta['duration'])}",
        f"# 生成时间：{meta['fetched_at']}",
        "",
    ]
    lines = header[:]
    for paragraph in paragraphs:
        lines.append(f"[{format_timestamp(paragraph['start'])}] {paragraph['text']}")
        lines.append("")
    transcript_txt.write_text("\n".join(lines), encoding="utf-8")

    srt_lines: list[str] = []
    for index, segment in enumerate(segments, 1):
        srt_lines.append(str(index))
        srt_lines.append(f"{format_timestamp(segment['start'], srt=True)} --> {format_timestamp(segment['end'], srt=True)}")
        srt_lines.append(segment["text"])
        srt_lines.append("")
    transcript_srt.write_text("\n".join(srt_lines), encoding="utf-8")

    return {
        "transcript_json": str(transcript_json),
        "transcript_txt": str(transcript_txt),
        "transcript_srt": str(transcript_srt),
        "paragraphs": len(paragraphs),
        "segment_count": len(segments),
    }


async def get_video_object(spec: dict[str, int | str], credential: Any | None):
    kwargs: dict[str, Any] = dict(spec)
    if credential is not None:
        kwargs["credential"] = credential
    return video.Video(**kwargs)


async def fetch_subtitle_segments(
    video_obj: video.Video,
    cid: int,
    referer: str,
    duration: float,
) -> tuple[list[dict[str, Any]], str, str, bool]:
    """Return (segments, source, language, partial)."""
    try:
        subtitle_info = await video_obj.get_subtitle(cid=cid)
    except Exception as exc:
        log(f"字幕接口失败：{exc}")
        return [], "", "", False

    tracks = (subtitle_info or {}).get("subtitles") or []
    if not tracks:
        log("没有可用的字幕轨道（通常需要登录；已登录则是该视频确实没有字幕）。")
        return [], "", "", False

    for track in sorted(tracks, key=subtitle_score, reverse=True):
        lan = str(track.get("lan") or "unknown")
        log(f"发现字幕轨道：{lan}（{track.get('lan_doc') or ''}，ai_status={track.get('ai_status')}）")
        if not track.get("subtitle_url"):
            log(f"轨道 {lan} 没有 subtitle_url，跳过。")
            continue
        try:
            segments = download_subtitle(track, referer)
        except Exception as exc:
            log(f"下载字幕 {lan} 失败：{exc}")
            continue
        if not segments:
            log(f"轨道 {lan} 内容为空，跳过。")
            continue

        last_end = max(item["end"] for item in segments)
        partial = bool(duration and last_end < duration * 0.8)
        if partial and duration > 120:
            log(
                f"警告：字幕只覆盖到 {format_duration(last_end)} / {format_duration(duration)}，"
                "可能是限流导致的截断。"
            )
            # One retry with a freshly signed URL.
            try:
                await asyncio.sleep(2)
                fresh = await video_obj.get_subtitle(cid=cid)
                fresh_tracks = (fresh or {}).get("subtitles") or []
                for fresh_track in sorted(fresh_tracks, key=subtitle_score, reverse=True):
                    if fresh_track.get("lan") != lan or not fresh_track.get("subtitle_url"):
                        continue
                    retry_segments = download_subtitle(fresh_track, referer)
                    if retry_segments and max(item["end"] for item in retry_segments) > last_end:
                        segments = retry_segments
                        last_end = max(item["end"] for item in segments)
                        partial = bool(duration and last_end < duration * 0.8)
                        log("重试后字幕覆盖范围已更新。")
                    break
            except Exception as exc:
                log(f"字幕重试失败：{exc}")

        return segments, f"subtitle:{lan}", lan, partial

    return [], "", "", False


async def fetch_ai_conclusion_payload(
    video_obj: video.Video,
    cid: int,
    page_index: int,
    up_mid: int,
) -> dict[str, Any] | None:
    try:
        payload = await video_obj.get_ai_conclusion(
            cid=cid,
            page_index=page_index,
            up_mid=up_mid,
        )
        if isinstance(payload, dict) and payload:
            return payload
    except Exception as exc:
        log(f"官方 AI 总结接口不可用：{exc}")
    return None


def pick_audio_stream(download_info: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    dash = download_info.get("dash") or {}
    audios = list(dash.get("audio") or [])
    flac = dash.get("flac") or {}
    if isinstance(flac, dict) and flac.get("audio"):
        audios.append(flac["audio"])
    if not audios:
        raise NoTranscriptError("该视频没有可用的 DASH 音频流。")

    # Prefer the 30216 AAC stream: speech ASR does not need more, and it was
    # the only stable stream in the benchmark (30232 timed out).
    priority_by_id = {stream_id: index for index, stream_id in enumerate(AUDIO_STREAM_PRIORITY)}

    def rank(item: dict[str, Any]) -> tuple[int, int]:
        return priority_by_id.get(item.get("id"), len(AUDIO_STREAM_PRIORITY)), int(
            item.get("bandwidth") or 0
        )

    audios.sort(key=rank)
    chosen = audios[0]
    urls: list[str] = [str(chosen.get("baseUrl") or chosen.get("base_url") or "")]
    backup = chosen.get("backupUrl") or chosen.get("backup_url") or []
    if isinstance(backup, str):
        urls.append(backup)
    else:
        urls.extend(str(url) for url in backup)
    return [url for url in urls if url], chosen


def download_audio(urls: list[str], destination: Path, referer: str) -> Path:
    headers = {
        **BASE_HEADERS,
        "Referer": referer,
        "Origin": "https://www.bilibili.com",
    }
    last_error: Exception | None = None
    for url in urls:
        try:
            downloaded = 0
            with httpx.Client(headers=headers, follow_redirects=True, timeout=60) as client:
                with client.stream("GET", url) as response:
                    response.raise_for_status()
                    with destination.open("wb") as handle:
                        for chunk in response.iter_bytes(chunk_size=256 * 1024):
                            handle.write(chunk)
                            downloaded += len(chunk)
                            if downloaded and downloaded % (5 * 1024 * 1024) < 256 * 1024:
                                log(f"  已下载音频 {downloaded / 1024 / 1024:.1f} MB")
            if destination.exists() and destination.stat().st_size > 1024:
                log(f"音频下载完成：{destination.name}（{destination.stat().st_size / 1024 / 1024:.1f} MB）")
                return destination
        except Exception as exc:
            last_error = exc
            destination.unlink(missing_ok=True)
            log(f"音频源下载失败，尝试备用地址：{exc}")
    raise NoTranscriptError(f"音频下载失败：{last_error}")


def download_audio_with_ytdlp(cache_dir: Path, referer: str) -> Path:
    log("尝试用 yt-dlp 下载音频...")
    try:
        import yt_dlp
    except ImportError as exc:
        raise NoTranscriptError("yt-dlp 未安装，无法下载音频。") from exc

    options = {
        "format": "bestaudio",
        "outtmpl": str(cache_dir / "audio.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "http_headers": {**BASE_HEADERS, "Referer": referer},
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([referer])
    candidates = sorted(cache_dir.glob("audio.*"), key=lambda path: path.stat().st_size, reverse=True)
    if not candidates:
        raise NoTranscriptError("yt-dlp 没有产出音频文件。")
    return candidates[0]


async def fetch_video(
    url: str,
    page: int = 1,
    force: bool = False,
    no_asr: bool = False,
    no_ai_summary: bool = False,
    model: str = DEFAULT_MODEL,
    device: str = DEFAULT_DEVICE,
    language: str = DEFAULT_LANGUAGE,
    keep_audio: bool = DEFAULT_KEEP_AUDIO,
) -> dict[str, Any]:
    pipeline_started = time.perf_counter()
    timings: dict[str, float] = {}

    spec, page_from_url = resolve_input(url)
    if page == 1 and page_from_url != 1:
        page = page_from_url

    credential = get_credential()
    if credential is None:
        log("提示：尚未登录。AI 字幕通常需要登录；本次会先尝试公开字幕，失败则转写音频。")
        log("      登录命令：bili-transcript login")

    video_obj = await get_video_object(spec, credential)
    phase_started = time.perf_counter()
    try:
        info = await video_obj.get_info()
    except Exception as exc:
        message = str(exc)
        if "-101" in message or "-403" in message or "412" in message:
            raise LoginRequiredError(
                f"B 站拒绝访问（{message}）。请先运行 bili-transcript login，"
                "并确认视频可正常播放。"
            ) from exc
        raise
    timings["metadata"] = round(time.perf_counter() - phase_started, 3)

    bvid = str(info.get("bvid") or "")
    aid = int(info.get("aid") or 0)
    pages = info.get("pages") or [
        {"cid": info.get("cid"), "page": 1, "part": info.get("title"), "duration": info.get("duration")}
    ]
    if page < 1 or page > len(pages):
        raise ValueError(f"分P {page} 不存在；该视频共 {len(pages)} P。")
    page_info = pages[page - 1]
    cid = int(page_info.get("cid") or info.get("cid"))
    page_title = str(page_info.get("part") or info.get("title") or "")
    duration = float(page_info.get("duration") or info.get("duration") or 0)
    page_url = f"https://www.bilibili.com/video/{bvid}/?p={page}" if len(pages) > 1 else f"https://www.bilibili.com/video/{bvid}/"

    cache_dir = DATA_DIR / bvid / f"p{page}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    meta_path = cache_dir / "meta.json"
    transcript_json = cache_dir / "transcript.json"

    if transcript_json.exists() and not force:
        try:
            cached = json.loads(transcript_json.read_text(encoding="utf-8"))
            log(f"命中缓存：{cache_dir}")
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            timings["cache_load"] = round(time.perf_counter() - pipeline_started, 3)
            timings["total"] = timings["cache_load"]
            return {
                "ok": True,
                "cached": True,
                "bvid": bvid,
                "aid": aid,
                "page": page,
                "pages": len(pages),
                "title": info.get("title"),
                "page_title": page_title,
                "owner": (info.get("owner") or {}).get("name"),
                "duration": duration,
                "url": page_url,
                "cache_dir": str(cache_dir),
                "transcript_txt": str(cache_dir / "transcript.txt"),
                "transcript_json": str(transcript_json),
                "transcript_srt": str(cache_dir / "transcript.srt"),
                "transcript_source": cached.get("source"),
                "transcript_language": cached.get("language"),
                "segment_count": len(cached.get("segments") or []),
                "paragraph_count": len(cached.get("paragraphs") or []),
                "partial": cached.get("partial", False),
                "ai_conclusion_path": str(cache_dir / "ai_conclusion.json")
                if (cache_dir / "ai_conclusion.json").exists()
                else None,
                "meta_path": str(meta_path),
                "audio_path": meta.get("audio_path"),
                "audio_retained": meta.get("audio_retained", False),
                "timings": timings,
            }
        except (OSError, json.JSONDecodeError):
            log("缓存损坏，重新抓取。")

    stamp = datetime.now().isoformat(timespec="seconds")
    meta: dict[str, Any] = {
        "bvid": bvid,
        "aid": aid,
        "cid": cid,
        "title": info.get("title"),
        "page_title": page_title,
        "page": page,
        "pages": len(pages),
        "owner": (info.get("owner") or {}).get("name"),
        "owner_mid": (info.get("owner") or {}).get("mid"),
        "duration": duration,
        "pubdate": datetime.fromtimestamp(int(info.get("pubdate") or 0)).isoformat(timespec="seconds")
        if info.get("pubdate")
        else None,
        "url": page_url,
        "cover": info.get("pic"),
        "description": info.get("desc"),
        "fetched_at": stamp,
    }

    # 1) Platform subtitles (CC or AI) - the fast path.
    phase_started = time.perf_counter()
    segments, source, transcript_language, partial = await fetch_subtitle_segments(
        video_obj, cid, page_url, duration
    )
    timings["subtitle"] = round(time.perf_counter() - phase_started, 3)

    # 2) Bilibili's own AI conclusion. Used as auxiliary material and, when it
    #    contains the AI subtitle body, as a transcript source.
    ai_payload: dict[str, Any] | None = None
    phase_started = time.perf_counter()
    if not no_ai_summary:
        ai_payload = await fetch_ai_conclusion_payload(
            video_obj, cid, page - 1, int(meta.get("owner_mid") or 0)
        )
        if ai_payload:
            model_result = ai_payload.get("model_result") or {}
            has_content = bool(
                model_result.get("summary")
                or model_result.get("outline")
                or model_result.get("subtitle")
            )
            if has_content:
                ai_path = cache_dir / "ai_conclusion.json"
                ai_path.write_text(
                    json.dumps(ai_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                meta["ai_conclusion_path"] = str(ai_path)
                if not segments:
                    ai_segments = segments_from_ai_conclusion(ai_payload)
                    if ai_segments:
                        segments = ai_segments
                        source = "ai-conclusion"
                        transcript_language = "zh"
                        last_end = max(item["end"] for item in segments)
                        partial = bool(duration and last_end < duration * 0.8)
                        log(f"使用官方 AI 总结中的字幕：{len(segments)} 段。")
            else:
                log("官方 AI 总结暂无内容，跳过保存。")
    timings["ai_conclusion"] = round(time.perf_counter() - phase_started, 3)

    # 3) Audio-only fallback with local ASR.
    asr_info: dict[str, Any] | None = None
    audio_path: Path | None = None
    if not segments:
        if no_asr:
            raise NoTranscriptError(
                "没有字幕，且已指定 --no-asr。请先登录后重试，或去掉 --no-asr 以启用音频转写。"
            )
        log("没有可用字幕，进入音频转写兜底。")
        phase_started = time.perf_counter()
        try:
            download_info = await video_obj.get_download_url(cid=cid, page_index=page - 1)
            urls, chosen = pick_audio_stream(download_info)
            mime = str(chosen.get("mimeType") or chosen.get("mime_type") or "audio/mp4")
            extension = ".flac" if "flac" in mime.lower() else ".m4a"
            audio_path = cache_dir / f"audio{extension}"
            log(f"选择音频流：id={chosen.get('id')} bandwidth={chosen.get('bandwidth')} mime={mime}")
            download_audio(urls, audio_path, page_url)
        except Exception as exc:
            log(f"直链下载音频失败：{exc}")
            if audio_path is not None:
                audio_path.unlink(missing_ok=True)
            audio_path = download_audio_with_ytdlp(cache_dir, page_url)
        timings["audio_download"] = round(time.perf_counter() - phase_started, 3)

        phase_started = time.perf_counter()
        try:
            segments, asr_info = transcribe(
                audio_path,
                model_size=model,
                device=device,
                language=language,
            )
        except Exception as exc:
            log(f"声音转写失败（{exc}），尝试 CPU int8 重试一次。")
            try:
                segments, asr_info = transcribe(
                    audio_path,
                    model_size=model,
                    device="cpu",
                    language=language,
                )
            except Exception as cpu_exc:
                raise NoTranscriptError(f"音频转写失败：{cpu_exc}") from cpu_exc
        timings["asr"] = round(time.perf_counter() - phase_started, 3)
        source = f"asr:{asr_info.get('model')}"
        transcript_language = str(asr_info.get("language") or language)
        partial = False
        meta["audio_path"] = str(audio_path) if keep_audio else None
        meta["audio_retained"] = keep_audio
        meta["asr"] = asr_info

    if not segments:
        raise NoTranscriptError("未能获得任何文字稿。")

    meta["transcript_source"] = source
    meta["transcript_language"] = transcript_language
    meta["partial"] = partial
    meta["segment_count"] = len(segments)

    phase_started = time.perf_counter()
    paths = write_transcript(cache_dir, meta, segments, source, transcript_language, partial)
    timings["write"] = round(time.perf_counter() - phase_started, 3)
    timings["total"] = round(time.perf_counter() - pipeline_started, 3)
    meta["timings"] = timings
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    if not keep_audio and audio_path is not None and audio_path.exists():
        audio_path.unlink(missing_ok=True)
        log("已删除临时音频（保留文字稿；需要保留请加 --keep-audio）。")

    return {
        "ok": True,
        "cached": False,
        "bvid": bvid,
        "aid": aid,
        "page": page,
        "pages": len(pages),
        "title": info.get("title"),
        "page_title": page_title,
        "owner": (info.get("owner") or {}).get("name"),
        "duration": duration,
        "url": page_url,
        "cache_dir": str(cache_dir),
        "transcript_txt": paths["transcript_txt"],
        "transcript_json": paths["transcript_json"],
        "transcript_srt": paths["transcript_srt"],
        "transcript_source": source,
        "transcript_language": transcript_language,
        "segment_count": paths["segment_count"],
        "paragraph_count": paths["paragraphs"],
        "partial": partial,
        "ai_conclusion_path": meta.get("ai_conclusion_path"),
        "meta_path": str(meta_path),
        "audio_path": meta.get("audio_path"),
        "audio_retained": meta.get("audio_retained", False),
        "timings": timings,
    }
