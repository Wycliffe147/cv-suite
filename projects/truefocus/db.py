"""
projects/truefocus/db.py
-------------------------
SQLite persistence for TrueFocus attention sessions and metrics.
Stored in data/logs/truefocus.db
"""

import sqlite3
from pathlib import Path
from datetime import datetime, date
from typing import Dict, Any, List, Optional

DB_PATH = Path(__file__).parents[2] / "data" / "logs" / "truefocus.db"


def init_db(db_path: Path = DB_PATH) -> None:
    """Initialize SQLite tables for time tracking."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS focus_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                duration_seconds REAL NOT NULL,
                state TEXT NOT NULL -- 'FOCUSED', 'DISTRACTED', 'AWAY'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_summaries (
                date TEXT PRIMARY KEY,
                focused_seconds REAL DEFAULT 0,
                distracted_seconds REAL DEFAULT 0,
                away_seconds REAL DEFAULT 0,
                breaks_taken INTEGER DEFAULT 0
            )
        """)
        conn.commit()


def log_interval(state: str, duration: float, db_path: Path = DB_PATH) -> None:
    """Record an interval in the focus_log table and update daily summary."""
    now_iso = datetime.now().isoformat()
    today_str = date.today().isoformat()

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO focus_log (timestamp, duration_seconds, state) VALUES (?, ?, ?)",
            (now_iso, duration, state)
        )

        column_map = {
            "FOCUSED": "focused_seconds",
            "DISTRACTED": "distracted_seconds",
            "AWAY": "away_seconds",
        }
        col = column_map.get(state)
        if col:
            cursor.execute(f"""
                INSERT INTO daily_summaries (date, {col})
                VALUES (?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    {col} = {col} + ?
            """, (today_str, duration, duration))
        conn.commit()


def get_daily_summary(day: Optional[date] = None, db_path: Path = DB_PATH) -> Dict[str, Any]:
    """Retrieve aggregate stats for a specific date (defaults to today)."""
    day_str = (day or date.today()).isoformat()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT focused_seconds, distracted_seconds, away_seconds, breaks_taken FROM daily_summaries WHERE date = ?",
            (day_str,)
        )
        row = cursor.fetchone()
        if not row:
            return {
                "date": day_str,
                "focused_seconds": 0.0,
                "distracted_seconds": 0.0,
                "away_seconds": 0.0,
                "breaks_taken": 0,
            }
        return {
            "date": day_str,
            "focused_seconds": row[0],
            "distracted_seconds": row[1],
            "away_seconds": row[2],
            "breaks_taken": row[3],
        }


def record_break(day: Optional[date] = None, db_path: Path = DB_PATH) -> None:
    """Increment the break counter for today."""
    day_str = (day or date.today()).isoformat()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO daily_summaries (date, breaks_taken)
            VALUES (?, 1)
            ON CONFLICT(date) DO UPDATE SET
                breaks_taken = breaks_taken + 1
        """, (day_str,))
        conn.commit()
