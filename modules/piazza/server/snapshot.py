"""Publish watched courses and already collected posts without another download."""
from backend.services.campus import course, identity, timestamp


def with_watched_courses(context, snapshot):
    catalog = context.store.read("catalog", {})
    selected = context.store.read("courses", [])
    known = {item["id"]: item for item in catalog.get("courses", [])}
    for item in selected:
        known.setdefault(item["id"], item)
    if not known:
        return snapshot
    data = snapshot["data"]
    courses = {item["id"]: item for item in data["courses"]}
    posts = {item["id"]: item for item in data["posts"]}
    for item in known.values():
        cid = identity("piazza", item["id"])
        existing = courses.get(cid, {})
        courses[cid] = course("piazza", item["id"], item["name"], item.get("code") or existing.get("code", ""), item.get("term") or existing.get("term", ""), "https://piazza.com/class/" + item["id"])
    for item in selected:
        for post in context.store.read("posts:" + item["id"], {}).values():
            key = identity("piazza", item["id"] + ":" + post["id"])
            updated = timestamp(post.get("updated_at") or post.get("created_at"))
            existing = posts.get(key)
            if existing and existing.get("updated_at") and updated and existing["updated_at"] > updated:
                continue
            posts[key] = {"id": key, "source": "piazza", "source_id": post["id"], "source_course_id": item["id"], "course_id": identity("piazza", item["id"]), "title": post["title"], "body_text": post["body"], "updated_at": updated, "url": post["url"], "read": post.get("read", False)}
    data.update(courses=list(courses.values()), posts=list(posts.values()))
    if snapshot["status"] == "not_connected":
        snapshot.pop("message", None)
    dates = [value for value in (snapshot.get("updated_at"), catalog.get("checked_at"), *(item.get("checked_at") for item in context.store.read("status", {}).values())) if value]
    return {**snapshot, "data": data, "status": "cached" if snapshot["status"] == "not_connected" else snapshot["status"], "updated_at": max(dates, default=None)}
