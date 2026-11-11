"""First-run catalog data (loaded once by migrate.py). Written as Python tuples, not SQL,
so a wrong column order is caught by validate() / the tests instead of failing at run time.
Tuple order for COURSES: (code, title, credits, when_offered, notes)"""

CATALOG_YEARS = [("2024-2025", 2024, False), ("2025-2026", 2025, False), ("2026-2027", 2026, True)]

PROGRAMS = [   # (code, name, type, credits_required)
    ("CS", "Computer Science", "Major", 43), ("Cyber", "Cybersecurity", "Major", 48),
    ("Data", "Data Science", "Major", 49), ("Math", "Mathematics", "Major", 41),
    ("Cyber&CS", "Computer Science & Cybersecurity", "Double Major", 64),
    ("Math&CS", "Mathematics & Computer Science", "Double Major", 69),
    ("Cyber&Data", "Cybersecurity & Data Science", "Double Major", 67),
    ("CS&Data", "Computer Science & Data Science", "Double Major", 65),
    ("Math&Data", "Mathematics & Data Science", "Double Major", 65),
    ("CS-M", "Computer Science Minor", "Minor", 18), ("Cyber-M", "Cybersecurity Minor", "Minor", 18),
    ("Math-M", "Mathematics Minor", "Minor", 19), ("Data-M", "Data Science Minor", "Minor", 18),
]

