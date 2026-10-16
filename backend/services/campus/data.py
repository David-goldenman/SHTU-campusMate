import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

KINDS = ("courses", "assignments", "materials", "announcements", "posts", "lessons", "timetable", "messages")


def identity(source, value):
    if value is None or str(value).strip() == "":
        raise ValueError("来源记录缺少标识。")
    return source + ":" + str(value)


def digest(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:20]


def plain(value):
    return BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True)


def timestamp(value):
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            number = float(value)
            parsed = datetime.fromtimestamp(number / 1000 if number > 100000000000 else number, timezone.utc)
        else:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def semester(value):
    value = str(value or "").strip()
    numeric = re.fullmatch(r"(20\d{2})-20\d{2}-([123])", value)
    if numeric:
        return str(int(numeric[1]) + (numeric[2] != "1")) + "-" + {"1": "fall", "2": "spring", "3": "summer"}[numeric[2]]
    year = re.search(r"20\d{2}", value)
    season = re.search(r"fall|autumn|spring|summer|秋|春|夏", value, re.I)
    if not year or not season:
        return value
    name = {"fall": "fall", "autumn": "fall", "spring": "spring", "summer": "summer", "秋": "fall", "春": "spring", "夏": "summer"}[season[0].lower()]
    return str(int(year[0]) + (bool(re.search(r"20\d{2}[-–]20\d{2}", value)) and name != "fall")) + "-" + name


def course(source, value, title, code="", term="", url="", **extra):
    match = re.search(r"\b([A-Z]{2,})\s*[- ]?\s*(\d{2,}[A-Z]?)\b", str(code or "").upper())
    return {"id": identity(source, value), "source": source, "source_id": str(value), "title": plain(title) or str(value),
            "code": "".join(match.groups()) if match else str(code or ""), "term": str(term or ""), "semester": semester(term), "url": url, **extra}


def validate_bundle(bundle):
    if not isinstance(bundle, dict):
        raise ValueError("来源数据需要返回对象。")
    result = {kind: [] for kind in KINDS}
    for kind in KINDS:
        values = bundle.get(kind, [])
        if not isinstance(values, list):
            raise ValueError("来源集合需要返回数组。")
        seen = set()
        for value in values:
            if not isinstance(value, dict) or not isinstance(value.get("id"), str) or not value["id"] or not value.get("source"):
                raise ValueError("来源记录缺少合法标识。")
            if value.get("url") and urlsplit(value["url"]).scheme not in {"http", "https"}:
                raise ValueError("来源链接需要使用 HTTP 或 HTTPS。")
            if value["id"] not in seen:
                result[kind].append(value)
                seen.add(value["id"])
    result["metadata"] = bundle.get("metadata", {})
    result["issues"] = bundle.get("issues", [])
    if not isinstance(result["metadata"], dict) or not isinstance(result["issues"], list):
        raise ValueError("来源范围或诊断格式不正确。")
    return result
