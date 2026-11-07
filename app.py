
import os
import sqlite3
import logging
from contextlib import closing

import pandas as pd
from flask import (
    Flask, flash, redirect, render_template,
    request, url_for
)

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY", "change-me-in-production"
)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Vercel has a read-only application filesystem.
# /tmp is writable, but its data is temporary.
if os.environ.get("VERCEL"):
    DB = "/tmp/student.db"
else:
    DB = os.path.join(BASE_DIR, "student.db")

PASSING_GRADE = 75
MIN_ATTENDANCE = 80

COLUMNS = [
    "student_id",
    "student_name",
    "program",
    "year_level",
    "subject",
    "semester",
    "school_year",
    "grade",
    "attendance_rate",
]

REQUIRED_COLUMNS = [
    "student_id",
    "student_name",
    "program",
    "grade",
]


def get_conn():
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def create_table():
    with closing(get_conn()) as conn:
        with conn:
            existing = [
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(students)"
                )
            ]

            if existing and "attendance_rate" not in existing:
                conn.execute("DROP TABLE students")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS students (
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


# Initialize database when the application starts.
create_table()


@app.route("/")
def dashboard():
    with closing(get_conn()) as conn:

        (
            total_records,
            total_students,
            avg_grade,
            highest_grade,
            lowest_grade,
            pass_count,
            avg_attendance,
        ) = conn.execute("""
            SELECT
                COUNT(*),
                COUNT(DISTINCT student_id),
                ROUND(AVG(grade), 2),
                MAX(grade),
                MIN(grade),
                COALESCE(
                    SUM(CASE WHEN grade >= ? THEN 1 ELSE 0 END),
                    0
                ),
                ROUND(AVG(attendance_rate), 2)
            FROM students
        """, (PASSING_GRADE,)).fetchone()

        programs = conn.execute("""
            SELECT program, ROUND(AVG(grade), 2)
            FROM students
            GROUP BY program
            ORDER BY program
        """).fetchall()

        subjects = conn.execute("""
            SELECT subject, ROUND(AVG(grade), 2)
            FROM students
            WHERE subject IS NOT NULL
            GROUP BY subject
            ORDER BY subject
        """).fetchall()

        year_levels = conn.execute("""
            SELECT year_level, ROUND(AVG(grade), 2)
            FROM students
            WHERE year_level IS NOT NULL
            GROUP BY year_level
            ORDER BY year_level
        """).fetchall()

        scatter = conn.execute("""
            SELECT attendance_rate, grade
            FROM students
            WHERE attendance_rate IS NOT NULL
              AND grade IS NOT NULL
        """).fetchall()

        at_risk = conn.execute("""
            SELECT
                student_id,
                student_name,
                program,
                subject,
                grade,
                attendance_rate
            FROM students
            WHERE grade < ? OR attendance_rate < ?
            ORDER BY grade ASC
        """, (PASSING_GRADE, MIN_ATTENDANCE)).fetchall()

        top_students = conn.execute("""
            SELECT
                student_id,
                student_name,
                program,
                subject,
                grade
            FROM students
            ORDER BY grade DESC
            LIMIT 5
        """).fetchall()

    fail_count = total_records - pass_count

    pass_rate = (
        round(pass_count * 100.0 / total_records, 2)
        if total_records else 0
    )

    chart_data = {
        "programs": {
            "labels": [p["program"] for p in programs],
            "values": [p[1] for p in programs],
        },
        "subjects": {
            "labels": [s["subject"] for s in subjects],
            "values": [s[1] for s in subjects],
        },
        "years": {
            "labels": [f"Year {y['year_level']}" for y in year_levels],
            "values": [y[1] for y in year_levels],
        },
        "passFail": [pass_count, fail_count],
        "scatter": [
            {"x": row["attendance_rate"], "y": row["grade"]}
            for row in scatter
        ],
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

        if not file or not file.filename:
            flash("Please choose a CSV file.")
            return redirect(url_for("upload"))

        if not file.filename.lower().endswith(".csv"):
            flash("Only CSV files are supported.")
            return redirect(url_for("upload"))

        try:
            # Read CSV
            df = pd.read_csv(file)

            if df.empty:
                flash("The uploaded CSV file is empty.")
                return redirect(url_for("upload"))

            # Normalize column names
            df.columns = [
                str(column).strip().lower()
                for column in df.columns
            ]

            if len(set(df.columns)) != len(df.columns):
                flash("Your CSV contains duplicate column names.")
                return redirect(url_for("upload"))

            # Validate required columns
            missing = [
                column
                for column in REQUIRED_COLUMNS
                if column not in df.columns
            ]

            if missing:
                flash(
                    "Missing required columns: "
                    + ", ".join(missing)
                )
                return redirect(url_for("upload"))

            # Add optional columns
            for column in COLUMNS:
                if column not in df.columns:
                    df[column] = None

            df = df[COLUMNS].copy()

            # Convert numeric columns
            for column in [
                "grade",
                "attendance_rate",
                "year_level",
            ]:
                df[column] = pd.to_numeric(
                    df[column],
                    errors="coerce"
                )

            # Remove rows without valid grades
            df = df.dropna(subset=["grade"])

            if df.empty:
                flash(
                    "No valid student records found. "
                    "Check the grade column."
                )
                return redirect(url_for("upload"))

            # Convert missing values to SQLite-compatible None
            df = df.astype(object).where(pd.notna(df), None)

            records = []

            for row in df.itertuples(index=False, name=None):
                clean_row = tuple(
                    value.item()
                    if hasattr(value, "item")
                    else value
                    for value in row
                )
                records.append(clean_row)

            placeholders = ", ".join(["?"] * len(COLUMNS))
            column_names = ", ".join(COLUMNS)

            insert_query = f"""
                INSERT INTO students ({column_names})
                VALUES ({placeholders})
            """

            # Import records in one database transaction
            with closing(get_conn()) as conn:
                with conn:
                    conn.execute("DELETE FROM students")
                    conn.executemany(insert_query, records)

            flash(f"Successfully imported {len(records)} student records.")

            return redirect(url_for("dashboard"))

        except pd.errors.EmptyDataError:
            flash("The uploaded CSV file has no data.")

        except pd.errors.ParserError:
            flash("Invalid CSV format. Please check your file.")

        except Exception:
            logging.exception("CSV upload failed")
            flash(
                "Upload failed because of a server error. "
                "Please check the Vercel Runtime Logs."
            )

        return redirect(url_for("upload"))

    return render_template("upload.html")


@app.errorhandler(413)
def file_too_large(error):
    flash("File is too large. Maximum allowed size is 10 MB.")
    return redirect(url_for("upload"))


if __name__ == "__main__":
    app.run(debug=True)
