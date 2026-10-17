"""Bounded, anonymous campus connectivity checks; never infer a user's location."""
import asyncio
import ipaddress
import socket
import ssl
import time
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from urllib.request import getproxies

import httpx

from .protocols import IDS, PROVIDERS, SERVICES, UA

TARGETS_TO_CHECK = (
    ("ids", "统一认证", IDS + "/login"),
    ("timetable", "教务系统", SERVICES["timetable"]),
    ("blackboard", "Blackboard", SERVICES["blackboard"]),
    ("elrc", "虚拟教学社区 ELRC", "https://elrc.shanghaitech.edu.cn/learn/login/info"),
    ("coremail", "学校邮箱", PROVIDERS["coremail"]["url"]),
)
VPN_GUIDE = "https://it.shanghaitech.edu.cn/2021/0424/c8423a63191/page.htm"
PROBE_TIMEOUT = 6
DNS_TIMEOUT = 3
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in
                         ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7"))


def address_kind(address):
    value = ipaddress.ip_address(address)
    if value.version == 4 and value in ipaddress.ip_network("198.18.0.0/15"):
        return "synthetic"
    if any(value.version == network.version and value in network for network in PRIVATE_NETWORKS):
        return "private"
    if value.is_global:
        return "public"
    return "special"


async def resolve(host, port):
    try:
        entries = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(
            host, port, type=socket.SOCK_STREAM), timeout=DNS_TIMEOUT)
        addresses = sorted({entry[4][0] for entry in entries})[:8]
        return {"status": "ok" if addresses else "dns_error", "addresses": addresses,
                "kinds": sorted({address_kind(address) for address in addresses})}
    except TimeoutError:
        return {"status": "dns_timeout", "addresses": [], "kinds": []}
    except OSError:
        return {"status": "dns_error", "addresses": [], "kinds": []}


def error_kind(error):
    chain, seen = [], set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        chain.append(error)
        error = error.__cause__ or error.__context__
    if any(isinstance(item, socket.gaierror) for item in chain):
        return "dns_error"
    if any(isinstance(item, ssl.SSLError) or "CERTIFICATE_VERIFY_FAILED" in str(item)
           or "TLS" in str(item) or "SSL" in str(item) for item in chain):
        return "tls_error"
    if any(isinstance(item, (httpx.TimeoutException, TimeoutError)) for item in chain):
        return "timeout"
    if any(isinstance(item, httpx.ProxyError) for item in chain):
        return "proxy_error"
    if any(isinstance(item, httpx.ProtocolError) for item in chain):
        return "protocol_error"
    return "connection_error"


def probe_client(proxy=None):
    try:
        # Explicit transport bypasses proxy discovery but keeps configured CA trust.
        transport = httpx.AsyncHTTPTransport(proxy=proxy, trust_env=True, retries=0)
        return httpx.AsyncClient(transport=transport, trust_env=False, timeout=4, follow_redirects=False)
    except (ValueError, ImportError, OSError):
        return None


async def probe(url, client):
    started = time.monotonic()
    if client is None:
        return {"status": "configuration_error", "reachable": False, "elapsed_ms": 0}
    try:
        async with asyncio.timeout(PROBE_TIMEOUT):
            # A fresh Request does not inherit even anonymous cookies from another probe.
            response = await client.send(httpx.Request("GET", url, headers={"User-Agent": UA}), stream=True)
            try:
                code = response.status_code
                status = ("login_required" if code == 401 else "access_denied" if code == 403
                          else "service_error" if code >= 500 else "http_error" if code >= 400
                          else "reachable")
                result = {"status": status, "reachable": True, "http_status": code}
            finally:
                await response.aclose()
    except (httpx.HTTPError, TimeoutError) as error:
        result = {"status": error_kind(error), "reachable": False}
    except (ValueError, ImportError, OSError):
        result = {"status": "configuration_error", "reachable": False}
    return {**result, "elapsed_ms": round((time.monotonic() - started) * 1000)}


