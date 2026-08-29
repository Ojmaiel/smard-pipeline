"""
Unit tests for the transformation logic.

These do not touch the network or the real database. They run in
milliseconds, so they can run on every commit.

Run with:  pytest -v
"""

import db
import fetch


# ---------------------------------------------------------------- to_rows


def test_nulls_are_dropped():
    """Unreported hours must not become rows."""
    series = [
        [1786917600000, 100.0],
        [1786921200000, None],
        [1786924800000, 300.0],
    ]
    rows = fetch.to_rows("Solar", series)

    assert len(rows) == 2
    assert all(row["value_mwh"] is not None for row in rows)


def test_zero_is_not_treated_as_null():
    """
    Zero is a real measurement — solar at night. Dropping it would be a
    serious bug, and `if not value` instead of `if value is None` would
    cause exactly that.
    """
    series = [[1786917600000, 0.0]]
    rows = fetch.to_rows("Solar", series)

    assert len(rows) == 1
    assert rows[0]["value_mwh"] == 0.0


def test_milliseconds_are_converted_correctly():
    """
    SMARD sends milliseconds. Forgetting the division by 1000 places every
    reading in 1970, which is silent and catastrophic.
    """
    series = [[1786917600000, 42.0]]
    rows = fetch.to_rows("Solar", series)

    assert rows[0]["timestamp_utc"].startswith("2026-")
    assert not rows[0]["timestamp_utc"].startswith("1970-")


def test_row_shape():
    """Column names must match what the database expects."""
    rows = fetch.to_rows("Wind Onshore", [[1786917600000, 5.0]])

    assert set(rows[0]) == {"source", "timestamp_utc", "value_mwh"}
    assert rows[0]["source"] == "Wind Onshore"


# ------------------------------------------------------------ deduplicate


def test_duplicates_are_collapsed():
    """The exact bug that once produced 868 rows instead of 602."""
    week = [
        {"source": "Solar", "timestamp_utc": f"2026-08-17 {h:02d}:00:00", "value_mwh": 1.0}
        for h in range(24)
    ]

    assert len(fetch.deduplicate(week + week)) == 24


def test_later_value_wins():
    """A revised figure must replace the earlier one, not be discarded."""
    rows = [
        {"source": "Solar", "timestamp_utc": "2026-08-17 05:00:00", "value_mwh": 100.0},
        {"source": "Solar", "timestamp_utc": "2026-08-17 05:00:00", "value_mwh": 999.0},
    ]

    assert fetch.deduplicate(rows)[0]["value_mwh"] == 999.0


def test_different_sources_are_not_merged():
    """Same hour, different source — two rows, not one."""
    rows = [
        {"source": "Solar", "timestamp_utc": "2026-08-17 05:00:00", "value_mwh": 1.0},
        {"source": "Wind Onshore", "timestamp_utc": "2026-08-17 05:00:00", "value_mwh": 2.0},
    ]

    assert len(fetch.deduplicate(rows)) == 2


# --------------------------------------------------------------- database


def make_rows(source: str, count: int) -> list[dict]:
    return [
        {
            "source": source,
            "timestamp_utc": f"2026-08-17 {h:02d}:00:00",
            "value_mwh": float(h),
        }
        for h in range(count)
    ]


def test_upsert_is_idempotent(tmp_path):
    """
    Running the pipeline twice must leave the same table as running it once.
    This is the property the whole design rests on.

    tmp_path is a pytest fixture — a fresh temporary directory per test, so
    tests never interfere with each other or with the real database.
    """
    connection = db.connect(str(tmp_path / "test.db"))
    rows = make_rows("Solar", 24)

    first = db.upsert_rows(connection, rows)
    second = db.upsert_rows(connection, rows)

    assert first["inserted"] == 24
    assert second["inserted"] == 0
    assert second["updated"] == 24
    assert db.count_rows(connection) == 24


def test_upsert_applies_revisions(tmp_path):
    """A corrected value from upstream must overwrite the stored one."""
    connection = db.connect(str(tmp_path / "test.db"))

    db.upsert_rows(connection, [
        {"source": "Solar", "timestamp_utc": "2026-08-17 05:00:00", "value_mwh": 100.0}
    ])
    db.upsert_rows(connection, [
        {"source": "Solar", "timestamp_utc": "2026-08-17 05:00:00", "value_mwh": 999.0}
    ])

    stored = connection.execute("SELECT value_mwh FROM generation").fetchone()[0]
    assert stored == 999.0
    assert db.count_rows(connection) == 1
