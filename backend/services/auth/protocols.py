import base64
import json
import re
import secrets
from http.cookiejar import Cookie, CookieJar, DefaultCookiePolicy
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/134.0.0.0 Safari/537.36"
IDS = "https://ids.shanghaitech.edu.cn/authserver"
SERVICES = {
    "blackboard": "https://elearning.shanghaitech.edu.cn:8443/",
    "elrc": "https://elrc.shanghaitech.edu.cn/unifiedlogin/v1/loginmanage/login/direction?redirect_url=https%3A%2F%2Felrc.shanghaitech.edu.cn%2Flearn%2F",
    "timetable": "https://eams.shanghaitech.edu.cn/eams/courseTableForStd!courseTable.action",
}
PROVIDERS = {
    "coremail": {"name": "学校邮箱", "url": "https://mail.shanghaitech.edu.cn/coremail/", "domains": ("mail.shanghaitech.edu.cn",)},
    "ids": {"name": "学校 IDS", "domains": ("shanghaitech.edu.cn",)},
    "gradescope": {"name": "Gradescope", "url": "https://www.gradescope.com/login", "domains": ("gradescope.com",)},
    "piazza": {"name": "Piazza", "url": "https://piazza.com/class", "domains": ("piazza.com",)},
}


class LoginRequired(RuntimeError):
    pass


class VerificationRequired(LoginRequired):
    pass


def checked_target(provider: str, target: str | None = None) -> str | None:
    if provider not in PROVIDERS:
        raise ValueError("认证提供方不存在。")
    if provider == "ids":
        target = target or "blackboard"
        if target not in SERVICES:
            raise ValueError("IDS 登录目标须为 blackboard、elrc 或 timetable。")
        return target
    if target is not None:
        raise ValueError("只有 IDS 接受登录目标。")
    return None


def browser_url(provider: str, target: str | None) -> str:
    return SERVICES[target] if provider == "ids" else PROVIDERS[provider]["url"]


def filtered_state(provider: str, state: dict) -> dict:
    domains = PROVIDERS[provider]["domains"]
    cookies = [cookie for cookie in state.get("cookies", []) if any(
        cookie["domain"].lstrip(".") == domain or cookie["domain"].lstrip(".").endswith("." + domain)
        for domain in domains
    )]
    result = {"cookies": cookies, "user_agent": state.get("user_agent", UA)}
    if provider == "coremail" and state.get("sid"):
        result["sid"] = state["sid"]
    return result


class NetworkConfigurationError(httpx.RequestError):
    """Public classification for invalid proxy or CA configuration at client startup."""


def http_client(state: dict | None = None) -> httpx.Client:
    state = state or {}
    # Campus services use local DNS and the OS route (including an active campus VPN).
    # Keep environment proxies for external providers and retain normal TLS verification.
    try:
        client = httpx.Client(headers={"User-Agent": state.get("user_agent", UA)}, follow_redirects=True, timeout=40,
                              mounts={"all://*shanghaitech.edu.cn": None})
    except (ValueError, ImportError, OSError) as error:
        raise NetworkConfigurationError("网络客户端配置无效，请检查代理与证书设置。") from error
    for cookie in state.get("cookies", []):
        expiry = cookie.get("expires")
        expiry = int(expiry) if expiry and expiry > 0 else None
        rest = {}
        if cookie.get("httpOnly"):
            rest["HttpOnly"] = None
        if cookie.get("sameSite"):
            rest["SameSite"] = cookie["sameSite"]
        domain = cookie["domain"]
        client.cookies.jar.set_cookie(Cookie(
            version=0, name=cookie["name"], value=cookie["value"], port=None, port_specified=False,
            domain=domain, domain_specified=cookie.get("domain_specified", domain.startswith(".")),
            domain_initial_dot=domain.startswith("."), path=cookie.get("path", "/"), path_specified=True,
            secure=cookie.get("secure", False), expires=expiry, discard=expiry is None,
            comment=None, comment_url=None, rest=rest,
        ))

    def cookie_header(request):
        # httpx copies CookieJars with a permissive policy; restore host-only scope before sending.
        jar = CookieJar(policy=DefaultCookiePolicy(strict_ns_domain=DefaultCookiePolicy.DomainStrictNonDomain))
        for cookie in client.cookies.jar:
            jar.set_cookie(cookie)
        request.headers.pop("cookie", None)
        httpx.Cookies(jar).set_cookie_header(request)

    client.event_hooks["request"].append(cookie_header)
    return client


def session_state(client: httpx.Client, previous: dict | None = None) -> dict:
    result = {"user_agent": client.headers.get("User-Agent", UA), "cookies": [{
        "name": c.name, "value": c.value, "domain": c.domain, "path": c.path, "expires": c.expires,
        "secure": c.secure, "domain_specified": c.domain_specified,
        "httpOnly": c.has_nonstandard_attr("HttpOnly"), "sameSite": c.get_nonstandard_attr("SameSite"),
    } for c in client.cookies.jar]}
    if previous and previous.get("sid"):
        result["sid"] = previous["sid"]
    return result


