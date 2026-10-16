"""Only explicit platform terms identify the teaching semester, never activity."""
import re

from .source import identifier

SEASONS = {"spring": "spring", "summer": "summer", "fall": "fall", "autumn": "fall", "winter": "winter"}


def school_reference(semester):
    if not semester:
        return None
    # ELRC's school-confirmed teaching term is supplied through its public catalog API.
    name = semester["name"].strip()
    matched = re.fullmatch(r"(20\d{2})-(20\d{2})学年(春|夏|秋)季", name)
    if not matched or int(matched[2]) != int(matched[1]) + 1:
        return None
    season = {"春": "spring", "夏": "summer", "秋": "fall"}[matched[3]]
    year = int(matched[1] if season == "fall" else matched[2])
    if not semester["id"].startswith(f"{matched[1]}-{matched[2]}-"):
        return None
    return {"id": semester["id"], "name": name, "year": year, "season": season, "source": "elrc"}


def piazza_term(value):
    matched = re.fullmatch(r"(Spring|Summer|Fall|Autumn|Winter)\s+(20\d{2})", str(value).strip(), re.IGNORECASE)
    if not matched:
        return None
    return int(matched[2]), SEASONS[matched[1].lower()]


def course_catalog(payload, reference):
    if not isinstance(payload, dict) or not isinstance(payload.get("networks"), list):
        raise RuntimeError("Piazza 未返回可识别的已加入课程列表，原有列表已保留。")
    if len(payload["networks"]) > 500:
        raise RuntimeError("Piazza 课程数量超过本次读取上限，原有列表已保留。")
    courses, seen = [], set()
    for row in payload["networks"]:
        if not isinstance(row, dict):
            raise RuntimeError("Piazza 课程记录格式已变化，原有列表已保留。")
        cid = identifier(row.get("id") or "")
        if cid in seen:
            continue
        seen.add(cid)
        term = str(row.get("term") or "").strip()
        parsed = piazza_term(term)
        state = "unknown" if not parsed or not reference else (
            "current" if parsed == (reference["year"], reference["season"]) else "other"
        )
        courses.append({
            "id": cid, "name": str(row.get("name") or row.get("course_number") or cid)[:200],
            "code": str(row.get("course_number") or "")[:100], "term": term[:100],
            "school": str(row.get("school") or "")[:200],
            "platform_status": str(row.get("status") or "")[:40],
            "semester_state": state,
            "semester_reason": "平台学期与学校当前学期一致" if state == "current" else
                               "平台学期与学校当前学期不同" if state == "other" else
                               "缺少学校当前学期或平台学期无法识别",
        })
    order = {"current": 0, "unknown": 1, "other": 2}
    courses.sort(key=lambda item: (order[item["semester_state"]], item["code"], item["name"], item["id"]))
    return courses
