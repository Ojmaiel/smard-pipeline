"""
Generate charts from the loaded generation data.

Writes PNG files that the README embeds. Regenerated on every pipeline run,
so the images in the repository always reflect current data.

Run with:  python chart.py
"""

import matplotlib

# Use a non-interactive backend. Without this, matplotlib tries to open a
# window, which fails on a CI runner that has no display.
matplotlib.use("Agg")

import matplotlib.pyplot as plt

import db

DAILY_PROFILE_SQL = """
SELECT
    source,
    CAST(substr(timestamp_utc, 12, 2) AS INTEGER) AS hour,
    ROUND(AVG(value_mwh), 0) AS avg_mwh
FROM generation
GROUP BY source, hour
ORDER BY source, hour
"""

# Only complete months. A partial month would show as a false collapse at
# either end of the chart — the same trap the `hours` column exposed in the
# text report.
MONTHLY_SQL = """
SELECT
    source,
    substr(timestamp_utc, 1, 7) AS month,
    ROUND(SUM(value_mwh) / 1000000.0, 2) AS total_twh
FROM generation
GROUP BY source, month
HAVING COUNT(*) >= 672
ORDER BY month
"""

COLOURS = {"Solar": "#f5a623", "Wind Onshore": "#4a90d9"}


def group_by_source(rows: list[tuple]) -> dict:
    """Turn flat query rows into {source: (x_values, y_values)}."""
    grouped: dict[str, tuple[list, list]] = {}

    for source, x, y in rows:
        grouped.setdefault(source, ([], []))
        grouped[source][0].append(x)
        grouped[source][1].append(y)

    return grouped


def daily_profile_chart(connection, path: str = "daily_profile.png") -> None:
    """Average output by hour of day. Shows solar's curve against wind's flatness."""
    data = group_by_source(connection.execute(DAILY_PROFILE_SQL).fetchall())

    figure, axes = plt.subplots(figsize=(9, 4.5))

    for source, (hours, values) in data.items():
        axes.plot(hours, values, label=source, linewidth=2,
                  color=COLOURS.get(source))

    axes.set_title("Average generation by hour of day", fontsize=13)
    axes.set_xlabel("Hour (UTC)")
    axes.set_ylabel("Average MWh")
    axes.set_xticks(range(0, 24, 2))
    axes.grid(alpha=0.3)
    axes.legend()

    figure.tight_layout()
    figure.savefig(path, dpi=110)
    plt.close(figure)
    print(f"Wrote {path}")


def monthly_chart(connection, path: str = "monthly_totals.png") -> None:
    """Monthly totals. Shows the seasonal inversion between the two sources."""
    data = group_by_source(connection.execute(MONTHLY_SQL).fetchall())

    figure, axes = plt.subplots(figsize=(9, 4.5))

    for source, (months, values) in data.items():
        axes.plot(months, values, marker="o", label=source, linewidth=2,
                  color=COLOURS.get(source))

    axes.set_title("Monthly generation, complete months only", fontsize=13)
    axes.set_ylabel("TWh")
    axes.grid(alpha=0.3)
    axes.legend()
    plt.setp(axes.get_xticklabels(), rotation=45, ha="right")

    figure.tight_layout()
    figure.savefig(path, dpi=110)
    plt.close(figure)
    print(f"Wrote {path}")


def main() -> None:
    connection = db.connect()
    daily_profile_chart(connection)
    monthly_chart(connection)
    connection.close()


if __name__ == "__main__":
    main()
