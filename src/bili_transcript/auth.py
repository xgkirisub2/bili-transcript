"""Bilibili QR-code login and login-state checks.

The QR flow is split into two commands so the agent can show the code first
and poll separately:
    bili-transcript login --qr-only
    bili-transcript login --poll
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlparse

import httpx
import qrcode

from .config import (
    BASE_HEADERS,
    QR_PENDING_PATH,
    QR_PNG_PATH,
    ensure_dirs,
    load_credentials,
    save_credentials,
    to_credential,
)

GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
BUVID_URL = "https://api.bilibili.com/x/frontend/finger/spi"


async def fetch_buvid() -> tuple[str, str]:
    """Fetch anonymous device ids, which reduce risk-control rejections."""
    try:
        async with httpx.AsyncClient(headers=BASE_HEADERS, timeout=10, follow_redirects=True) as client:
            response = await client.get(BUVID_URL)
            data = response.json().get("data") or {}
            return str(data.get("b_3") or ""), str(data.get("b_4") or "")
    except Exception:
        return "", ""


async def nav_status(credential=None) -> tuple[bool, dict]:
    cookies = credential.get_cookies() if credential is not None else {}
    try:
        async with httpx.AsyncClient(headers=BASE_HEADERS, timeout=10, follow_redirects=True) as client:
            response = await client.get(NAV_URL, cookies=cookies)
            payload = response.json()
    except Exception as exc:
        return False, {"error": str(exc)}
    data = payload.get("data") or {}
    return payload.get("code") == 0 and bool(data.get("isLogin")), data


def render_qr(url: str) -> None:
    qr = qrcode.QRCode(border=1, box_size=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    qrcode.make(url).save(QR_PNG_PATH)


async def request_qr() -> int:
    ensure_dirs()
    async with httpx.AsyncClient(headers=BASE_HEADERS, timeout=15, follow_redirects=True) as client:
        response = await client.get(GENERATE_URL)
        payload = response.json()
        session_cookies = {cookie.name: cookie.value for cookie in client.cookies.jar}
    if payload.get("code") != 0:
        print(f"生成二维码失败：{payload}", file=sys.stderr)
        return 1

    data = payload.get("data") or {}
    url = str(data.get("url") or "")
    key = str(data.get("qrcode_key") or "")
    if not url or not key:
        print(f"二维码响应异常：{payload}", file=sys.stderr)
        return 1

    QR_PENDING_PATH.write_text(
        json.dumps(
            {
                "url": url,
                "qrcode_key": key,
                "cookies": session_cookies,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n请用手机 B 站 App 扫码登录：\n")
    render_qr(url)
    print(f"\n二维码图片：{QR_PNG_PATH}")
    print(f"二维码链接：{url}")
    print("\n扫码后运行：bili-transcript login --poll")
    return 0


def collect_bili_cookies(client: httpx.AsyncClient, responses: list[httpx.Response]) -> dict[str, str]:
    """Collect cookies, preferring values scoped to .bilibili.com."""
    candidates: dict[str, tuple[int, str]] = {}

    def offer(name: str, value: str, domain: str) -> None:
        if not name or not value:
            return
        domain = (domain or "").lstrip(".").lower()
        if domain == "bilibili.com" or domain.endswith(".bilibili.com"):
            score = 3
        elif domain.endswith("bilibili.com"):
            score = 2
        else:
            score = 0
        current = candidates.get(name)
        if current is None or score >= current[0]:
            candidates[name] = (score, value)

    for cookie in client.cookies.jar:
        offer(cookie.name, cookie.value, cookie.domain)

    for response in responses:
        for header in response.headers.get_list("set-cookie"):
            parsed = SimpleCookie()
            try:
                parsed.load(header)
            except Exception:
                continue
            for name, morsel in parsed.items():
                offer(name, morsel.value, morsel["domain"] or urlparse(str(response.url)).hostname or "")

    return {name: value for name, (_, value) in candidates.items()}


async def poll_qr(timeout: int = 180) -> int:
    ensure_dirs()
    if not QR_PENDING_PATH.exists():
        print("没有待处理的二维码，请先运行：bili-transcript login --qr-only", file=sys.stderr)
        return 2

    pending = json.loads(QR_PENDING_PATH.read_text(encoding="utf-8"))
    key = str(pending.get("qrcode_key") or "")
    if not key:
        print("二维码记录损坏，请重新生成。", file=sys.stderr)
        return 2

    print("等待扫码...", flush=True)
    deadline = time.monotonic() + timeout
    last_state = None
    async with httpx.AsyncClient(headers=BASE_HEADERS, timeout=15, follow_redirects=True) as client:
        for name, value in (pending.get("cookies") or {}).items():
            try:
                client.cookies.set(name, value, domain=".bilibili.com")
            except Exception:
                pass
        while time.monotonic() < deadline:
            response = await client.get(
                POLL_URL,
                params={"qrcode_key": key, "source": "main-fe-header"},
                headers={"Referer": "https://passport.bilibili.com/"},
            )
            payload = response.json()
            data = payload.get("data") or {}
            state = data.get("code")

            if state != last_state:
                label = {86101: "等待扫码", 86090: "已扫码，请在手机上确认", 86038: "二维码已过期"}.get(
                    state, "登录成功" if state == 0 else str(state)
                )
                print(f"状态：{label}", flush=True)
                last_state = state

            if state == 0:
                cookie_url = str(data.get("url") or "")
                responses: list[httpx.Response] = [response]
                if cookie_url:
                    try:
                        cross = await client.get(
                            cookie_url,
                            headers={"Referer": "https://passport.bilibili.com/"},
                        )
                        responses.extend(cross.history)
                        responses.append(cross)
                    except Exception as exc:
                        print(f"跨域登录跳转失败：{exc}", file=sys.stderr)

                cookies = collect_bili_cookies(client, responses)
                parsed = parse_qs(urlparse(cookie_url).query)
                for name in ("SESSDATA", "bili_jct", "DedeUserID"):
                    value = (parsed.get(name) or [""])[0]
                    if value:
                        cookies.setdefault(name, value)
                normalized = {name.lower(): value for name, value in cookies.items()}
                sessdata = normalized.get("sessdata", "")
                bili_jct = normalized.get("bili_jct", "")
                dedeuserid = normalized.get("dedeuserid", "")

                if not sessdata:
                    domains = sorted({cookie.domain for cookie in client.cookies.jar})
                    print(
                        f"登录成功，但没有取到 .bilibili.com 的 SESSDATA。"
                        f"已捕获的 Cookie 域：{domains}",
                        file=sys.stderr,
                    )
                    print(f"登录响应 URL：{cookie_url}", file=sys.stderr)
                    return 1

                buvid3, buvid4 = await fetch_buvid()
                data_to_save = {
                    "sessdata": sessdata,
                    "bili_jct": bili_jct,
                    "buvid3": normalized.get("buvid3") or buvid3,
                    "buvid4": normalized.get("buvid4") or buvid4,
                    "dedeuserid": dedeuserid,
                    "ac_time_value": str(data.get("refresh_token") or ""),
                }
                save_credentials(data_to_save)
                QR_PENDING_PATH.unlink(missing_ok=True)

                ok, nav = await nav_status(to_credential(data_to_save))
                if ok:
                    print(f"\n登录成功：{nav.get('uname')}（UID {nav.get('mid')}）")
                    print("凭证已保存到 config/credentials.json")
                    return 0
                print("扫码完成，但登录态校验失败；请重试或检查网络。", file=sys.stderr)
                return 1

            if state == 86038:
                QR_PENDING_PATH.unlink(missing_ok=True)
                print("二维码已过期，请重新运行 login --qr-only。", file=sys.stderr)
                return 2

            await asyncio.sleep(2)

    print("等待超时，请重新生成二维码。", file=sys.stderr)
    return 2


def parse_cookie_string(raw: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in raw.replace("\n", ";").split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name and value:
            cookies[name] = value
    return cookies


async def cookie_login(raw: str) -> int:
    """Fallback for users who already exported a SESSDATA cookie string."""
    ensure_dirs()
    cookies = parse_cookie_string(raw)
    normalized = {name.lower(): value for name, value in cookies.items()}
    sessdata = normalized.get("sessdata", "")
    if not sessdata:
        print("Cookie 字符串里没有 SESSDATA。", file=sys.stderr)
        return 1

    buvid3, buvid4 = await fetch_buvid()
    data_to_save = {
        "sessdata": sessdata,
        "bili_jct": cookies.get("bili_jct") or normalized.get("bili_jct", ""),
        "buvid3": cookies.get("buvid3") or buvid3,
        "buvid4": cookies.get("buvid4") or buvid4,
        "dedeuserid": cookies.get("DedeUserID") or normalized.get("dedeuserid", ""),
        "ac_time_value": cookies.get("ac_time_value") or "",
    }
    ok, nav = await nav_status(to_credential(data_to_save))
    if not ok:
        print("Cookie 校验失败，可能已过期或复制不完整。", file=sys.stderr)
        return 1
    save_credentials(data_to_save)
    print(f"登录成功：{nav.get('uname')}（UID {nav.get('mid')}）")
    print("凭证已保存到 config/credentials.json")
    return 0


async def qr_login(force: bool = False) -> int:
    ensure_dirs()
    if not force:
        existing = load_credentials()
        if existing:
            ok, data = await nav_status(to_credential(existing))
            if ok:
                print(f"当前已登录：{data.get('uname')}（UID {data.get('mid')}）")
                print("如需切换账号，运行：bili-transcript login --force")
                return 0
            print("本地 Cookie 已失效，重新扫码登录。", file=sys.stderr)

    code = await request_qr()
    if code != 0:
        return code
    return await poll_qr()
