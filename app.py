import os
import sqlite3

import pandas as pd
from flask import Flask, flash, redirect, render_template, request, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB = os.path.join(BASE_DIR, "student.db")

PASSING_GRADE = 75        # grade >= this is a pass
MIN_ATTENDANCE = 80       # attendance below this is flagged "at risk"

COLUMNS = [
    "student_id", "student_name", "program", "year_level",
    "subject", "semester", "school_year", "grade", "attendance_rate",
]
REQUIRED_COLUMNS = ["student_id", "student_name", "program", "grade"]


def get_conn():
    return sqlite3.connect(DB)


def create_table():
    with get_conn() as conn:
        existing = [r[1] for r in conn.execute("PRAGMA table_info(students)")]
        # Old database from the earlier 4-column version: rebuild it
        if existing and "attendance_rate" not in existing:
            conn.execute("DROP TABLE students")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS students(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            student_name TEXT,
            program TEXT,
            year_level INTEGER,
            subject TEXT,
            semester TEXT,
            school_year TEXT,
            grade REAL,
            attendance_rate REAL
        )
        """)


create_table()


@app.route("/")
def dashboard():
    conn = get_conn()
    try:
        (total_records, total_students, avg_grade, highest_grade, lowest_grade,
         pass_count, avg_attendance) = conn.execute(
            """
            SELECT COUNT(*),
                   COUNT(DISTINCT student_id),
                   ROUND(AVG(grade), 2),
                   MAX(grade),
                   MIN(grade),
                   COALESCE(SUM(CASE WHEN grade >= ? THEN 1 ELSE 0 END), 0),
                   ROUND(AVG(attendance_rate), 2)
            FROM students
            """,
            (PASSING_GRADE,),
        ).fetchone()

        programs = conn.execute(
            "SELECT program, ROUND(AVG(grade), 2) FROM students "
            "GROUP BY program ORDER BY program"
        ).fetchall()

        subjects = conn.execute(
            "SELECT subject, ROUND(AVG(grade), 2) FROM students "
            "WHERE subject IS NOT NULL GROUP BY subject ORDER BY subject"
        ).fetchall()

        year_levels = conn.execute(
            "SELECT year_level, ROUND(AVG(grade), 2) FROM students "
            "WHERE year_level IS NOT NULL GROUP BY year_level ORDER BY year_level"
        ).fetchall()

        scatter = conn.execute(
            "SELECT attendance_rate, grade FROM students "
            "WHERE attendance_rate IS NOT NULL AND grade IS NOT NULL"
        ).fetchall()

        at_risk = conn.execute(
            """
            SELECT student_id, student_name, program, subject, grade, attendance_rate
            FROM students
            WHERE grade < ? OR attendance_rate < ?
            ORDER BY grade ASC
            """,
            (PASSING_GRADE, MIN_ATTENDANCE),
        ).fetchall()

        top_students = conn.execute(
            """
            SELECT student_id, student_name, program, subject, grade
            FROM students ORDER BY grade DESC LIMIT 5
            """
        ).fetchall()
    finally:
        conn.close()

    fail_count = total_records - pass_count
    pass_rate = round(pass_count * 100.0 / total_records, 2) if total_records else 0

    chart_data = {
        "programs": {"labels": [p[0] for p in programs], "values": [p[1] for p in programs]},
        "subjects": {"labels": [s[0] for s in subjects], "values": [s[1] for s in subjects]},
        "years": {"labels": [f"Year {y[0]}" for y in year_levels], "values": [y[1] for y in year_levels]},
        "passFail": [pass_count, fail_count],
        "scatter": [{"x": a, "y": g} for a, g in scatter],
    }

    return render_template(
        "dashboard.html",
        total_records=total_records,
        total_students=total_students,
        avg_grade=avg_grade,
        highest_grade=highest_grade,
        lowest_grade=lowest_grade,
        avg_attendance=avg_attendance,
        pass_rate=pass_rate,
        at_risk=at_risk,
        top_students=top_students,
        passing_grade=PASSING_GRADE,
        min_attendance=MIN_ATTENDANCE,
        chart_data=chart_data,
    )


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == "":
            flash("Please choose a CSV file.")
            return redirect(url_for("upload"))

        try:
            df = pd.read_csv(file)
        except Exception:
            flash("Could not read that file. Make sure it is a valid CSV.")
            return redirect(url_for("upload"))

        df.columns = [str(c).strip().lower() for c in df.columns]
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            flash("Missing required column(s): " + ", ".join(missing))
            return redirect(url_for("upload"))

        # Optional columns that are absent are stored as empty values
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = None
        df = df[COLUMNS].copy()

        for col in ("grade", "attendance_rate", "year_level"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["grade"])
        df = df.astype(object).where(df.notna(), None)

        if df.empty:
            flash("No valid rows found (check that the grade column is numeric).")
            return redirect(url_for("upload"))

        with get_conn() as conn:
            conn.execute("DELETE FROM students")
            df.to_sql("students", conn, if_exists="append", index=False)

        flash(f"Imported {len(df)} records.")
        return redirect(url_for("dashboard"))

    return render_template("upload.html")


if __name__ == "__main__":
    app.run(debug=True)
