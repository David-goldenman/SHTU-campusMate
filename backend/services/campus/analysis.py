"""Shared account epochs and citation validation; no module selection or business rules."""
from .data import digest
from .remote import SourceError

PROVIDERS = ("ids", "coremail", "gradescope", "piazza")


def account_revision(context):
    return digest([context.auth.get_status(provider)["account_revision"] for provider in PROVIDERS])


def citations(ids, context):
    if not isinstance(ids, list) or any(not isinstance(value, str) for value in ids):
        raise SourceError("AI 返回的引用格式不正确。")
    known = {item["id"]: item for item in context["items"]}
    if any(identity not in known for identity in ids):
        raise SourceError("AI 引用了当前资料范围以外的条目，请重试。")
    return [{"id": identity, "title": known[identity].get("title", "来源"), "source": known[identity]["source"], "url": known[identity].get("url", "")} for identity in dict.fromkeys(ids)]