def diagnosis(dns, direct, proxy):
    state = direct["status"]
    if direct["reachable"]:
        if proxy and proxy["status"] == "configuration_error":
            return {"code": "proxy_configuration", "confidence": "confirmed", "title": "校园入口可达，代理配置需要修正",
                    "message": "匿名直连已收到响应，但代理客户端无法初始化；这类配置也可能阻止同步客户端启动。",
                    "actions": ["修正本机代理配置的协议、地址和端口，重启工作台后重新检测与同步。"]}
        if state in {"service_error", "http_error"}:
            return {"code": "service", "confidence": "confirmed", "title": "网络已连通，服务响应异常",
                    "message": f"已收到 HTTP {direct['http_status']}，问题发生在服务响应阶段。",
                    "actions": ["稍后重试；若持续出现，请把检测时间和状态码提供给学校服务支持。"]}
        if state == "access_denied":
            return {"code": "access", "confidence": "confirmed", "title": "网络已连通，访问被拒绝",
                    "message": "服务返回 HTTP 403，可能需要登录或受访问策略限制。",
                    "actions": ["先在账号连接中完成学校登录；仍被拒绝时联系学校服务支持。"]}
        if proxy and not proxy["reachable"]:
            return {"code": "proxy", "confidence": "confirmed", "title": "校园服务可达，代理路径失败",
                    "message": "同一入口直连成功，通过已配置代理的对照请求失败；工作台已绕过该代理。",
                    "actions": (["匿名检测返回 HTTP 401；若尚未连接账号，请先完成登录，再同步。"] if state == "login_required" else [])
                               + ["其他浏览器若仍失败，将 shanghaitech.edu.cn 及其子域名设为直连；工作台可通过直连访问。"]}
        return {"code": "reachable", "confidence": "confirmed", "title": "校园服务可达",
                "message": "已收到服务响应；此检测不代表账号已登录或所有资料接口都可用。",
                "actions": ["需要登录时，前往账号连接完成验证，再重新同步。"] if state == "login_required" else []}
    # An actual request's configuration/TLS error is stronger evidence than a
    # separate DNS probe that may have timed out or observed different results.
    if state == "configuration_error":
        return {"code": "configuration", "confidence": "confirmed", "title": "网络客户端配置异常",
                "message": "检测连接未能初始化，可能是本机证书文件或代理配置无效。",
                "actions": ["检查本机代理与证书环境配置，修正后重启工作台再检测。"]}
    if state == "tls_error":
        return {"code": "tls", "confidence": "confirmed", "title": "安全连接握手失败",
                "message": "实际请求发生 HTTPS 握手或证书验证失败；不能据此判断 VPN 未连接。",
                "actions": ["核对系统日期时间；检查代理 HTTPS 检查、证书配置或 TUN 干扰。",
                            "保持证书校验开启；若官方网页也失败，请联系学校服务支持。"]}
    if "synthetic" in dns["kinds"]:
        return {"code": "dns_proxy", "confidence": "suspected", "title": "疑似代理 DNS 或 TUN 冲突",
                "message": "域名解析到常见 Fake-IP 使用的保留地址段，且直连失败；仅凭地址不能确定是哪款代理。",
                "actions": ["将校园域名设为直连并排除 Fake-IP，让其使用系统或校园 DNS。",
                            "若使用 TUN，按校园 VPN 实际下发的网段设置排除后重新检测。"]}
    if dns["status"] != "ok" or state == "dns_error":
        return {"code": "dns", "confidence": "confirmed", "title": "DNS 解析失败或超时",
                "message": "系统未能及时解析校园域名。可能与当前 DNS、网络或 VPN 的 DNS 配置有关。",
                "actions": ["确认网络已连接；校外先连接学校 VPN，再重新检测。",
                            "已连接 VPN 时，检查校园域名是否仍被代理 DNS / Fake-IP 接管，改用系统或校园 DNS。"]}
    if proxy and proxy["reachable"]:
        return {"code": "direct_route", "confidence": "suspected", "title": "直连路径不可用，代理路径可达",
                "message": "同一入口通过代理收到响应，但系统直连失败；需要检查直连使用的 DNS 和校园路由。",
                "actions": ["校外请连接官方校园 VPN；已连接时重新连接 VPN 后检测。",
                            "检查 TUN 是否覆盖了校园 VPN 的路由，并确认校园域名使用系统或校园 DNS。"]}
    if "private" in dns["kinds"]:
        return {"code": "campus_route", "confidence": "suspected", "title": "疑似校园网络或 VPN 路径问题",
                "message": "域名含校园内网地址，但未收到服务响应；无法据此确认你在校外或 VPN 未连接。",
                "actions": ["校外先连接官方校园 VPN；校内确认校园网认证已完成。",
                            "若已连接 VPN，重新连接并检查 TUN 路由冲突；仅一个服务失败时，也可能是该服务故障。"]}
    return {"code": "connection", "confidence": "unknown", "title": "暂时无法连接校园服务",
            "message": "DNS 已解析，但连接失败或超时；现有证据无法区分本地网络、路由与服务故障。",
            "actions": ["确认网络可用，校外连接校园 VPN；若只影响一个服务，稍后重试或联系该服务支持。"]}


async def check_target(target, direct_client, proxy_client, compare):
    key, name, url = target
    parsed = httpx.URL(url)
    tasks = [resolve(parsed.host, parsed.port or 443), probe(url, direct_client)]
    if compare:
        tasks.append(probe(url, proxy_client))
    values = await asyncio.gather(*tasks)
    dns, direct, comparison = values[0], values[1], values[2] if compare else None
    return {"id": key, "name": name, "host": parsed.host, "port": parsed.port or 443,
            "dns": dns, "direct": direct, "proxy": comparison,
            "diagnosis": diagnosis(dns, direct, comparison)}


class NetworkDiagnostics:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.result = None
        self.completed = 0.0

    def snapshot(self):
        return self.result or {"checked_at": None, "services": []}

    async def check(self):
        # Coalesce simultaneous checks, and prevent repeated clicks flooding school services.
        async with self.lock:
            if self.result and time.monotonic() - self.completed < 5:
                return self.result
            proxies = getproxies()
            proxy_url = proxies.get("https") or proxies.get("all")
            # Loading CA certificates is blocking on Windows. Do it once per path, before
            # starting DNS/network deadlines, outside the event loop.
            direct_client, comparison_client = await asyncio.gather(
                asyncio.to_thread(probe_client), asyncio.to_thread(probe_client, proxy_url) if proxy_url
                else asyncio.sleep(0, result=None))
            async with AsyncExitStack() as clients:
                for client in (direct_client, comparison_client):
                    if client is not None:
                        await clients.enter_async_context(client)
                services = await asyncio.gather(*(check_target(target, direct_client, comparison_client, bool(proxy_url))
                                                  for target in TARGETS_TO_CHECK))
            count = sum(item["direct"]["reachable"] for item in services)
            self.result = {"checked_at": datetime.now(timezone.utc).isoformat(), "services": services,
                           "reachable_count": count, "total": len(services),
                           "proxy_configured": bool(proxy_url), "campus_location": "unknown", "vpn_status": "unknown",
                           "vpn_guide": VPN_GUIDE,
                           "summary": f"{count} / {len(services)} 个校园服务入口收到响应",
                           "scope": "仅检测服务入口，不读取账号或资料；不判断物理位置，也不证明 VPN 已连接。"}
            self.completed = time.monotonic()
            return self.result