COURSES = [
    # ---- Computer Science
    ("CMSCI 101", "Computer Technology", 3, "Not Offered", "Not offered since the late 2010s"),
    ("CMSCI 115", "Computer Games and Gaming", 3, "Not Offered", "Not offered since the late 2010s"),
    ("CMSCI 119", "Intro to Artificial Intelligence", 3, None, "New course, never been offered"),
    ("CMSCI 120", "Introduction to Computer Science I", 3, "Both", None),
    ("CMSCI 125", "Introduction to Computer Science II", 3, "Both", None),
    ("CMSCI 254", "Data Structures and Algorithms", 3, "Fall", None),
    ("CMSCI 256", "Principles of Software Development", 3, "Spring", None),
    ("CMSCI 277", "Computer Systems", 3, "Fall", None),
    ("CMSCI 305", "Mobile App Development", 3, None, "New course, never been offered"),
    ("CMSCI 349", "Software Engineering", 3, "Fall", None),
    ("CMSCI 355", "Network Systems and Design", 3, "Fall", None),
    ("CMSCI 356", "Operating Systems", 3, "Spring", None),
    ("CMSCI 358", "Computer Security I", 3, "Fall", None),
    ("CMSCI 359", "Database Management Systems", 3, "Spring", None),
    ("CMSCI 368", "Computer Security II", 3, "Spring", "Spring of odd years"),
    ("CMSCI 369", "Database Implementation", 3, None, "Never been offered"),
    ("CMSCI 394", "Computer Graphics", 3, "Spring", "On a rotating basis"),
    ("CMSCI 398", "Independent Study", 3, None, None),
    ("CMSCI 442", "Principles of Programming Languages", 3, "Fall", "Fall of odd years"),
    ("CMSCI 449", "AI Theory & Implementation", 3, "Spring", "Spring of even years"),
    ("CMSCI 452", "Compiler Design", 3, "Fall", "Fall of even years"),
    ("CMSCI 453", "Algorithms", 3, "Spring", None),
    ("CMSCI 474", "Computer Science Capstone I", 3, "Fall", None),
    ("CMSCI 475", "Computer Science Capstone II", 3, "Spring", None),
    ("CMSCI 485", "Theory of Computation", 3, "Fall", None),
    ("CMSCI 492", "Practicum", 3, None, None), ("CMSCI 493", "Practicum", 3, None, None),
    ("CMSCI 499", "Special Topics in Computer Science", 3, None, None),
    # ---- Cybersecurity
    ("CYBER 100", "Foundations of Cybersecurity", 3, None, None),
    ("CYBER 260", "Networking Administration", 3, "Spring", None),
    ("CYBER 261", "Unix and Windows Operating Systems", 3, "Fall", None),
    ("CYBER 283", "Critical Infrastructure Security", 3, None, "On a rotating basis"),
    ("CYBER 301", "Secure Systems Design and Risk Management", 3, "Fall", None),
    ("CYBER 310", "Systems Operations Management", 3, "Spring", None),
    ("CYBER 354", "Cloud Security", 3, None, "On a rotating basis"),
    ("CYBER 357", "Network Security", 3, "Spring", None),
    ("CYBER 365", "Penetration Testing and Ethical Hacking", 3, None, "On a rotating basis"),
    ("CYBER 398", "Independent Study", 3, None, None),
    ("CYBER 400", "Cybersecurity Capstone", 3, "Both", None),
    ("CYBER 492", "Practicum", 3, None, None), ("CYBER 493", "Practicum", 3, None, None),
    ("CYBER 499", "Special topics in Cybersecurity", 3, None, None),
    # ---- Data Science
    ("DATA 200", "Introduction to Data Science", 3, "Both", None),
    ("DATA 201", "Special Topics in Data Science", 3, "Both", None),
    ("DATA 210", "Exploratory Data Analysis", 3, "Spring", None),
    ("DATA 220", "Machine Learning Models", 3, "Fall", None),
    ("DATA 320", "Distributed Data Systems", 3, "Spring", "Spring of odd years"),
    ("DATA 330", "Data Wrangling", 3, "Fall", "Fall of odd years"),
    ("DATA 340", "Advanced Data Visualization", 3, "Spring", "Spring of even years"),
    ("DATA 350", "Natural Language Processing", 3, "Fall", "Fall of even years"),
    ("DATA 410", "Advanced Machine Learning", 3, None, None),
    ("DATA 420", "High Performance Computing", 3, None, None),
    ("DATA 430", "Network Science", 3, None, None),
    ("DATA 475", "Data Science Capstone", 3, "Spring", None),
    ("DATA 492", "Data Science Practicum", 3, None, None), ("DATA 493", "Data Science Practicum", 3, None, None),
    # ---- Mathematics  (credits are ALWAYS the 3rd value: Calculus = 4, seminars = 1; verify)
    ("MATH 105", "Elementary Statistics", 3, "Both", None),
    ("MATH 108", "Concepts of Mathematics for Teachers I", 3, "Fall", None),
    ("MATH 109", "Concepts of Mathematics for Teachers II", 3, "Spring", None),
    ("MATH 114", "Precalculus Mathematics", 3, "Fall", None),
    ("MATH 211", "Mathematical Thinking", 3, "Both", None),
    ("MATH 228", "Discrete Mathematics", 3, "Both", None),
    ("MATH 247", "Calculus I", 4, "Both", None),
    ("MATH 248", "Calculus II", 4, "Spring", None),
    ("MATH 249", "Calculus III", 4, "Fall", None),
    ("MATH 332", "Graph Theory", 3, "Fall", "On a rotating basis, typically fall of even years"),
    ("MATH 336", "Elementary Number Theory", 3, "Fall", "On a rotating basis, typically fall of odd years"),
    ("MATH 364", "Linear Algebra", 3, "Spring", None),
    ("MATH 377", "Foundations of Geometry", 3, "Spring", "Spring of odd years"),
    ("MATH 384", "Differential Equations", 3, "Spring", "Spring of odd years"),
    ("MATH 387", "Probability", 3, "Spring", "On a rotating basis, typically spring of odd years"),
    ("MATH 388", "Operations Research", 3, "Fall", "On a rotating basis (original note said 'fall of seven years' - verify)"),
    ("MATH 389", "Numerical Methods", 3, "Fall", "On a rotating basis, typically fall of odd years. Same as CMSCI 389."),
    ("MATH 390", "Mathematical Statistics", 3, "Not Offered", None),
    ("MATH 398", "Independent Study", 3, None, None),
    ("MATH 447", "Introduction to Real Analysis", 3, None, None),
    ("MATH 457", "Introduction to Complex Analysis", 3, "Not Offered", None),
    ("MATH 464", "Advanced Linear Algebra", 3, "Not Offered", None),
    ("MATH 468", "Algebraic Structures", 3, "Spring", "Spring of even years"),
    ("MATH 472", "Topology", 3, "Not Offered", None),
    ("MATH 488", "Stochastic Processes", 3, "Not Offered", None),
    ("MATH 489", "Modeling and Simulation", 3, "Not Offered", "Same as CMSCI 489"),
    ("MATH 492", "Practicum", 3, None, None), ("MATH 493", "Practicum", 3, None, None),
    ("MATH 495", "Seminar I", 1, "Spring", None), ("MATH 496", "Seminar II", 1, "Spring", None),
    ("MATH 497", "Undergraduate Research in Mathematics", 3, None, None),
    ("MATH 499", "Special Topics in Mathematics", 3, None, None),
    # ---- University CORE courses (from the CORE picture). Titles given only as a code are placeholders:
    #      edit the titles on the Courses tab.
    ("FSYM 101", "First-Year Symposium", 3, "Fall", None),
    ("WCIV 102", "Origins of the West", 3, "Spring", None),
    ("PHIL 103", "Foundations of Philosophy", 3, "Spring", None),
    ("PHIL 203", "Philosophy in the Modern Age", 3, "Fall", None),
    ("WCIV 201", "Atlantic Encounters", 3, "Fall", None),
    ("THEOL 220", "Foundations of Theology", 3, "Spring", None),
    ("AMER 202", "America in the World", 3, "Spring", None),
    ("THEOL 320", "Made in God's Image", 3, "Fall", None),
    ("THEOL 300", "Ethics and the Human Good (Theology)", 3, "Spring", None),
    ("PHIL 300", "Ethics and the Human Good (Philosophy)", 3, "Spring", None),
    ("CJUST 110", "Social Science CORE option (title to import)", 3, None, None),
    ("ECON 101", "Social Science CORE option (title to import)", 3, None, None),
    ("ECON 102", "Social Science CORE option (title to import)", 3, None, None),
    ("EDUC 100", "Social Science CORE option (title to import)", 3, None, None),
    ("PSCI 100", "Social Science CORE option (title to import)", 3, None, None),
    ("PSYCH 100", "Social Science CORE option (title to import)", 3, None, None),
    ("SOC 100", "Social Science CORE option (title to import)", 3, None, None),
    ("ENMO 300", "Modernity (English)", 3, "Fall", None), ("MUMO 300", "Modernity (Music)", 3, "Fall", None),
    ("ARMO 300", "Modernity (Art)", 3, "Fall", None), ("THMO 300", "Modernity (Theology)", 3, "Fall", None),
]

