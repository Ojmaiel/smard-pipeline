# SMARD Pipeline

Fetches hourly electricity generation data for Germany from
[SMARD](https://www.smard.de), the Bundesnetzagentur's official electricity
market data platform, and writes it to a flat CSV file.

Currently covers solar and onshore wind for the two most recent weeks.

## Data source

SMARD does not publish a formal API. The website uses internal JSON endpoints
to render its charts, documented by the community
[bundesAPI/smard-api](https://github.com/bundesAPI/smard-api) project. No API
key and no authentication are required.

Two endpoints are used:

| Purpose | Endpoint |
|---|---|
| Which weeks exist | `/chart_data/{filter}/{region}/index_{resolution}.json` |
| One week of data | `/chart_data/{filter}/{region}/{filter}_{region}_{resolution}_{timestamp}.json` |

Because the endpoints are undocumented, they can change without notice.

## Running it

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
python fetch.py
```

Output is written to `generation.csv` in the project directory.

## Output schema

Long format — one row per source per hour. Adding a new generation source
produces more rows, not a schema change.

| Column | Type | Example |
|---|---|---|
| `source` | string | `Solar` |
| `timestamp_utc` | string | `2026-08-17 11:00:00` |
| `value_mwh` | float | `28451.5` |

## Notes on the data

**Timestamps are Unix milliseconds, not seconds.** Dividing by 1000 before
converting is required; skipping it silently places every reading in 1970.

**All timestamps are UTC.** German local time is UTC+1 in winter and UTC+2 in
summer, so the hour shown here will not match a German clock. Converting is
left to the consumer, deliberately — storing UTC avoids ambiguity during the
daylight saving changeover, when one local hour occurs twice.

**`null` means unreported, not zero.** SMARD returns `null` for hours it has
not yet published, which is normal for the current week. These rows are
dropped rather than stored as zero, since zero generation and no measurement
are different facts. The trade-off is that a missing hour in the output cannot
be distinguished from a failed run — acceptable while the target is a flat
file, worth revisiting once the data lands in a database.

**Published values can be revised.** Figures for recent hours are preliminary
and may be corrected later. Each run therefore re-fetches whole weeks and
replaces them rather than appending only new rows.

**Solar is zero overnight.** A useful sanity check: if solar generation is
non-zero at 02:00 UTC, either the filter ID or the timestamp handling is wrong.

## Roadmap

- [ ] Deduplicate on `(source, timestamp_utc)` in code
- [ ] Load into SQLite with a primary key enforcing that constraint
- [ ] Containerise with Docker
- [ ] Schedule daily runs via GitHub Actions
- [ ] Move storage to BigQuery, transformations to SQL
