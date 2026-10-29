"""Load demo data so the dashboard has something to show.

    python seed.py

Creates a demo teacher account and 12 sample students with grades and attendance.
Safe to run twice: it does nothing if students already exist.
The names are fictional. Delete the demo account before any real use.
"""
import random
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from app import app, get_db, init_db

DEMO_USER = ("teacher", "Demo Teacher", "Teacher123!")

# (student_no, first, last, course, year, average target, attendance target 0-1)
STUDENTS = [
    ("2024-0001", "Maria", "Santos", "BSIT", 3, 92, 0.98),
    ("2024-0002", "Juan", "Dela Cruz", "BSIT", 3, 88, 0.96),
    ("2024-0003", "Angela", "Reyes", "BSIT", 2, 81, 0.90),
    ("2024-0004", "Mark", "Garcia", "BSIT", 4, 78, 0.85),
    ("2024-0005", "Joan", "Mendoza", "BSBA", 1, 72, 0.88),
    ("2024-0006", "Paolo", "Bautista", "BSIT", 2, 70, 0.78),
    ("2024-0007", "Liza", "Ramos", "BSCS", 3, 66, 0.72),
    ("2024-0008", "Carlo", "Villanueva", "BSIT", 1, 62, 0.65),
    ("2024-0009", "Nina", "Aquino", "BSBA", 2, 95, 0.99),
    ("2024-0010", "Ken", "Torres", "BSCS", 4, 74, 0.80),
    ("2024-0011", "Bea", "Lopez", "BSIT", 1, 84, 0.93),
    ("2024-0012", "Rico", "Navarro", "BSIT", 3, 58, 0.60),
]
SUBJECTS = ["Programming 1", "Database Systems", "Web Development", "Networking"]
TERMS = ["Prelim", "Midterm", "Finals"]


def weekdays_back(n):
    days, d = [], date.today()
    while len(days) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            days.append(d)
    return days


def main():
    rng = random.Random(42)
    with app.app_context():
        init_db()
        db = get_db()

        if not db.execute("SELECT 1 FROM users WHERE username = ?", (DEMO_USER[0],)).fetchone():
            db.execute("INSERT INTO users (username, full_name, password_hash) VALUES (?, ?, ?)",
                       (DEMO_USER[0], DEMO_USER[1], generate_password_hash(DEMO_USER[2])))

        if db.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0:
            days = weekdays_back(20)
            for no, first, last, course, year, target, att in STUDENTS:
                sid = db.execute(
                    "INSERT INTO students (student_no, first_name, last_name, course, year_level, email)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (no, first, last, course, year, f"{first}.{last}".replace(" ", "").lower() + "@example.com"),
                ).lastrowid
                for subject in SUBJECTS[:3]:
                    for i, term in enumerate(TERMS):
                        # low performers slide down a little each term
                        drift = -2 * i if target < 80 else 0
                        score = max(40, min(100, target + drift + rng.randint(-5, 5)))
                        db.execute("INSERT INTO grades (student_id, subject, term, score) VALUES (?, ?, ?, ?)",
                                   (sid, subject, term, score))
                for d in days:
                    roll = rng.random()
                    if roll < att:
                        status = "Present" if rng.random() > 0.08 else "Late"
                    else:
                        status = "Absent" if rng.random() > 0.2 else "Excused"
                    db.execute("INSERT INTO attendance (student_id, date, status) VALUES (?, ?, ?)",
                               (sid, d.isoformat(), status))
            print(f"Added {len(STUDENTS)} demo students.")
        else:
            print("Students already exist, so no demo students were added.")
        db.commit()
    print(f"Demo login -> username: {DEMO_USER[0]}   password: {DEMO_USER[2]}")


if __name__ == "__main__":
    main()
