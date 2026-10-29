"""Student Performance Early-Warning System (Flask + SQLite).

Run:  python app.py      then open http://127.0.0.1:5000
"""
import logging
import os
import re
import secrets
import sqlite3
from datetime import date
from functools import wraps

from flask import (Flask, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from risk import assess

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _load_secret_key():
    """Use SECRET_KEY from the environment, otherwise create and reuse a local one."""
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    path = os.path.join(BASE_DIR, ".secret_key")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        key = secrets.token_hex(32)
        with open(path, "w", encoding="utf-8") as f:
            f.write(key)
        return key


app = Flask(__name__)
app.config.update(
    DATABASE=os.environ.get("DATABASE", os.path.join(BASE_DIR, "ewsys.db")),
    SECRET_KEY=_load_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=64 * 1024,  # requests here are tiny; reject anything large
)
logging.basicConfig(level=logging.INFO)

TERMS = ("Prelim", "Midterm", "Finals")
STATUSES = ("Present", "Late", "Absent", "Excused")


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with open(os.path.join(BASE_DIR, "schema.sql"), "r", encoding="utf-8") as f:
        script = f.read()
    db = get_db()
    db.executescript(script)
    db.commit()


# --------------------------------------------------------------------------
# Security helpers: login guard and CSRF token for HTML forms
# --------------------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify(error="Please log in first."), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


def csrf_ok():
    sent = request.form.get("_csrf", "")
    return bool(sent) and secrets.compare_digest(sent, session.get("_csrf", ""))


def safe_next(target):
    """Only allow redirects to a path on this site (prevents open redirects)."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("dashboard")


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
STUDENT_NO_RE = re.compile(r"^[A-Za-z0-9-]{3,20}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,30}$")


def _text(data, key, label, errors, min_len=1, max_len=60):
    value = data.get(key)
    value = value.strip() if isinstance(value, str) else ""
    if len(value) < min_len:
        errors[key] = f"{label} is required."
    elif len(value) > max_len:
        errors[key] = f"{label} must be {max_len} characters or fewer."
    return value


def validate_student(data):
    errors = {}
    clean = {
        "student_no": _text(data, "student_no", "Student number", errors, 3, 20),
        "first_name": _text(data, "first_name", "First name", errors, 1, 50),
        "last_name": _text(data, "last_name", "Last name", errors, 1, 50),
        "course": _text(data, "course", "Course", errors, 2, 60),
    }
    if "student_no" not in errors and not STUDENT_NO_RE.match(clean["student_no"]):
        errors["student_no"] = "Use letters, numbers and dashes only (3-20 characters)."

    try:
        year = int(data.get("year_level"))
        if not 1 <= year <= 6:
            raise ValueError
        clean["year_level"] = year
    except (TypeError, ValueError):
        errors["year_level"] = "Year level must be a number from 1 to 6."

    email = data.get("email")
    email = email.strip() if isinstance(email, str) else ""
    if email and (len(email) > 120 or not EMAIL_RE.match(email)):
        errors["email"] = "Enter a valid email address."
    clean["email"] = email or None
    return clean, errors


def validate_grade(data):
    errors = {}
    clean = {"subject": _text(data, "subject", "Subject", errors, 2, 60)}
    term = data.get("term")
    if term not in TERMS:
        errors["term"] = "Choose Prelim, Midterm or Finals."
    clean["term"] = term
    try:
        score = float(data.get("score"))
        if not 0 <= score <= 100 or score != score:
            raise ValueError
        clean["score"] = round(score, 2)
    except (TypeError, ValueError):
        errors["score"] = "Score must be a number from 0 to 100."
    return clean, errors


def validate_attendance(data):
    errors = {}
    clean = {}
    raw = data.get("date")
    try:
        d = date.fromisoformat(raw) if isinstance(raw, str) else None
        if d is None:
            raise ValueError
        if d > date.today():
            errors["date"] = "Date cannot be in the future."
        clean["date"] = d.isoformat()
    except ValueError:
        errors["date"] = "Enter a valid date."
    status = data.get("status")
    if status not in STATUSES:
        errors["status"] = "Choose Present, Late, Absent or Excused."
    clean["status"] = status
    return clean, errors


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None
    return data


def bad_request(message="Invalid request.", fields=None):
    body = {"error": message}
    if fields:
        body["fields"] = fields
    return jsonify(body), 400


# --------------------------------------------------------------------------
# Data access
# --------------------------------------------------------------------------
def _like(term):
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def load_students(db, query=""):
    sql = "SELECT * FROM students"
    params = []
    if query:
        sql += (" WHERE student_no LIKE ? ESCAPE '\\' OR first_name LIKE ? ESCAPE '\\'"
                " OR last_name LIKE ? ESCAPE '\\' OR course LIKE ? ESCAPE '\\'"
                " OR (first_name || ' ' || last_name) LIKE ? ESCAPE '\\'")
        params = [_like(query)] * 5
    sql += " ORDER BY last_name, first_name"
    return db.execute(sql, params).fetchall()


def student_with_risk(db, student_id):
    grades = [dict(r) for r in db.execute(
        "SELECT * FROM grades WHERE student_id = ? ORDER BY id", (student_id,))]
    attendance = [dict(r) for r in db.execute(
        "SELECT * FROM attendance WHERE student_id = ? ORDER BY date DESC", (student_id,))]
    return grades, attendance, assess(grades, attendance)


def all_risks(db):
    """Risk assessment for every student, computed from two bulk queries."""
    grades, attendance = {}, {}
    for r in db.execute("SELECT student_id, subject, score FROM grades ORDER BY id"):
        grades.setdefault(r["student_id"], []).append(dict(r))
    for r in db.execute("SELECT student_id, status FROM attendance"):
        attendance.setdefault(r["student_id"], []).append(dict(r))
    ids = [r["id"] for r in db.execute("SELECT id FROM students")]
    return {sid: assess(grades.get(sid, []), attendance.get(sid, [])) for sid in ids}


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
@app.route("/")
def index():
    return redirect(url_for("dashboard" if "user_id" in session else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if not csrf_ok():
            flash("Your session expired. Please try again.", "danger")
            return redirect(url_for("login"))
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["full_name"] = user["full_name"]
            return redirect(safe_next(request.args.get("next")))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    values = {}
    if request.method == "POST":
        if not csrf_ok():
            flash("Your session expired. Please try again.", "danger")
            return redirect(url_for("register"))
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        values = {"full_name": full_name, "username": username}

        problems = []
        if not 2 <= len(full_name) <= 80:
            problems.append("Full name must be 2 to 80 characters.")
        if not USERNAME_RE.match(username):
            problems.append("Username: 3-30 characters, lowercase letters, numbers, dot or underscore.")
        if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            problems.append("Password must be at least 8 characters and include a letter and a number.")
        if password != confirm:
            problems.append("Passwords do not match.")

        if not problems:
            try:
                db = get_db()
                db.execute(
                    "INSERT INTO users (username, full_name, password_hash) VALUES (?, ?, ?)",
                    (username, full_name, generate_password_hash(password)))
                db.commit()
                flash("Account created. You can log in now.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                problems.append("That username is already taken.")
        for p in problems:
            flash(p, "danger")
    return render_template("register.html", values=values)


@app.route("/logout", methods=["POST"])
def logout():
    if csrf_ok():
        session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/students/<int:student_id>")
@login_required
def student_page(student_id):
    row = get_db().execute("SELECT id FROM students WHERE id = ?", (student_id,)).fetchone()
    if row is None:
        return render_template("error.html", code=404, message="That student does not exist."), 404
    return render_template("student.html", student_id=student_id)


# --------------------------------------------------------------------------
# JSON API: students
# --------------------------------------------------------------------------
@app.route("/api/students", methods=["GET"])
@login_required
def api_students_list():
    db = get_db()
    query = request.args.get("q", "").strip()[:60]
    level_filter = request.args.get("risk", "").strip()
    risks = all_risks(db)

    summary = {"total": len(risks), "High": 0, "Moderate": 0, "Low": 0, "No data": 0}
    for r in risks.values():
        summary[r["level"]] += 1

    students = []
    for row in load_students(db, query):
        risk = risks[row["id"]]
        if level_filter and risk["level"] != level_filter:
            continue
        students.append({**dict(row), "risk": risk})

    order = {"High": 0, "Moderate": 1, "Low": 2, "No data": 3}
    if request.args.get("sort", "risk") == "risk":
        students.sort(key=lambda s: (order[s["risk"]["level"]], -(s["risk"]["score"] or 0)))
    return jsonify(students=students, summary=summary)


@app.route("/api/students", methods=["POST"])
@login_required
def api_students_create():
    data = json_body()
    if data is None:
        return bad_request("Send the student details as JSON.")
    clean, errors = validate_student(data)
    if errors:
        return bad_request("Please fix the highlighted fields.", errors)
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO students (student_no, first_name, last_name, course, year_level, email)"
            " VALUES (:student_no, :first_name, :last_name, :course, :year_level, :email)", clean)
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify(error="That student number already exists.",
                       fields={"student_no": "Already in use."}), 409
    return jsonify(id=cur.lastrowid), 201


@app.route("/api/students/<int:student_id>", methods=["GET"])
@login_required
def api_students_get(student_id):
    db = get_db()
    row = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if row is None:
        return jsonify(error="Student not found."), 404
    grades, attendance, risk = student_with_risk(db, student_id)
    return jsonify(student=dict(row), grades=grades, attendance=attendance, risk=risk)


@app.route("/api/students/<int:student_id>", methods=["PUT"])
@login_required
def api_students_update(student_id):
    data = json_body()
    if data is None:
        return bad_request("Send the student details as JSON.")
    clean, errors = validate_student(data)
    if errors:
        return bad_request("Please fix the highlighted fields.", errors)
    db = get_db()
    try:
        cur = db.execute(
            "UPDATE students SET student_no=:student_no, first_name=:first_name,"
            " last_name=:last_name, course=:course, year_level=:year_level, email=:email"
            " WHERE id=:id", {**clean, "id": student_id})
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify(error="That student number already exists.",
                       fields={"student_no": "Already in use."}), 409
    if cur.rowcount == 0:
        return jsonify(error="Student not found."), 404
    return jsonify(ok=True)


@app.route("/api/students/<int:student_id>", methods=["DELETE"])
@login_required
def api_students_delete(student_id):
    db = get_db()
    cur = db.execute("DELETE FROM students WHERE id = ?", (student_id,))
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="Student not found."), 404
    return jsonify(ok=True)


# --------------------------------------------------------------------------
# JSON API: grades
# --------------------------------------------------------------------------
def _student_exists(db, student_id):
    return db.execute("SELECT 1 FROM students WHERE id = ?", (student_id,)).fetchone() is not None


@app.route("/api/students/<int:student_id>/grades", methods=["POST"])
@login_required
def api_grades_create(student_id):
    db = get_db()
    if not _student_exists(db, student_id):
        return jsonify(error="Student not found."), 404
    data = json_body()
    if data is None:
        return bad_request("Send the grade as JSON.")
    clean, errors = validate_grade(data)
    if errors:
        return bad_request("Please fix the highlighted fields.", errors)
    cur = db.execute(
        "INSERT INTO grades (student_id, subject, term, score) VALUES (?, ?, ?, ?)",
        (student_id, clean["subject"], clean["term"], clean["score"]))
    db.commit()
    return jsonify(id=cur.lastrowid), 201


@app.route("/api/grades/<int:grade_id>", methods=["PUT"])
@login_required
def api_grades_update(grade_id):
    data = json_body()
    if data is None:
        return bad_request("Send the grade as JSON.")
    clean, errors = validate_grade(data)
    if errors:
        return bad_request("Please fix the highlighted fields.", errors)
    db = get_db()
    cur = db.execute("UPDATE grades SET subject=?, term=?, score=? WHERE id=?",
                     (clean["subject"], clean["term"], clean["score"], grade_id))
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="Grade not found."), 404
    return jsonify(ok=True)


@app.route("/api/grades/<int:grade_id>", methods=["DELETE"])
@login_required
def api_grades_delete(grade_id):
    db = get_db()
    cur = db.execute("DELETE FROM grades WHERE id = ?", (grade_id,))
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="Grade not found."), 404
    return jsonify(ok=True)


# --------------------------------------------------------------------------
# JSON API: attendance
# --------------------------------------------------------------------------
@app.route("/api/students/<int:student_id>/attendance", methods=["POST"])
@login_required
def api_attendance_create(student_id):
    db = get_db()
    if not _student_exists(db, student_id):
        return jsonify(error="Student not found."), 404
    data = json_body()
    if data is None:
        return bad_request("Send the attendance as JSON.")
    clean, errors = validate_attendance(data)
    if errors:
        return bad_request("Please fix the highlighted fields.", errors)
    try:
        cur = db.execute(
            "INSERT INTO attendance (student_id, date, status) VALUES (?, ?, ?)",
            (student_id, clean["date"], clean["status"]))
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify(error="Attendance for that date is already recorded.",
                       fields={"date": "Already recorded."}), 409
    return jsonify(id=cur.lastrowid), 201


@app.route("/api/attendance/<int:attendance_id>", methods=["DELETE"])
@login_required
def api_attendance_delete(attendance_id):
    db = get_db()
    cur = db.execute("DELETE FROM attendance WHERE id = ?", (attendance_id,))
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="Record not found."), 404
    return jsonify(ok=True)


# --------------------------------------------------------------------------
# Error handling
# --------------------------------------------------------------------------
def _error_response(code, message):
    if request.path.startswith("/api/"):
        return jsonify(error=message), code
    return render_template("error.html", code=code, message=message), code


@app.errorhandler(HTTPException)
def handle_http_error(err):
    messages = {404: "That page does not exist.", 405: "That action is not allowed here.",
                413: "The request was too large."}
    return _error_response(err.code, messages.get(err.code, err.description))


@app.errorhandler(Exception)
def handle_unexpected_error(err):
    app.logger.exception("Unhandled error: %s", err)
    return _error_response(500, "Something went wrong on our side. Please try again.")


# Create the tables on startup (safe to repeat).
with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
