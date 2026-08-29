"""
SQLite storage for SMARD generation data.

The point of this module is that correctness stops depending on the fetch
code being right. The table declares a primary key, so the database itself
refuses to hold the same (source, hour) twice — no matter what fetch.py does.
"""

import os
import sqlite3
from datetime import datetime, timezone

DB_FILE = os.environ.get("DB_PATH", "generation.db")

# PRIMARY KEY (source, timestamp_utc) is the whole point of this file.
# It is a composite key: neither column is unique alone, but together they
# identify exactly one measurement.
#
# loaded_at is not part of the data. It records when this row was last
# written, which is how you answer "is the pipeline still running?" and
# "when did this value last change?" without any external logging.
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS generation (
    source        TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL,
    value_mwh     REAL NOT NULL,
    loaded_at     TEXT NOT NULL,
    PRIMARY KEY (source, timestamp_utc)
)
"""

# The upsert. Try to insert; if the primary key already exists, update the
# value instead of failing. "excluded" is SQLite's name for the row that was
# being inserted when the conflict happened.
#
# This is what makes a re-run safe: hours already stored get refreshed with
# any upstream revision, new hours get added, nothing is duplicated.
UPSERT_SQL = """
INSERT INTO generation (source, timestamp_utc, value_mwh, loaded_at)
VALUES (?, ?, ?, ?)
ON CONFLICT (source, timestamp_utc) DO UPDATE SET
    value_mwh = excluded.value_mwh,
    loaded_at = excluded.loaded_at
"""


def connect(db_file: str = DB_FILE) -> sqlite3.Connection:
    """Open the database, creating the file and table if they do not exist."""
    connection = sqlite3.connect(db_file)
    connection.execute(CREATE_TABLE_SQL)
    connection.commit()
    return connection


def upsert_rows(connection: sqlite3.Connection, rows: list[dict]) -> dict:
    """
    Write rows to the database, replacing any that already exist.

    Returns counts of what changed, so a run can report whether it actually
    did anything. A pipeline that silently writes zero rows every day is a
    broken pipeline that looks healthy.
    """
    loaded_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    before = count_rows(connection)

    payload = [
        (row["source"], row["timestamp_utc"], row["value_mwh"], loaded_at)
        for row in rows
    ]

    # executemany sends the whole batch in one go. Looping with execute()
    # would work but is far slower, and matters once you load years of data.
    connection.executemany(UPSERT_SQL, payload)
    connection.commit()

    after = count_rows(connection)

    inserted = after - before
    updated = len(rows) - inserted

    return {"inserted": inserted, "updated": updated, "total": after}


def count_rows(connection: sqlite3.Connection) -> int:
    """How many measurements are stored."""
    return connection.execute("SELECT COUNT(*) FROM generation").fetchone()[0]


def summary(connection: sqlite3.Connection) -> list[tuple]:
    """
    Per-source overview: row count, time range, average output.

    This is the first real SQL in the project. GROUP BY collapses many rows
    into one row per source; the aggregate functions describe each group.
    """
    query = """
    SELECT
        source,
        COUNT(*)          AS hours,
        MIN(timestamp_utc) AS first_hour,
        MAX(timestamp_utc) AS last_hour,
        ROUND(AVG(value_mwh), 1) AS avg_mwh
    FROM generation
    GROUP BY source
    ORDER BY source
    """
    return connection.execute(query).fetchall()
