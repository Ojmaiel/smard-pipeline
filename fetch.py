"""
Fetch German electricity generation data from SMARD (Bundesnetzagentur).

Step 1 of the pipeline: just get data out of the API and look at it.
No database, no cloud, no Docker yet.
"""

from datetime import datetime, timezone

import requests

# SMARD filter IDs — each one is a generation source.
# 4068 = Photovoltaik (solar)
# 4067 = Wind Onshore
# 1225 = Wind Offshore
# 4071 = Erdgas (natural gas)
# 1223 = Braunkohle (lignite)
#ILTER_SOLAR = 4068
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


def format_row(row: list) -> str:
    """Turn one [timestamp_ms, value] pair into something a human can read."""
    timestamp_ms, value = row

    # SMARD gives MILLISECONDS since 1970. Python's fromtimestamp expects
    # SECONDS. Forget the division by 1000 and every date lands in 1970.
    moment = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

    readable_value = "NULL" if value is None else f"{value:,.0f} MWh"
    return f"{moment:%Y-%m-%d %H:%M} UTC   {readable_value}"


def main() -> None:
    for name, filter_id in SOURCES.items():

        timestamps = get_available_timestamps(filter_id, REGION, RESOLUTION)
        print(f"\nSMARD offers {len(timestamps)} weekly files.")

        # The last one is the most recent week, i.e. the freshest data.
        latest = timestamps[-1]
        print(f"Newest file starts at {datetime.fromtimestamp(latest / 1000, tz=timezone.utc)}\n")

        series = get_timeseries(filter_id, REGION, RESOLUTION, latest)

        null_count = sum(1 for _, value in series if value is None)
        print(f"\nGot {len(series)} data points, of which {null_count} are NULL.")
        print("NULLs are hours SMARD has not reported yet — normal, not a bug.\n")

        print("--- first 3 ---")
        for row in series[:3]:
            print(format_row(row))

        print("\n--- last 3 ---")
        for row in series[-3:]:
            print(format_row(row))


if __name__ == "__main__":
    main()
