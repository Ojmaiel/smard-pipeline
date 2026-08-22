"""
Ad-hoc analysis of the loaded generation data.

Run with:  python analyze.py
"""

import db



DAILY_PROFILE_SQL = """
SELECT
    source,
    substr(timestamp_utc, 12, 2) AS hour,
    ROUND(AVG(value_mwh), 0)     AS avg_mwh
FROM generation
GROUP BY source, hour
ORDER BY source, hour
"""

MONTHLY_TOTALS_SQL = """
SELECT
    source,
    substr(timestamp_utc, 1, 7) AS month,
    COUNT(*) AS hours,
    ROUND(SUM(value_mwh), 0)     AS sum_mwh
FROM generation
GROUP BY source, month
ORDER BY source, month
"""

def main() -> None:
    connection = db.connect()

    rows = connection.execute(DAILY_PROFILE_SQL).fetchall()
    print(f"{len(rows)} rows returned\n")

    print(f"{'source':<14} {'hour':>4} {'avg MWh':>10}")
    print("-" * 32)
    for source, hour, avg_mwh in rows:
        # A crude bar chart. Each block is roughly 1000 MWh.
        bar = "#" * int(avg_mwh / 1000)
        print(f"{source:<14} {hour:>4} {avg_mwh:>10,.0f}  {bar}")

    rows = connection.execute(MONTHLY_TOTALS_SQL).fetchall()
    print(f"\n{len(rows)} rows returned\n")

    print(f"{'source':<14} {'month':>8} {'total MWh':>14} {'hours':>7}")
    print("-" * 48)
    for source, month, hours, sum_mwh in rows:
        print(f"{source:<14} {month:>8} {sum_mwh:>14,.0f} {hours:>7}")
    connection.close()


if __name__ == "__main__":
    main()
