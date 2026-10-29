"""Automated tests. Run from the project folder with:  python -m unittest discover -s tests -v"""
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

# Use a throwaway database; this must be set before the app is imported.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE"] = _tmp.name
os.environ["SECRET_KEY"] = "test-secret"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, get_db, init_db  # noqa: E402
from risk import assess, attendance_rate  # noqa: E402


class RiskTests(unittest.TestCase):
    def test_no_data(self):
        self.assertEqual(assess([], [])["level"], "No data")

    def test_strong_student_is_low(self):
        grades = [{"subject": "Math", "score": 92}] * 3
        att = [{"status": "Present"}] * 10
        r = assess(grades, att)
        self.assertEqual(r["level"], "Low")
        self.assertEqual(r["score"], 0)

    def test_struggling_student_is_high(self):
        grades = [{"subject": "Math", "score": 60}] * 3
        att = [{"status": "Absent"}] * 5 + [{"status": "Present"}] * 5
        r = assess(grades, att)
        self.assertEqual(r["level"], "High")
        self.assertIn("Math", r["weak_subjects"])

    def test_attendance_rate_credits_late_half(self):
        rate = attendance_rate([{"status": "Present"}, {"status": "Late"}, {"status": "Absent"}, {"status": "Excused"}])
        self.assertAlmostEqual(rate, 62.5)

    def test_dropping_grades_add_trend_risk(self):
        steady = assess([{"subject": "A", "score": 80}] * 4, [])
        falling = assess([{"subject": "A", "score": s} for s in (90, 90, 70, 70)], [])
        self.assertGreater(falling["score"], steady["score"])


class AppTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        with app.app_context():
            init_db()
            db = get_db()
            for t in ("attendance", "grades", "students", "users"):
                db.execute(f"DELETE FROM {t}")
            db.commit()
        self.client = app.test_client()
        with self.client.session_transaction() as s:
            s["_csrf"] = "tok"

    # helpers
    def set_csrf(self):
        """Logging in resets the session (and its CSRF token), so set it again before each form post."""
        with self.client.session_transaction() as s:
            s["_csrf"] = "tok"

    def logout(self):
        self.set_csrf()
        self.client.post("/logout", data={"_csrf": "tok"})

    def register_and_login(self, username="teacher1", password="Passw0rdX"):
        self.set_csrf()
        self.client.post("/register", data={"_csrf": "tok", "full_name": "Test Teacher",
                         "username": username, "password": password, "confirm": password})
        self.set_csrf()
        return self.client.post("/login", data={"_csrf": "tok", "username": username, "password": password})

    def student(self, **over):
        data = {"student_no": "2024-0001", "first_name": "Ana", "last_name": "Cruz",
                "course": "BSIT", "year_level": 2, "email": "ana@example.com"}
        data.update(over)
        return data

    # authentication
    def test_api_requires_login(self):
        r = self.client.get("/api/students")
        self.assertEqual(r.status_code, 401)

    def test_dashboard_redirects_when_logged_out(self):
        r = self.client.get("/dashboard")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])

    def test_register_validation(self):
        r = self.client.post("/register", data={"_csrf": "tok", "full_name": "A", "username": "BAD NAME",
                             "password": "short", "confirm": "different"}, follow_redirects=True)
        self.assertIn(b"Full name must be", r.data)
        self.assertIn(b"Password must be at least 8", r.data)
        self.assertIn(b"Passwords do not match", r.data)

    def test_duplicate_username_rejected(self):
        self.register_and_login()
        self.logout()
        self.set_csrf()
        r = self.client.post("/register", data={"_csrf": "tok", "full_name": "Other Teacher", "username": "teacher1",
                             "password": "Passw0rdX", "confirm": "Passw0rdX"}, follow_redirects=True)
        self.assertIn(b"already taken", r.data)

    def test_wrong_password_rejected(self):
        self.register_and_login()
        self.logout()
        self.set_csrf()
        r = self.client.post("/login", data={"_csrf": "tok", "username": "teacher1", "password": "nope"}, follow_redirects=True)
        self.assertIn(b"Invalid username or password", r.data)
        self.assertEqual(self.client.get("/api/students").status_code, 401)

    def test_login_without_csrf_token_rejected(self):
        self.register_and_login()
        self.logout()
        self.set_csrf()
        r = self.client.post("/login", data={"username": "teacher1", "password": "Passw0rdX"}, follow_redirects=True)
        self.assertIn(b"session expired", r.data)
        self.assertEqual(self.client.get("/api/students").status_code, 401)

    def test_logout_ends_session(self):
        self.register_and_login()
        self.assertEqual(self.client.get("/api/students").status_code, 200)
        self.logout()
        self.assertEqual(self.client.get("/api/students").status_code, 401)

    def test_open_redirect_blocked(self):
        self.register_and_login()
        self.logout()
        self.set_csrf()
        r = self.client.post("/login?next=//evil.example", data={"_csrf": "tok", "username": "teacher1", "password": "Passw0rdX"})
        self.assertTrue(r.headers["Location"].endswith("/dashboard"))

    # students: create, read, update, delete
    def test_student_crud(self):
        self.register_and_login()
        r = self.client.post("/api/students", json=self.student())
        self.assertEqual(r.status_code, 201)
        sid = r.get_json()["id"]

        r = self.client.get(f"/api/students/{sid}")
        self.assertEqual(r.get_json()["student"]["last_name"], "Cruz")

        r = self.client.put(f"/api/students/{sid}", json=self.student(last_name="Reyes"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get(f"/api/students/{sid}").get_json()["student"]["last_name"], "Reyes")

        self.assertEqual(self.client.delete(f"/api/students/{sid}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/students/{sid}").status_code, 404)

    def test_student_validation_errors(self):
        self.register_and_login()
        r = self.client.post("/api/students", json=self.student(student_no="!", first_name="", year_level=9, email="bad"))
        self.assertEqual(r.status_code, 400)
        fields = r.get_json()["fields"]
        for key in ("student_no", "first_name", "year_level", "email"):
            self.assertIn(key, fields)

    def test_duplicate_student_number(self):
        self.register_and_login()
        self.client.post("/api/students", json=self.student())
        r = self.client.post("/api/students", json=self.student(first_name="Other"))
        self.assertEqual(r.status_code, 409)

    def test_non_json_body_rejected(self):
        self.register_and_login()
        r = self.client.post("/api/students", data="not json", content_type="text/plain")
        self.assertEqual(r.status_code, 400)

    def test_missing_student_returns_404_json(self):
        self.register_and_login()
        r = self.client.get("/api/students/9999")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    # search and filter
    def test_search_and_risk_filter(self):
        self.register_and_login()
        a = self.client.post("/api/students", json=self.student()).get_json()["id"]
        self.client.post("/api/students", json=self.student(student_no="2024-0002", first_name="Ben", last_name="Lim", course="BSCS"))
        self.client.post(f"/api/students/{a}/grades", json={"subject": "Math", "term": "Prelim", "score": 55})

        by_name = self.client.get("/api/students?q=ben").get_json()["students"]
        self.assertEqual([s["first_name"] for s in by_name], ["Ben"])
        by_course = self.client.get("/api/students?q=BSIT").get_json()["students"]
        self.assertEqual(len(by_course), 1)
        high = self.client.get("/api/students?risk=High").get_json()["students"]
        self.assertEqual(len(high), 1)
        self.assertEqual(high[0]["id"], a)

    def test_search_treats_wildcards_literally(self):
        self.register_and_login()
        self.client.post("/api/students", json=self.student())
        r = self.client.get("/api/students?q=%25").get_json()["students"]
        self.assertEqual(r, [])

    def test_sql_injection_attempt_is_harmless(self):
        self.register_and_login()
        self.client.post("/api/students", json=self.student())
        r = self.client.get("/api/students?q=' OR 1=1 --")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["students"], [])
        self.assertEqual(len(self.client.get("/api/students").get_json()["students"]), 1)

    # grades and attendance
    def test_grade_validation_and_crud(self):
        self.register_and_login()
        sid = self.client.post("/api/students", json=self.student()).get_json()["id"]
        bad = self.client.post(f"/api/students/{sid}/grades", json={"subject": "Math", "term": "Prelim", "score": 120})
        self.assertEqual(bad.status_code, 400)
        ok = self.client.post(f"/api/students/{sid}/grades", json={"subject": "Math", "term": "Prelim", "score": 88})
        gid = ok.get_json()["id"]
        self.assertEqual(self.client.put(f"/api/grades/{gid}", json={"subject": "Math", "term": "Midterm", "score": 90}).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/grades/{gid}").status_code, 200)

    def test_attendance_rules(self):
        self.register_and_login()
        sid = self.client.post("/api/students", json=self.student()).get_json()["id"]
        today = date.today().isoformat()
        future = (date.today() + timedelta(days=3)).isoformat()
        self.assertEqual(self.client.post(f"/api/students/{sid}/attendance", json={"date": today, "status": "Present"}).status_code, 201)
        self.assertEqual(self.client.post(f"/api/students/{sid}/attendance", json={"date": today, "status": "Absent"}).status_code, 409)
        self.assertEqual(self.client.post(f"/api/students/{sid}/attendance", json={"date": future, "status": "Present"}).status_code, 400)
        self.assertEqual(self.client.post(f"/api/students/{sid}/attendance", json={"date": "not-a-date", "status": "Present"}).status_code, 400)

    def test_deleting_student_removes_their_grades(self):
        self.register_and_login()
        sid = self.client.post("/api/students", json=self.student()).get_json()["id"]
        self.client.post(f"/api/students/{sid}/grades", json={"subject": "Math", "term": "Prelim", "score": 80})
        self.client.delete(f"/api/students/{sid}")
        with app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM grades").fetchone()[0], 0)

    # error pages
    def test_unknown_page_is_friendly_404(self):
        self.register_and_login()
        r = self.client.get("/nope")
        self.assertEqual(r.status_code, 404)
        self.assertIn(b"does not exist", r.data)

    def test_passwords_are_hashed(self):
        self.register_and_login()
        with app.app_context():
            stored = get_db().execute("SELECT password_hash FROM users").fetchone()[0]
        self.assertNotIn("Passw0rdX", stored)


if __name__ == "__main__":
    unittest.main()
