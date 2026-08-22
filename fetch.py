"""
Fetch German electricity generation data from SMARD (Bundesnetzagentur).

Step 2 of the pipeline: fetch several sources, turn the raw API response
into clean rows, and write them to a CSV file.

Still no database, no cloud, no Docker.
"""

import csv
from datetime import datetime, timezone

import requests

# SMARD filter IDs — each one is a generation source.
# 1225 = Wind Offshore, 4071 = Erdgas, 1223 = Braunkohle (add later if you want)
SOURCES = {
    "Solar": 4068,
    "Wind Onshore": 4067,
}

REGION = "DE"
RESOLUTION = "hour"

BASE_URL = "https://www.smard.de/app/chart_data"

# Always set a timeout. A request without one can hang forever,
# which in a scheduled pipeline means a job that never finishes.
TIMEOUT_SECONDS = 30

OUTPUT_FILE = "generation.csv"

# The column order of the output file. Defining it in one place means
# to_rows() and the CSV writer can never drift apart.
FIELDNAMES = ["source", "timestamp_utc", "value_mwh"]


def get_available_timestamps(filter_id: int, region: str, resolution: str) -> list[int]:
    """
    Ask SMARD which time series files exist.

    Returns a list of Unix timestamps in MILLISECONDS. Each one is the
    start of a weekly file — SMARD splits the data into week-sized chunks.
    """
    url = f"{BASE_URL}/{filter_id}/{region}/index_{resolution}.json"
    print(f"GET {url}")

    response = requests.get(url, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()  # turn a 404/500 into a loud error, not silent bad data

    payload = response.json()
    return payload["timestamps"]


def get_timeseries(
    filter_id: int, region: str, resolution: str, timestamp: int
) -> list[list]:
    """
    Fetch one weekly file of actual measurements.

    Note the ugly URL: the filter and region appear TWICE. That is not a
    mistake on your side — the API really is designed that way.

    Returns a list of [timestamp_ms, value] pairs. value can be None.
    """
    url = (
        f"{BASE_URL}/{filter_id}/{region}/"
        f"{filter_id}_{region}_{resolution}_{timestamp}.json"
    )
    print(f"GET {url}")

    response = requests.get(url, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()

    payload = response.json()
    return payload["series"]


def to_rows(name: str, series: list[list]) -> list[dict]:
    """
    Convert one source's raw [timestamp_ms, value] pairs into clean rows.

    Output is LONG format: one row per source per hour. Adding a third
    source later means more rows, not a schema change.

    DECISION — NULLs are dropped, not stored.
    A NULL here means "SMARD has not reported this hour yet", which is not
    the same as "zero electricity was generated". Writing it would create a
    row that has to be corrected on a later run. Dropping it means tomorrow's
    run simply adds the hours that have since been reported, and every row in
    the file is always a real measurement. The cost: the file alone cannot
    tell you whether an hour is missing because it lies in the future or
    because the pipeline failed. Acceptable for now, revisit at the DB stage.
    """
    rows = []

    for timestamp_ms, value in series:
        if value is None:
            continue

        # SMARD gives MILLISECONDS since 1970. Python expects SECONDS.
        # Forget the division by 1000 and every date lands in 1970.
        moment = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

        rows.append(
            {
                "source": name,
                "timestamp_utc": moment.strftime("%Y-%m-%d %H:%M:%S"),
                "value_mwh": float(value),
            }
        )

    return rows


def write_csv(rows: list[dict], path: str) -> None:
    """
    Write rows to a CSV file.

    newline="" is required on Windows. Without it, Python and the csv module
    each add a line ending and you get a blank line between every row.

    encoding="utf-8" keeps German characters intact if you later add source
    names like "Braunkohle" or any label with an umlaut.
    """
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    all_rows = []

    for name, filter_id in SOURCES.items():
        print(f"\n===== {name} =====")

        timestamps = get_available_timestamps(filter_id, REGION, RESOLUTION)

        # The last one is the most recent week, i.e. the freshest data.
        latest = timestamps[-1]
        series = get_timeseries(filter_id, REGION, RESOLUTION, latest)

        rows = to_rows(name, series)
        dropped = len(series) - len(rows)
        print(f"{len(rows)} usable rows, {dropped} unreported hours skipped")

        all_rows.extend(rows)

    write_csv(all_rows, OUTPUT_FILE)
    print(f"\nWrote {len(all_rows)} rows to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()