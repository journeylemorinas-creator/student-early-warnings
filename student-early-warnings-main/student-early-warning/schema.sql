-- Database schema for the Student Performance Early-Warning System (SQLite)
-- Safe to run more than once: every statement uses IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    full_name     TEXT    NOT NULL,
    password_hash TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS students (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_no TEXT    NOT NULL UNIQUE,
    first_name TEXT    NOT NULL,
    last_name  TEXT    NOT NULL,
    course     TEXT    NOT NULL,
    year_level INTEGER NOT NULL CHECK (year_level BETWEEN 1 AND 6),
    email      TEXT,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS grades (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    subject    TEXT    NOT NULL,
    term       TEXT    NOT NULL CHECK (term IN ('Prelim', 'Midterm', 'Finals')),
    score      REAL    NOT NULL CHECK (score BETWEEN 0 AND 100),
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS attendance (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    date       TEXT    NOT NULL,
    status     TEXT    NOT NULL CHECK (status IN ('Present', 'Late', 'Absent', 'Excused')),
    UNIQUE (student_id, date)
);

CREATE INDEX IF NOT EXISTS idx_grades_student     ON grades(student_id);
CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance(student_id);
