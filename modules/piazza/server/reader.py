import secrets
from urllib.parse import urlencode

from fastapi import HTTPException

from backend.services.auth import LoginRequired
from backend.services.campus import SourceError, course, identity, plain, rows, timestamp

BASE = "https://piazza.com"


def rpc(remote, method, parameters):
    token = next((cookie.value for cookie in remote.client.cookies.jar if cookie.name == "session_id"), "")
    value = remote.json("POST", BASE + "/logic/api", params={"method": method, "aid": secrets.token_hex(8)}, json={"method": method, "params": parameters}, headers={"CSRF-Token": token})
    if not isinstance(value, dict) or "result" not in value:
        raise SourceError("Piazza 未返回预期的读取结果。")
    if value.get("error"):
        error = str(value["error"]).lower()
        if any(word in error for word in ("login", "session", "unauthor", "not logged")):
            raise LoginRequired("Piazza 会话已失效，请重新连接。")
        raise SourceError("Piazza 未能读取该课程或帖子。")
    if value["result"] is None:
        raise HTTPException(404, "Piazza 内容已移除或当前不可访问。")
    return value["result"]


def fetch(remote, previous):
    profile = rpc(remote, "user_profile.get_profile", {})
    if not isinstance(profile, dict) or "all_classes" not in profile:
        raise SourceError("Piazza 课程目录格式已变化。")
    classes = profile["all_classes"]
    classes = list(classes.values()) if isinstance(classes, dict) else classes
    result = {"courses": [], "posts": [], "issues": [], "metadata": {"feed_limit": 50, "scope": "recent_updated_per_course"}}
    for network in rows(classes):
        nid = network.get("id") or network.get("nid")
        if not isinstance(nid, (str, int)) or not str(nid):
            result["issues"].append("一门 Piazza 课程缺少标识。")
            continue
        item = course("piazza", nid, network.get("name") or network.get("num") or str(nid), network.get("num"), network.get("term"), BASE + "/class/" + str(nid), status="active")
        result["courses"].append(item)
        try:
            feed = rpc(remote, "network.get_my_feed", {"nid": str(nid), "limit": 50, "offset": 0, "sort": "updated"})
            for post in rows(feed, "feed") if isinstance(feed, dict) else rows(feed):
                pid = post.get("id") or post.get("cid")
                if not isinstance(pid, (str, int)) or not str(pid):
                    result["issues"].append("一个 Piazza 帖子缺少标识。")
                    continue
                canonical = identity("piazza", str(nid) + ":" + str(pid))
                old = next((value for value in previous.get("posts", []) if value["id"] == canonical), {})
                result["posts"].append({"id": canonical, "source": "piazza", "source_id": str(pid), "source_course_id": str(nid), "course_id": item["id"], "title": plain(post.get("subject") or post.get("title")) or "课程帖子", "body_text": old.get("body_text") or plain(post.get("content") or post.get("snippet")), "updated_at": timestamp(post.get("updated") or post.get("modified")), "url": item["url"] + "?" + urlencode({"cid": post.get("nr") or pid})})
        except HTTPException:
            result["issues"].append(item["title"] + " 的近期讨论暂时不可读，保留缓存。")
            result["posts"].extend(old for old in previous.get("posts", []) if old.get("course_id") == item["id"])
    return result


def parse_post(value, course_id, post_id):
    if not isinstance(value, dict):
        raise SourceError("Piazza 帖子格式已变化。")
    history = rows(value.get("history"))
    current = history[0] if history else value
    replies, stack = [], list(reversed(rows(value.get("children"))))
    seen = set()
    while stack:
        reply = stack.pop()
        rid = str(reply.get("id") or len(replies))
        if rid in seen:
            continue
        seen.add(rid)
        if len(seen) > 500:
            raise SourceError("Piazza 回复超过单次 500 条的读取范围。")
        versions = rows(reply.get("history"))
        replies.append({"id": rid, "text": plain((versions[0] if versions else reply).get("content"))})
        stack.extend(reversed(rows(reply.get("children"))))
    return {"title": plain(current.get("subject") or current.get("title")), "body_text": plain(current.get("content")), "replies": replies, "url": BASE + "/class/" + course_id + "?" + urlencode({"cid": value.get("nr") or post_id})}