def _check_page(response: httpx.Response, host: str):
    if response.status_code in (401, 403) or urlsplit(str(response.url)).hostname != host:
        raise LoginRequired("登录会话已到期，请重新连接账号。")
    response.raise_for_status()
    if BeautifulSoup(response.text, "html.parser").select_one("#loginForm"):
        raise LoginRequired("登录会话已到期，请重新连接账号。")


def _piazza_profile(client: httpx.Client):
    token = next((c.value for c in client.cookies.jar if c.name == "session_id"), "")
    response = client.post("https://piazza.com/logic/api", params={"method": "user_profile.get_profile", "aid": secrets.token_hex(8)},
                           json={"method": "user_profile.get_profile", "params": {}}, headers={"CSRF-Token": token})
    if response.status_code in (401, 403):
        raise LoginRequired("Piazza 登录会话已到期。")
    response.raise_for_status()
    data = response.json()
    if data.get("error") or data.get("result") is None:
        raise LoginRequired("Piazza 登录会话已到期。")
    profile = data["result"]
    if isinstance(profile, dict):
        subject = profile.get("uid") or profile.get("id") or profile.get("email")
        if subject:
            return subject
    raise LoginRequired("Piazza 未返回可验证的账号标识，请重新连接。")


def _elrc_identity(client):
    response = client.get("https://elrc.shanghaitech.edu.cn/unifiedplatform/v1/user/current", follow_redirects=False)
    if response.status_code != 200:
        raise LoginRequired("虚拟教学社区未确认当前账号。")
    payload = response.json()
    user = payload.get("extendMessage") if isinstance(payload, dict) else None
    value = user.get("userCode") or user.get("user_code") if isinstance(user, dict) else None
    if not isinstance(value, (str, int)) or not str(value).strip():
        raise LoginRequired("虚拟教学社区未返回可验证的账号标识。")
    return str(value).strip()


def complete_blackboard_login(client: httpx.Client, response: httpx.Response):
    form = BeautifulSoup(response.text, "html.parser").select_one('form[action*="/webapps/bb-sso-BBLEARN/execute/authValidate/customLogin"]')
    if form is not None:
        destination = urljoin(str(response.url), form["action"])
        if (urlsplit(destination).scheme, urlsplit(destination).netloc) != ("https", "elearning.shanghaitech.edu.cn:8443"):
            raise LoginRequired("Blackboard 登录交换地址与学校域名不一致。")
        fields = {i["name"]: i.get("value", "") for i in form.select('input[type="hidden"][name]')}
        result = client.post(destination, data=fields)
        _check_page(result, "elearning.shanghaitech.edu.cn")


def validate(client: httpx.Client, provider: str, target: str | None, state: dict):
    if provider == "gradescope":
        response = client.get("https://www.gradescope.com/account")
        _check_page(response, "www.gradescope.com")
        if not BeautifulSoup(response.text, "html.parser").select_one("#account-show"):
            raise LoginRequired("Gradescope 未确认登录，请连接账号或使用浏览器验证。")
        # The signed-in account page supplies identity without settings reauthentication.
        for script in BeautifulSoup(response.text, "html.parser").select("script"):
            text = script.get_text()
            match = re.search(r"(?:^|;)\s*gon\.page_context\s*=\s*", text)
            if match:
                try:
                    profile = json.JSONDecoder().raw_decode(text[match.end():])[0]
                    identity = re.fullmatch(r"trn:user:[a-z-]+:gs::(\d+)", profile["user_trn"])
                    if identity:
                        return "user:" + identity[1]
                except (ValueError, KeyError, TypeError):
                    pass
        raise LoginRequired("Gradescope 未返回可验证的账号标识，请重新连接。")
    elif provider == "piazza":
        return _piazza_profile(client)
    elif provider == "ids":
        response = client.get(SERVICES[target])
        _check_page(response, urlsplit(SERVICES[target]).hostname)
        if target == "blackboard":
            complete_blackboard_login(client, response)
            profile = client.get("https://elearning.shanghaitech.edu.cn:8443/learn/api/public/v1/users/me")
            _check_page(profile, "elearning.shanghaitech.edu.cn")
            user = profile.json()
            if isinstance(user, dict) and user.get("userName"):
                return user["userName"]
            raise LoginRequired("Blackboard 未返回可验证的账号标识，请重新连接。")
        elif target == "elrc":
            response = client.get("https://elrc.shanghaitech.edu.cn/learn/login/info")
            _check_page(response, "elrc.shanghaitech.edu.cn")
            result = response.json()
            if result.get("message") == "unLogin" or result.get("status") in (401, "401") or not result.get("data"):
                raise LoginRequired("虚拟教学社区登录会话已到期。")
            return _elrc_identity(client)
        else:
            home = client.get("https://eams.shanghaitech.edu.cn/eams/home.action")
            _check_page(home, "eams.shanghaitech.edu.cn")
            subjects = {match[1] for node in BeautifulSoup(home.text, "html.parser").select("font")
                        if (match := re.fullmatch(r"[^()]+\(([A-Za-z0-9_-]{4,40})\)", node.get_text(strip=True)))}
            if len(subjects) != 1:
                raise LoginRequired("教务系统未返回可验证的账号标识，请重新连接。")
            return subjects.pop()
    else:
        if not state.get("sid"):
            raise VerificationRequired("请在验证窗口完成学校邮箱登录并导入会话。")
        response = client.post("https://mail.shanghaitech.edu.cn/coremail/s/json",
                               params={"sid": state["sid"], "func": "user:getAttrs"}, json={"attrIds": ["uid"]})
        if response.status_code in (401, 403):
            raise LoginRequired("学校邮箱会话已到期，请重新验证。")
        response.raise_for_status()
        result = response.json()
        if result.get("code") in {"FA_UNAUTHORIZED", "FA_INVALID_SESSION", "FA_INVALID_TEMP_SESSION", "FA_SECURITY"}:
            raise LoginRequired("学校邮箱会话已到期，请重新验证。")
        if result.get("code") != "S_OK":
            raise LoginRequired("学校邮箱未确认登录状态，请重新验证。")
        profile = result.get("var") or {}
        if isinstance(profile, dict):
            subject = profile.get("uid") or profile.get("email") or profile.get("account")
            if subject:
                return subject
        raise LoginRequired("邮箱未返回可验证的账号标识，请重新连接。")


