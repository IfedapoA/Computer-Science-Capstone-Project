"""OPTIONAL demo data for trying the program (fictional people). Safe to run twice; never touches existing students.
    python seed_demo.py
Real use: skip this, start the program and press 'Create advisor account...'."""
import db
import migrate

ADVISOR = ("Jane", "Doe", "advisor@example.edu")


def _prog(code):
    return next(p["id"] for p in db.all_programs() if p["code"] == code)


def seed() -> dict:
    migrate.run()
    if not db.find_advisor(ADVISOR[2]):
        db.add_advisor(*ADVISOR)
    adv = db.find_advisor(ADVISOR[2])["advisor_id"]
    years = {y["label"]: y["id"] for y in db.catalog_years()}
    existing = {s["email_address"] for s in db.list_students()}
    # an outside-the-department program (Political Science minor) to show requirement #5
    if "POLS-M" not in {p["code"] for p in db.all_programs()}:
        for code, title in (("PSCI 100", None), ("PSCI 210", "Comparative Politics"), ("PSCI 220", "International Relations"), ("PSCI 330", "Political Theory")):
            if not db.get_course(code):
                db.ensure_course(code, title or "Introduction to Political Science", 3)
        pid = db.save_program("POLS-M", "Political Science Minor", "Minor", 18, "Political Science", True)
        cy = years["2026-2027"]
        for code, t in (("PSCI 100", "Core"), ("PSCI 210", "Core"), ("PSCI 220", "Core"), ("PSCI 330", "Elective")):
            db.add_requirement(cy, pid, code, t)
        db.set_electives_needed(cy, pid, 1)
        db.copy_requirements_to_all_years(pid, cy)
    people = [
        ("Ada", "Lovelace-Sample", "ada@example.edu", "2025-2026", ["CS"], [
            ("CMSCI 120", "Fall", 2025, "Completed", "A"), ("CMSCI 125", "Spring", 2026, "Completed", "A-"),
            ("MATH 247", "Spring", 2026, "Completed", "B+"), ("MATH 228", "Fall", 2025, "Completed", "A"),
            ("FSYM 101", "Fall", 2025, "Completed", "A"), ("WCIV 102", "Spring", 2026, "Completed", "B"),
            ("PHIL 103", "Spring", 2026, "Completed", "B+"), ("CMSCI 254", "Fall", 2026, "In Progress", None),
            ("CMSCI 277", "Fall", 2026, "In Progress", None)]),
        ("Ben", "Byte", "ben@example.edu", "2024-2025", ["Cyber", "CS"], [
            ("CMSCI 120", "Fall", 2024, "Completed", "B"), ("CMSCI 125", "Spring", 2025, "Completed", "B+"), ("MATH 228", "Spring", 2025, "Completed", "B"),
            ("MATH 247", "Fall", 2025, "Completed", "C+"), ("CMSCI 254", "Fall", 2025, "Completed", "B"), ("CYBER 100", "Spring", 2025, "Completed", "A"),
            ("CYBER 260", "Spring", 2026, "Completed", "B+"), ("CYBER 261", "Fall", 2025, "Completed", "A-"), ("CMSCI 355", "Fall", 2025, "Completed", "B"),
            ("CMSCI 358", "Fall", 2026, "In Progress", None), ("CYBER 301", "Fall", 2026, "In Progress", None)]),
        ("Pia", "Politics", "pia@example.edu", "2026-2027", ["Data", "POLS-M"], [
            ("CMSCI 120", "Fall", 2026, "In Progress", None), ("DATA 200", "Fall", 2026, "In Progress", None), ("PSCI 100", "Fall", 2026, "In Progress", None),
            ("FSYM 101", "Fall", 2026, "In Progress", None)]),
    ]
    made = {}
    for first, last, email, year, progs, courses in people:
        if email in existing:
            continue
        sid = db.add_student(first, last, email, years[year], adv, [_prog(p) for p in progs])
        for code, term, y, status, grade in courses:
            db.save_student_course(sid, code, term, y, status, grade)
        made[email] = sid
    return made


if __name__ == "__main__":
    print("demo data created for:", list(seed()) or "nothing (already present)")
    print("sign in as", ADVISOR[2])
