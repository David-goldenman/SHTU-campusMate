"""Expose the existing lesson library through the shared campus data contract."""
from backend.services.campus import course, identity

from .catalog import ELRC
from .content import ContentLibrary


def with_library(context, snapshot):
    catalog = ELRC(context.data_dir).catalog("all")
    if not catalog["courses"]:
        return snapshot
    library = ContentLibrary(ELRC(context.data_dir))
    data = snapshot["data"]
    courses = {item["id"]: item for item in data["courses"]}
    lessons = {item["id"]: item for item in data["lessons"]}
    materials = {item["id"]: item for item in data["materials"]}
    dates = [value for value in (snapshot.get("updated_at"), catalog.get("updated_at")) if value]
    current = (catalog.get("current_semester") or {}).get("id")
    for item in catalog["courses"]:
        cid = identity("elrc", item["id"])
        terms = item.get("semester_ids", [])
        term = current if current in terms else item.get("semester_id", "")
        courses[cid] = {**courses.get(cid, {}), **course("elrc", item["id"], item["name"], item.get("code"), term, library.course_url(item["id"]))}
        cached = library.read(item["id"])
        if cached.get("updated_at"):
            dates.append(cached["updated_at"])
        for material in cached.get("materials", []):
            key = identity("elrc", item["id"] + ":" + material["id"])
            materials.setdefault(key, {"id": key, "source": "elrc", "course_id": cid, "title": material["title"], "type": material.get("kind", "content"), "path": [material["chapter"]] if material.get("chapter") else [], "url": library.course_url(item["id"])})
        for lesson in cached.get("lessons", []):
            content = library.read(item["id"], lesson["id"])
            key = identity("elrc", "lesson:" + item["id"] + ":" + lesson["id"])
            text = "\n".join(row["text"] for row in content.get("transcript", []))
            summary = "\n".join(row["text"] for row in content.get("summary", []))
            lessons[key] = {"id": key, "source": "elrc", "course_id": cid, "title": item["name"] + " · " + lesson["label"], "body_text": text, "summary_text": summary, "term": lesson.get("semester_id") or term, "url": lesson["source_url"], "updated_at": content.get("updated_at"), "stale": content.get("voice_state") == "stale"}
    data.update(courses=list(courses.values()), materials=list(materials.values()), lessons=list(lessons.values()))
    data["metadata"]["semester"] = catalog.get("current_semester") or {}
    data["metadata"]["library"] = "cached_lessons"
    if snapshot["status"] == "not_connected":
        snapshot.pop("message", None)
    return {**snapshot, "data": data, "status": "cached" if snapshot["status"] == "not_connected" else snapshot["status"], "updated_at": max(dates, default=None)}