def encrypt_ids_password(password: str, salt: str) -> str:
    alphabet = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"
    prefix = "".join(secrets.choice(alphabet) for _ in range(64))
    iv = "".join(secrets.choice(alphabet) for _ in range(16)).encode()
    padder = PKCS7(128).padder()
    padded = padder.update((prefix + password).encode()) + padder.finalize()
    encryptor = Cipher(algorithms.AES(salt.strip().encode()), modes.CBC(iv)).encryptor()
    return base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode()


def login(client: httpx.Client, provider: str, username: str, password: str, target: str | None):
    if provider == "gradescope":
        response = client.get(PROVIDERS[provider]["url"])
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        if soup.select_one("#account-show"):
            return
        form = soup.select_one('form[action="/login"]')
        if form is None:
            raise VerificationRequired("Gradescope 登录页需要浏览器验证。")
        fields = {i["name"]: i.get("value", "") for i in form.select('input[type="hidden"][name]')}
        fields.update({"session[email]": username, "session[password]": password, "session[remember_me]": "1"})
        result = client.post("https://www.gradescope.com/login", data=fields)
        if result.status_code in (400, 401, 403, 422):
            raise LoginRequired("Gradescope 未接受登录，请核对账号密码或使用验证窗口。")
        result.raise_for_status()
    elif provider == "piazza":
        response = client.get("https://piazza.com/main/csrf_token")
        response.raise_for_status()
        token = re.search(r'CSRF_TOKEN\s*=\s*["\']([^"\']+)', response.text)
        if not token:
            raise VerificationRequired("Piazza 登录页需要浏览器验证。")
        result = client.post("https://piazza.com/class", data={"email": username, "password": password, "from": "/signup", "remember": "on", "csrf_token": token[1]})
        if result.status_code in (400, 401, 403, 422):
            raise LoginRequired("Piazza 未接受登录，请核对账号密码或使用验证窗口。")
        result.raise_for_status()
    elif provider == "ids":
        response = client.get(SERVICES[target])
        response.raise_for_status()
        if urlsplit(str(response.url)).hostname != "ids.shanghaitech.edu.cn":
            if target == "blackboard":
                complete_blackboard_login(client, response)
            return
        salt = BeautifulSoup(response.text, "html.parser").select_one("#pwdEncryptSalt")
        if salt is None:
            raise VerificationRequired("IDS 要求二次验证，请在验证窗口完成。")
        captcha = client.get(IDS + "/checkNeedCaptcha.htl", params={"username": username})
        captcha.raise_for_status()
        if captcha.json().get("isNeed"):
            raise VerificationRequired("IDS 要求图形验证码，请使用浏览器验证。")
        form = salt.find_parent("form")
        fields = {i["name"]: i.get("value", "") for i in form.select('input[type="hidden"][name]')}
        fields.update({"username": username, "password": encrypt_ids_password(password, salt["value"]), "captcha": "", "_eventId": "submit", "cllt": "userNameLogin", "dllt": "generalLogin"})
        result = client.post(str(response.url), data=fields)
        if urlsplit(str(result.url)).hostname == "ids.shanghaitech.edu.cn":
            error = BeautifulSoup(result.text, "html.parser").select_one("#showErrorTip, #msg, .auth_error")
            if error and error.get_text(strip=True):
                raise LoginRequired("IDS 未接受账号密码，请核对后重试。")
            raise VerificationRequired("IDS 需要二次验证，请在验证窗口完成后导入会话。")
        result.raise_for_status()
        if target == "blackboard":
            complete_blackboard_login(client, result)
    else:
        raise VerificationRequired("学校邮箱通过验证窗口登录，支持原站的密码加密与二次验证。")
