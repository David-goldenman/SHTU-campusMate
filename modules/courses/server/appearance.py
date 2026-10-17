"""Course-owned department palette, using source evidence before plan metadata."""
import re

PALETTE = (
    ("sem", "创管学院", ("创业与管理学院", "创管学院", "SEM"), "#80649A", "#F0EBF5", "#59406F"),
    ("sca", "创艺学院", ("创意与艺术学院", "创艺学院", "SCA"), "#C96046", "#FAEBE6", "#8C3D2A"),
    ("slst", "生命学院", ("生命科学与技术学院", "生命学院", "SLST"), "#A58134", "#F4EEDC", "#70551E"),
    ("spst", "物质学院", ("物质科学与技术学院", "物质学院", "SPST"), "#548768", "#E7F0E9", "#345C43"),
    ("ims", "数学所", ("数学科学研究所", "数学所", "IMS"), "#344F78", "#E8EDF5", "#263D60"),
    ("sist", "信息学院", ("信息科学与技术学院", "信息学院", "SIST"), "#83B5D2", "#E9F3F8", "#345F79"),
    ("college", "体育与书院", (), "#BF616A", "#F7E9EB", "#843F46"),
)
DEFAULT = {"key": "general", "label": "其他院系", "accent": "#8994A6", "tint": "#EFF1F5", "ink": "#4C566A"}


def colors(row, label=None):
    key, title, _, accent, tint, ink = row
    return {"key": key, "label": label or title, "accent": accent, "tint": tint, "ink": ink}


def code(value):
    return re.sub(r"[\s_-]", "", str(value or "")).upper()


def decorate(courses, plan):
    departments = {}
    for group in plan.get("groups", []):
        for item in group.get("courses", []):
            name = str(item.get("department") or "").strip()
            if name and item.get("code"):
                departments.setdefault(code(item["code"]), set()).add(name)
    for item in courses:
        observed = {str(source.get("department") or "").strip() for source in item.get("sources", []) if source.get("department")}
        matched = observed or departments.get(code(item.get("code")), set())
        department = next(iter(matched)) if len(matched) == 1 else ""
        sport = bool(re.match(r"^(?:PE|CLPE)\d", code(item.get("code"))))
        appearance = {**DEFAULT, "label": department or "院系待确认"}
        if sport or department.endswith("书院"):
            appearance = colors(PALETTE[-1], "体育课程" if sport else department)
            if sport:
                appearance["icon"] = "person-running"
        else:
            for row in PALETTE:
                if department in row[2]:
                    appearance = colors(row)
                    break
        item.update(department=department, appearance=appearance,
                    department_source="course" if observed and department else "study_plan" if department else "unknown")
    return courses