# (course, prerequisite, group_no)  same group = OR, different groups = AND
PREREQS = [
    ("CMSCI 125", "CMSCI 120", 1), ("CMSCI 254", "CMSCI 125", 1), ("CMSCI 256", "CMSCI 125", 1),
    ("CMSCI 277", "CMSCI 120", 1), ("CMSCI 305", "CMSCI 125", 1), ("CMSCI 349", "CMSCI 254", 1),
    ("CMSCI 355", "CMSCI 125", 1), ("CMSCI 356", "CMSCI 125", 1), ("CMSCI 356", "CMSCI 277", 2),
    ("CMSCI 358", "CMSCI 125", 1), ("CMSCI 359", "CMSCI 125", 1), ("CMSCI 368", "CMSCI 358", 1),
    ("CMSCI 369", "CMSCI 359", 1), ("CMSCI 394", "CMSCI 125", 1), ("CMSCI 442", "CMSCI 254", 1),
    ("CMSCI 449", "CMSCI 254", 1), ("CMSCI 452", "CMSCI 254", 1), ("CMSCI 453", "CMSCI 254", 1),
    ("CMSCI 453", "MATH 228", 2), ("CMSCI 474", "CMSCI 254", 1), ("CMSCI 475", "CMSCI 474", 1),
    ("CMSCI 485", "CMSCI 254", 1), ("CMSCI 485", "MATH 228", 2),
    ("CYBER 260", "CMSCI 125", 1), ("CYBER 261", "CMSCI 125", 1), ("CYBER 283", "CMSCI 120", 1),
    ("CYBER 301", "CMSCI 125", 1), ("CYBER 310", "CMSCI 125", 1), ("CYBER 354", "CYBER 260", 1),
    ("CYBER 357", "CMSCI 355", 1), ("CYBER 365", "CYBER 260", 1),
    ("DATA 201", "DATA 200", 1), ("DATA 210", "DATA 200", 1), ("DATA 220", "DATA 210", 1),
    ("DATA 320", "DATA 200", 1), ("DATA 320", "CMSCI 125", 2), ("DATA 330", "DATA 200", 1), ("DATA 330", "CMSCI 125", 2),
    ("DATA 340", "DATA 200", 1), ("DATA 340", "CMSCI 125", 2), ("DATA 350", "DATA 200", 1), ("DATA 350", "CMSCI 125", 2),
    ("DATA 410", "DATA 220", 1), ("DATA 420", "DATA 220", 1), ("DATA 430", "DATA 220", 1),
    ("MATH 247", "MATH 114", 1), ("MATH 248", "MATH 247", 1), ("MATH 249", "MATH 248", 1),
    ("MATH 332", "MATH 228", 1), ("MATH 336", "MATH 247", 1), ("MATH 336", "MATH 228", 1),
    ("MATH 364", "MATH 247", 1), ("MATH 364", "MATH 228", 1), ("MATH 377", "MATH 228", 1),
    ("MATH 384", "MATH 248", 1), ("MATH 387", "MATH 228", 1), ("MATH 387", "MATH 248", 2),
    ("MATH 388", "MATH 247", 1), ("MATH 388", "MATH 228", 1), ("MATH 389", "MATH 247", 1),
    ("MATH 389", "CMSCI 120", 2), ("MATH 390", "MATH 387", 1), ("MATH 447", "MATH 248", 1),
    ("MATH 457", "MATH 249", 1), ("MATH 464", "MATH 364", 1), ("MATH 468", "MATH 228", 1),
    ("MATH 468", "MATH 248", 2), ("MATH 472", "MATH 228", 1), ("MATH 472", "MATH 248", 2),
    ("MATH 488", "MATH 387", 1), ("MATH 489", "MATH 248", 1),
]

