"""Bounded, versioned workspace appearance; independent of port settings."""
import copy
import json
import math
import re

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import PublicError

MAX_BYTES = 64 * 1024
MAX_DEPTH = 8
MAX_NODES = 4096
SAFE_INTEGER = 2**53 - 1
IDENTIFIER = re.compile(r"[a-z][a-z0-9-]{0,47}\Z")
FORBIDDEN = {"__proto__", "prototype", "constructor"}
FIELDS = {"theme", "companions", "reduceMotion", "options"}
DEFAULT = {"theme": "default", "companions": {}, "reduceMotion": False, "options": {}}


def bounded_json(value):
    remaining = MAX_NODES

    def visit(item, depth):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > MAX_DEPTH:
            raise ValueError("外观配置的层级或项目数过多。")
        if isinstance(item, dict):
            if len(item) > 128:
                raise ValueError("外观配置对象项目过多。")
            for key, child in item.items():
                if not isinstance(key, str) or not key or len(key) > 128 or key in FORBIDDEN:
                    raise ValueError("外观配置包含不允许的字段名。")
                visit(child, depth + 1)
        elif isinstance(item, list):
            if len(item) > 128:
                raise ValueError("外观配置列表过长。")
            for child in item:
                visit(child, depth + 1)
        elif isinstance(item, str):
            if len(item) > 8192:
                raise ValueError("外观配置文字过长。")
        elif item is None or isinstance(item, bool):
            return
        elif isinstance(item, (int, float)):
            if abs(item) > SAFE_INTEGER or not math.isfinite(item):
                raise ValueError("外观配置数字超出范围。")
        else:
            raise ValueError("外观配置必须是 JSON 数据。")

    visit(value, 0)
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError) as error:
        raise ValueError("外观配置不是有效 JSON。") from error
    if len(encoded) > MAX_BYTES:
        raise ValueError("外观配置超过 64 KiB。")
    return value


def validate_patch(value):
    bounded_json(value)
    if not isinstance(value, dict) or set(value) - FIELDS:
        raise ValueError("外观配置只能修改 theme、companions、reduceMotion 和 options。")
    if "theme" in value and (not isinstance(value["theme"], str) or not IDENTIFIER.fullmatch(value["theme"])):
        raise ValueError("主题 ID 格式不正确。")
    if "reduceMotion" in value and not isinstance(value["reduceMotion"], bool):
        raise ValueError("减少动态效果必须是布尔值。")
    if "companions" in value:
        companions = value["companions"]
        if not isinstance(companions, dict) or any(
            not IDENTIFIER.fullmatch(key) or not isinstance(choice, str) or not IDENTIFIER.fullmatch(choice)
            for key, choice in companions.items()
        ):
            raise ValueError("人物配置需要有效的主题 ID 和选项 ID。")
    if "options" in value:
        options = value["options"]
        if not isinstance(options, dict) or any(not IDENTIFIER.fullmatch(key) or not isinstance(prefs, dict) for key, prefs in options.items()):
            raise ValueError("主题偏好需要以主题 ID 分区的 JSON 对象。")
    return value


def merge(current, patch):
    result = copy.deepcopy(current)
    for key, value in patch.items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else copy.deepcopy(value)
    return result


class AppearanceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0, le=SAFE_INTEGER, strict=True)
    patch: dict

    @field_validator("patch")
    @classmethod
    def checked_patch(cls, value):
        return validate_patch(value)


def read_appearance(store):
    record = store.read("appearance")
    if record is None:
        return {"revision": 0, "resetRevision": 0, "value": None}
    try:
        if not isinstance(record, dict) or set(record) not in ({"revision", "value"}, {"revision", "resetRevision", "value"}):
            raise ValueError("Invalid saved appearance")
        record = {"resetRevision": 0, **record}
        if (type(record["revision"]) is not int or not 1 <= record["revision"] <= SAFE_INTEGER
                or type(record["resetRevision"]) is not int or not 0 <= record["resetRevision"] <= record["revision"]
                or not isinstance(record["value"], dict) or set(record["value"]) != FIELDS):
            raise ValueError("Invalid saved appearance")
        validate_patch(record["value"])
    except ValueError as error:
        raise PublicError("本地外观配置无法读取，请保留数据并联系维护者。") from error
    return record


def patch_appearance(store, update):
    # SQLite serializes writers from separate Store connections/processes as well.
    with store.lock:
        store.db.execute("BEGIN IMMEDIATE")
        try:
            record = read_appearance(store)
            if record["revision"] != update.revision:
                raise HTTPException(409, "外观设置已由其他页面更新，请重新读取后重试。")
            if record["revision"] >= SAFE_INTEGER:
                raise HTTPException(409, "外观设置版本已达上限，请联系维护者。")
            value = merge(record["value"] or DEFAULT, update.patch)
            try:
                validate_patch(value)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            result = {"revision": record["revision"] + 1, "resetRevision": record["resetRevision"], "value": value}
            store.db.execute("INSERT OR REPLACE INTO state VALUES (?, ?, ?)",
                             (store.namespace, "appearance", json.dumps(result, ensure_ascii=False, allow_nan=False)))
            store.db.commit()
            return result
        except Exception:
            store.db.rollback()
            raise


def reset_core(store):
    """Reset all core data while keeping appearance revisions monotonic."""
    with store.lock:
        store.db.execute("BEGIN IMMEDIATE")
        try:
            record = read_appearance(store)
            if record["revision"] >= SAFE_INTEGER:
                raise HTTPException(409, "外观设置版本已达上限，请联系维护者。")
            revision = record["revision"] + 1
            result = {"revision": revision, "resetRevision": revision, "value": copy.deepcopy(DEFAULT)}
            store.db.execute("DELETE FROM state WHERE namespace=?", (store.namespace,))
            store.db.execute("INSERT INTO state VALUES (?, ?, ?)",
                             (store.namespace, "appearance", json.dumps(result, ensure_ascii=False)))
            store.db.commit()
            return result
        except Exception:
            store.db.rollback()
            raise
