# SMARD Pipeline

Fetches hourly electricity generation data for Germany from
[SMARD](https://www.smard.de), the Bundesnetzagentur's official electricity
market data platform, loads it into SQLite, and reports on it.

Currently covers solar and onshore wind over the most recent 52 weeks —
roughly 17,400 hourly measurements.

## Data source

SMARD does not publish a formal API. The website uses internal JSON endpoints
to render its charts, documented by the community
[bundesAPI/smard-api](https://github.com/bundesAPI/smard-api) project. No API
key and no authentication are required.

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

python fetch.py       # fetch, load into SQLite, export CSV
python analyze.py     # report on what is loaded
```

## Project layout

| File | Purpose |
|---|---|
| `fetch.py` | Calls the API, cleans the response, writes to the database |
| `db.py` | Schema, connection, upsert, summary queries |
| `analyze.py` | Read-only analysis queries |

## Schema

One table, `generation`, in long format — one row per source per hour. Adding
a new generation source produces more rows, not a schema change.

| Column | Type | Notes |
|---|---|---|
| `source` | TEXT | e.g. `Solar`, part of the primary key |
| `timestamp_utc` | TEXT | `YYYY-MM-DD HH:MM:SS`, part of the primary key |
| `value_mwh` | REAL | Generation during that hour |
| `loaded_at` | TEXT | When this row was last written |

`PRIMARY KEY (source, timestamp_utc)` is the core design decision. Writes use
`INSERT ... ON CONFLICT DO UPDATE`, so a re-run refreshes existing hours
instead of duplicating them. Running the pipeline once or five times produces
the same table.

`loaded_at` is not part of the measurement. It exists so that "did the
pipeline run today?" and "when did this value last change?" can be answered
without a separate logging system.

## Design decisions

**Timestamps are stored in UTC, not German local time.** SMARD returns Unix
milliseconds; dividing by 1000 before converting is required. Storing local
time would break twice a year at the daylight saving changeover — the October
switch repeats one local hour, which under a `(source, timestamp)` key would
silently overwrite a real measurement. The row counts below confirm this: every
complete month contains exactly 24 × its number of days, with no 23- or
25-hour anomalies.

**`null` means unreported, not zero.** SMARD returns `null` for hours it has
not yet published, normal for the current week. These are dropped rather than
stored as zero, since zero generation and no measurement are different facts.
Trade-off: a missing hour cannot be distinguished from a failed run. The
`hours` column in the monthly report exposes this instead of hiding it.

**Published values can be revised.** Figures for recent hours are preliminary.
Each run re-fetches whole weeks and upserts them, so corrections are picked up
automatically.

**Deduplication happens in code and is enforced in the database.** The code
collapses duplicate keys and warns when it finds any, since duplicates
indicate a bug in the fetch loop rather than bad upstream data. The primary
key then makes duplicates structurally impossible regardless.

## Findings

From 12 complete months of data:

- **Solar swings roughly 8× across the year** — about 1.5 TWh in December
  against 12.0 TWh in July.
- **Wind runs counter to it**, strongest in autumn and winter (13.7 TWh in
  October, 13.0 in January) and weakest in late spring (5.5 TWh in May).
- **The two are anti-correlated**, which is the physical argument for building
  both rather than either alone.
- **Solar peaks near 11:00 UTC**, not 12:00, because German summer time is
  UTC+2 — a useful check that the timestamp handling is correct.
- **Solar is exactly zero overnight.** Non-zero generation at 02:00 UTC would
  mean the filter ID or the timestamp conversion is wrong.

## Sanity checks

Cheap checks worth running after any change:

- Solar generation at night must be zero.
- A complete month must contain exactly 24 × days hours.
- A second identical run must insert 0 rows and update the rest.

## Roadmap

- [x] Deduplicate on `(source, timestamp_utc)` in code
- [x] Load into SQLite with a primary key enforcing that constraint
- [ ] Containerise with Docker
- [ ] Schedule daily runs via GitHub Actions
- [ ] Move storage to BigQuery, transformations to SQL