# DRAFT requirement lists (fit to the credit totals in PROGRAMS). Verify, then edit in the app.
_R = {
    "CS": ("CMSCI 120 CMSCI 125 CMSCI 254 CMSCI 256 CMSCI 277 CMSCI 349 CMSCI 453 CMSCI 474 CMSCI 475 CMSCI 485 MATH 228 MATH 247",
           "CMSCI 305 CMSCI 355 CMSCI 356 CMSCI 358 CMSCI 359 CMSCI 368 CMSCI 394 CMSCI 442 CMSCI 449 CMSCI 452", 2),
    "Cyber": ("CMSCI 120 CMSCI 125 CMSCI 355 CMSCI 358 CYBER 100 CYBER 260 CYBER 261 CYBER 301 CYBER 310 CYBER 357 CYBER 400 MATH 228",
              "CYBER 283 CYBER 354 CYBER 365 CMSCI 356 CMSCI 359 CMSCI 368", 4),
    "Data": ("DATA 200 DATA 210 DATA 220 DATA 475 CMSCI 120 CMSCI 125 CMSCI 254 CMSCI 359 MATH 105 MATH 247",
             "DATA 201 DATA 320 DATA 330 DATA 340 DATA 350 DATA 410 DATA 420 DATA 430", 6),
    "Math": ("MATH 228 MATH 247 MATH 248 MATH 249 MATH 364 MATH 387 MATH 447 MATH 468 MATH 495 MATH 496 CMSCI 120",
             "MATH 332 MATH 336 MATH 377 MATH 384 MATH 388 MATH 389 MATH 457 MATH 464 MATH 472", 3),
    "CS-M": ("CMSCI 120 CMSCI 125 CMSCI 254", "CMSCI 256 CMSCI 277 CMSCI 349 CMSCI 355 CMSCI 358 CMSCI 359 CMSCI 394", 3),
    "Cyber-M": ("CYBER 100 CYBER 260 CYBER 261 CYBER 301", "CYBER 310 CYBER 354 CYBER 357 CYBER 365 CYBER 283", 2),
    "Math-M": ("MATH 247 MATH 248 MATH 249 MATH 228 MATH 364 MATH 495", "", 0),
    "Data-M": ("DATA 200 DATA 210 DATA 220", "DATA 201 DATA 320 DATA 330 DATA 340 DATA 350", 3),
}


def _codes(s):          # "CMSCI 120 CMSCI 125" -> ["CMSCI 120", "CMSCI 125"]
    w = s.split()
    return [f"{w[i]} {w[i + 1]}" for i in range(0, len(w), 2)]


