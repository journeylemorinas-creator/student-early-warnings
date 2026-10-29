"""Early-warning risk assessment.

This is the "AI-assisted" part of the system. It is a transparent, rule-based
scoring model (not a machine-learning model): every point of risk can be
traced to a rule, and the result is explained in plain language so a teacher
can verify it. It only supports a teacher's judgement; it never decides alone.

Risk score (0-100) = grade risk (max 60) + attendance risk (max 30) + trend risk (max 10)
"""

PASSING_GRADE = 75.0      # a subject average below this is a concern
GOOD_GRADE = 85.0         # at or above this, grade risk is zero
FLOOR_GRADE = 60.0        # at or below this, grade risk is maximum

GOOD_ATTENDANCE = 95.0    # at or above this, attendance risk is zero
FLOOR_ATTENDANCE = 70.0   # at or below this, attendance risk is maximum

ATTENDANCE_POINTS = {"Present": 1.0, "Excused": 1.0, "Late": 0.5, "Absent": 0.0}

HIGH_AT = 60
MODERATE_AT = 30


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def attendance_rate(records):
    """Percentage of attendance credit earned, or None when there are no records."""
    if not records:
        return None
    earned = sum(ATTENDANCE_POINTS.get(r["status"], 0.0) for r in records)
    return earned / len(records) * 100


def assess(grades, attendance):
    """Return a risk assessment for one student.

    grades:     list of dicts with "subject" and "score", oldest first
    attendance: list of dicts with "status"
    """
    if not grades and not attendance:
        return {
            "score": None, "level": "No data", "average": None,
            "attendance_rate": None, "weak_subjects": [],
            "reasons": ["No grades or attendance have been recorded yet."],
            "suggestions": ["Record grades and attendance to enable monitoring."],
        }

    reasons = []
    suggestions = []

    # --- grade component (max 60) ---
    average = None
    grade_risk = 0.0
    weak_subjects = []
    if grades:
        scores = [g["score"] for g in grades]
        average = sum(scores) / len(scores)
        grade_risk = _clamp((GOOD_GRADE - average) / (GOOD_GRADE - FLOOR_GRADE)) * 60

        by_subject = {}
        for g in grades:
            by_subject.setdefault(g["subject"], []).append(g["score"])
        weak_subjects = sorted(
            s for s, vals in by_subject.items() if sum(vals) / len(vals) < PASSING_GRADE
        )
        if average < PASSING_GRADE:
            reasons.append(f"Overall average is {average:.1f}, below the passing mark of {PASSING_GRADE:.0f}.")
        if weak_subjects:
            reasons.append("Below passing in: " + ", ".join(weak_subjects) + ".")
            suggestions.append("Offer tutoring or remedial work in " + ", ".join(weak_subjects) + ".")
    else:
        reasons.append("No grades recorded yet, so grade risk could not be measured.")

    # --- attendance component (max 30) ---
    rate = attendance_rate(attendance)
    attendance_risk = 0.0
    if rate is not None:
        attendance_risk = _clamp((GOOD_ATTENDANCE - rate) / (GOOD_ATTENDANCE - FLOOR_ATTENDANCE)) * 30
        if rate < GOOD_ATTENDANCE:
            absences = sum(1 for r in attendance if r["status"] == "Absent")
            reasons.append(f"Attendance is {rate:.0f}% ({absences} absence{'s' if absences != 1 else ''} recorded).")
            suggestions.append("Follow up with the student about missed classes.")
    else:
        reasons.append("No attendance recorded yet, so attendance risk could not be measured.")

    # --- trend component (max 10): are the latest grades dropping? ---
    trend_risk = 0.0
    if len(grades) >= 3:
        recent = [g["score"] for g in grades[-2:]]
        earlier = [g["score"] for g in grades[:-2]]
        drop = sum(earlier) / len(earlier) - sum(recent) / len(recent)
        if drop > 0:
            trend_risk = _clamp(drop / 15) * 10
        if drop >= 5:
            reasons.append(f"Recent grades are {drop:.1f} points lower than earlier ones.")
            suggestions.append("Ask what changed recently; a sudden drop is easier to fix early.")

    score = round(grade_risk + attendance_risk + trend_risk)
    if score >= HIGH_AT:
        level = "High"
        suggestions.insert(0, "Schedule a one-on-one meeting and inform the class adviser.")
    elif score >= MODERATE_AT:
        level = "Moderate"
        suggestions.insert(0, "Check in with the student and monitor the next assessment closely.")
    else:
        level = "Low"
        if not reasons:
            reasons.append("Grades and attendance are within healthy ranges.")
        suggestions.insert(0, "No action needed. Keep monitoring.")

    return {
        "score": score,
        "level": level,
        "average": round(average, 1) if average is not None else None,
        "attendance_rate": round(rate, 1) if rate is not None else None,
        "weak_subjects": weak_subjects,
        "reasons": reasons,
        "suggestions": suggestions,
    }
