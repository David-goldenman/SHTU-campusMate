"""Fixed-host IMAP access for the school mailbox.

The school documents ``imap.shanghaitech.edu.cn`` with SSL on port 993 (or
plain IMAP on 143).  Accounts are expected to use a client-specific password
generated in Coremail rather than the account password.
"""
import imaplib
import ssl

from .protocols import LoginRequired

IMAP_HOST = "imap.shanghaitech.edu.cn"
DEFAULT_PORT = 993
TIMEOUT = 20


def checked_port(value) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise ValueError("IMAP 端口需要是整数。") from None
    if not 1 <= port <= 65535:
        raise ValueError("IMAP 端口需要在 1 到 65535 之间。")
    return port


def checked_settings(port=None, secure=True) -> dict:
    return {"host": IMAP_HOST, "port": checked_port(DEFAULT_PORT if port in (None, "") else port), "ssl": bool(secure)}


def connect(username: str, password: str, port=None, secure=True, *, readonly=True) -> imaplib.IMAP4:
    """Return a logged-in mailbox with INBOX selected.

    ``BODY.PEEK`` is used by callers so reading mail never marks it as seen.
    Errors are normalized to avoid returning server text or credentials.
    """
    settings = checked_settings(port, secure)
    if not isinstance(username, str) or not username.strip():
        raise ValueError("请填写学校邮箱账号。")
    if not isinstance(password, str) or not password:
        raise ValueError("请填写客户端专用密码。")
    try:
        if settings["ssl"]:
            mailbox = imaplib.IMAP4_SSL(settings["host"], settings["port"],
                                       ssl_context=ssl.create_default_context(), timeout=TIMEOUT)
        else:
            mailbox = imaplib.IMAP4(settings["host"], settings["port"], timeout=TIMEOUT)
    except (OSError, ssl.SSLError, imaplib.IMAP4.error):
        raise LoginRequired("无法连接学校 IMAP 服务，请检查网络、VPN、端口和 SSL 设置。") from None
    try:
        mailbox.login(username.strip(), password)
    except imaplib.IMAP4.error:
        try:
            mailbox.logout()
        except (OSError, imaplib.IMAP4.error):
            pass
        raise LoginRequired("IMAP 登录未通过，请核对邮箱账号与客户端专用密码。") from None
    except (OSError, ssl.SSLError):
        try:
            mailbox.logout()
        except (OSError, imaplib.IMAP4.error):
            pass
        raise LoginRequired("IMAP 登录连接中断，请稍后重试。") from None
    try:
        status, data = mailbox.select("INBOX", readonly=readonly)
        if status != "OK":
            raise imaplib.IMAP4.error("INBOX unavailable")
    except (OSError, ssl.SSLError, imaplib.IMAP4.error):
        try:
            mailbox.logout()
        except (OSError, imaplib.IMAP4.error):
            pass
        raise LoginRequired("IMAP 已登录，但无法读取收件箱。") from None
    return mailbox


def verify(username: str, password: str, port=None, secure=True) -> None:
    mailbox = connect(username, password, port, secure)
    try:
        mailbox.logout()
    except (OSError, imaplib.IMAP4.error):
        pass