REQUIREMENTS = {p: (_codes(c), _codes(e), n) for p, (c, e, n) in _R.items()}   # program -> (core, elective pool, n)

# CORE curriculum from the picture. (name, take_as, offered, credits, manual_only, notes, [options])
CORE = [
    ("First-Year Symposium", "Fr", "Fall", 3, False, None, ["FSYM 101"]),
    ("Origins of the West", "Fr", "Spring", 3, False, None, ["WCIV 102"]),
    ("Foundations of Philosophy", "Fr", "Spring", 3, False, None, ["PHIL 103"]),
    ("Social Science", "Fr", "Both", 3, False,
     "CJUST 110, ECON 101/102, EDUC 100, PSCI 100, PSYCH 100, or SOC 100. Social Science majors need a course different from their major.",
     ["CJUST 110", "ECON 101", "ECON 102", "EDUC 100", "PSCI 100", "PSYCH 100", "SOC 100"]),
    ("World Languages 1", "Fr", "Fall", 3, True,
     "Either take both 101 and 102 of the same language, or complete just 201 or 301. ASL can count if the student has special permission. Mark it satisfied manually (any language code).", []),
    ("World Languages 2", "Fr", "Spring", 3, True,
     "Part of the World Languages requirement (see World Languages 1). Waived if the student completes 201 or 301.", []),
    ("Philosophy in the Modern Age", "So", "Fall", 3, False, None, ["PHIL 203"]),
    ("Atlantic Encounters", "So", "Fall", 3, False, None, ["WCIV 201"]),
    ("Foundations of Theology", "So", "Spring", 3, False, None, ["THEOL 220"]),
    ("America in the World", "So", "Spring", 3, False, None, ["AMER 202"]),
    ("Mathematical Thinking", "So", "Both", 3, False, None, ["MATH 211"]),
    ("Made in God's Image", "Ju", "Fall", 3, False, None, ["THEOL 320"]),
    ("Modernity", "Ju", "Fall", 3, False, "ENMO 300, MUMO 300, ARMO 300, THMO 300 (xxMO 300).",
     ["ENMO 300", "MUMO 300", "ARMO 300", "THMO 300", "xxMO 300"]),
    ("Ethics and the Human Good", "Ju", "Spring", 3, False, "THEOL 300 or PHIL 300.", ["THEOL 300", "PHIL 300"]),
    ("Global Encounters", "Ju", "Spring", 3, False, "Any xxGE 3xx course.", ["xxGE 3xx"]),
    ("Lab Science", "Ju", "Both", 4, False, "4 credits. BIO, CHEM, PHYS could count for this as well.",
     ["GNSCI xxx", "BIO xxx", "CHEM xxx", "PHYS xxx"]),
    ("Ethical Leaders", "Sr", "Both", 3, True, None, []),
]


def validate():
    """Raise AssertionError with a precise message if the seed data is malformed."""
    codes = set()
    for i, c in enumerate(COURSES):
        assert len(c) == 5, f"COURSES[{i}] {c[:1]} must have 5 values"
        assert isinstance(c[2], int) and 0 <= c[2] <= 12, f"COURSES[{i}] {c[0]}: credits must be an int (got {c[2]!r})"
        assert c[3] in (None, "Fall", "Spring", "Both", "Not Offered"), f"{c[0]}: bad when_offered {c[3]!r}"
        assert c[0] not in codes, f"duplicate course {c[0]}"
        codes.add(c[0])
    for a, b, g in PREREQS:
        assert a in codes and b in codes and isinstance(g, int), f"bad prerequisite {(a, b, g)}"
    for p, (core, el, n) in REQUIREMENTS.items():
        for x in core + el:
            assert x in codes, f"{p}: unknown course {x}"
        assert p in {q[0] for q in PROGRAMS}, f"unknown program {p}"
    for name, take, off, cr, man, notes, opts in CORE:
        assert take in ("Fr", "So", "Ju", "Sr") and off in ("Fall", "Spring", "Both"), name
        for o in opts:
            if not any(ch == "x" for ch in o):
                assert o in codes, f"CORE {name}: option {o} is not in COURSES"
    return True
