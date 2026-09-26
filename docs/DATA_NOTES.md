# Data Notes

Source-specific facts, verification status, and field mappings. Update this file whenever something is confirmed or changes.

Status legend: **Verified** (checked against the live source, with date) · **To verify** · **Assumption**

## Primary source: BTS Airline On-Time Performance

- **Publisher:** U.S. Department of Transportation, Bureau of Transportation Statistics (BTS), via TranStats
- **Database page:** https://transtats.bts.gov/DatabaseInfo.asp?QO_VQ=EFD
- **Coverage (per BTS):** scheduled and actual departure and arrival times reported by certified U.S. air carriers that account for at least half of one percent of domestic scheduled passenger revenues. Non-stop domestic flights. Includes cancellations, diversions, taxi times, delay causes, air time, and distance.
- **Tables of interest:**
  - *Reporting Carrier On-Time Performance (1987–present)*: flights reported by the carrier that operated them.
  - *Marketing carrier on-time table*: on-time data by marketing network, marketing carrier, and regional code-share group. Likely closer to the flight numbers travelers search for.
- **Cadence:** monthly, published after the month closes (the monthly Air Travel Consumer Report typically covers a month that ended weeks earlier).
- **Rights:** U.S. federal government data. Confirm the data.gov or BTS terms page and record the result here.
- **Attribution text for pages:** "Source: U.S. Department of Transportation, Bureau of Transportation Statistics."

### Verification status

**Verified 2026-09-26** for the reporting carrier table, from the owner's machine,
by `verify-source --month 2025-01`. The record is
`data/verification/bts_ontime_reporting_carrier.json`; `ingest` now runs.

Reachability note: `https://transtats.bts.gov/` (the site root) and
`www.transtats.bts.gov` time out from here, and `www.bts.gov` returns 403 to curl,
but `https://transtats.bts.gov/PREZIP/` answers normally and serves a plain
directory listing. A timeout on the root does not mean the downloads are down.

### Verified 2026-09-26 · bts_ontime_reporting_carrier

- **URL template:** `https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip` (month not zero-padded). The second candidate in `URL_CANDIDATES` was never needed.
- **Available months (PREZIP listing, 2026-09-26):** 1987-10 .. 2026-07.
- **Checked with month:** 2025-01 (27,108,664 bytes, sha256 `868387dcedaef1b8…`, `Last-Modified: Thu, 08 May 2025`; an ETag is sent, so conditional GETs work)
- **Archive members:** `On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2025_1.csv`, `readme.html` (BTS's field glossary)
- **Delimiter:** `,` · **Encoding:** `utf-8-sig` · **Columns in source:** 110
- **Mapped:** 24 · **Missing required:** 0 · **Missing optional:** 0. Every column in the mapping below exists under exactly that name.
- **Row count:** 539,747 CSV data rows = 539,747 Parquet rows = `sum(Flights)`. Re-normalizing the same raw file gives the same rows; the Parquet bytes differ only because `ingested_at` is stamped at normalize time (lineage, read by no export).

Field meanings, from the bundled `readme.html` and checked against the 2025-01 rows:

| Question | Answer | Evidence |
|---|---|---|
| Time fields | Local time, `hhmm` string, zero-padded to 4 characters (`0005`) | readme; min/max length 4 |
| `2400` | Never in scheduled times (`CRSDepTime`/`CRSArrTime` run `0001`..`2359`); **does** occur in actual times (33 `DepTime`, 245 `ArrTime` in 2025-01) | data. Anything doing arithmetic on actual times (the M7 connection checker) must treat `2400` as midnight ending that day |
| `DepDelayMinutes`, `ArrDelayMinutes` | Early is set to 0 | readme |
| Cancelled flights | `ArrDel15`, `ArrTime`, `ArrDelayMinutes` and all cause columns null | data: 16,312 rows, none non-null |
| Diverted flights | `ArrDel15`, `ArrDelayMinutes` and causes null; `ArrTime` populated on 898 of 1,166 (the readme says `ArrDelay` stays null for diversions and the scheduled-destination figure is in `DivArrDelay`) | data + readme |
| Delay-cause columns | Populated exactly when an operated flight has `ArrDel15 = 1` (98,130 of 98,130), null otherwise; the five causes sum to `ArrDelayMinutes` on every such row | data |
| `CancellationCode` | `A`..`D` present (A 1,635 · B 14,327 · C 342 · D 8). The readme says only "reason for cancellation"; the letter meanings come from BTS's lookup table, **not yet downloaded** | data |
| `Reporting_Airline` | BTS's *unique* carrier code: when a code has had several holders, earlier ones get a suffix (`PA(1)`). Distinct from `IATA_CODE_Reporting_Airline` | readme |
| `DOT_ID_Reporting_Airline` | One ID per DOT certificate, independent of code, name or holding company | readme |

2025-01 has 14 reporting carriers: AA AS B6 DL F9 G4 HA MQ NK OH OO UA WN YX.

### Verified 2026-09-26 · bts_ontime_marketing_carrier

Verified by `verify-source --month 2025-01 --source bts_ontime_marketing_carrier`;
the record is `data/verification/bts_ontime_marketing_carrier.json`. 27 columns
mapped, none missing. The canonical schema (`MARKETING_FIELDS` in
`pipeline/models/schema.py`) is the reporting one with `carrier`, `carrier_id` and
`flight_number` taken from the marketing columns, plus `operating_carrier`,
`operating_carrier_id` and `operating_flight_number`. It feeds flight, route and
airport pages; the reporting table feeds airline pages only (DECISIONS.md
2026-09-26).

- **URL pattern:** `https://transtats.bts.gov/PREZIP/On_Time_Marketing_Carrier_On_Time_Performance_Beginning_January_2018_{year}_{month}.zip`, months 2018-01 .. 2026-07. 2025-01 is 31,599,374 bytes.
- **CSV member:** `On_Time_Marketing_Carrier_On_Time_Performance_(Beginning_January_2018)_2025_1.csv`, plus `readme.html`. 119 named columns and a trailing comma (DuckDB reports an empty 120th, `column119`).
- **Header gotcha:** the operating carrier column is `"Operating_Airline "` **with a trailing space**. DuckDB trims it to `Operating_Airline`; Python's `csv` module does not.
- **Per row:** `Marketing_Airline_Network`, `DOT_ID_Marketing_Airline`, `IATA_Code_Marketing_Airline`, `Flight_Number_Marketing_Airline`, `Operated_or_Branded_Code_Share_Partners`, `Operating_Airline`, `DOT_ID_Operating_Airline`, `IATA_Code_Operating_Airline`, `Flight_Number_Operating_Airline`, `Originally_Scheduled_Code_Share_Airline` (with its ID, IATA code and flight number), a `Duplicate` flag, and the same timing, status, delay-cause and distance columns as the reporting table.
- **One marketing carrier per row.** It is the network brand (10 in 2025-01: AA AS B6 DL F9 G4 HA NK UA WN), not a list of every codeshare partner. A ticket sold under a foreign partner's code will not be found here.
- **The marketing flight number equals the operating one** on 195,084 of the 195,119 rows where the two carriers differ; 35 differ.
- **It is a superset of the reporting table, not a relabelling.** 599,013 rows vs 539,747, with no duplicates (`Duplicate = 'N'` on every row, and the operating-carrier key is unique). Joined on date + operating carrier + operating flight number + origin + dest + scheduled departure:
  - 59,282 marketing rows have no reporting row. 59,259 of them (about 10% of all flights) are by seven regional operators that do not report to BTS themselves: 9E 18,279 · PT 10,621 · QX 7,754 · YV 6,628 · C5 6,612 · G7 5,575 · ZW 3,790. The other 23 are on reporting carriers (YX, MQ, OH, OO) and are **not explained**.
  - 16 reporting rows have no marketing row, **not explained**.
  - Scheduled departure never disagrees on a matched pair, so it adds nothing to the key.
  - The two are separate filings: over the carriers both tables cover, cancellations are 16,296 (marketing) vs 16,312 (reporting) and `ArrDel15 = 1` is 98,144 vs 98,130.
- **Codes:** `Marketing_Airline_Network` equals `IATA_Code_Marketing_Airline` for all 10 brands in 2025-01, and `Operating_Airline` equals `IATA_Code_Operating_Airline` for all 21 operators. `Operated_or_Branded_Code_Share_Partners` is the brand, suffixed `_CODESHARE` when a partner operates it (`DL_CODESHARE`). `Originally_Scheduled_Code_Share_Airline` is set on 41 rows only.
- **Keys:** (date, marketing carrier, marketing flight number, origin, dest) is unique across all 599,013 rows. Marketing and operating flight numbers can differ: DL 3860 flown by 9E as 5538.
- Consequence: joining the marketing table *onto* the reporting table would drop every flight by those seven operators. Decided instead: the marketing table feeds flight, route and airport pages, the reporting table airline pages only (DECISIONS.md 2026-09-26).

### Verification checklist (M1)

- [x] Current bulk download method (prezipped monthly files vs field-selection download). Community tools commonly reference a prezipped monthly file pattern on transtats.bts.gov; **confirm the exact URL on the live site before coding against it.**
- [x] File format, delimiter, encoding, header names
- [x] Column list and types for the chosen table
- [x] Meaning of time fields (local time, `hhmm` format, handling of `2400`)
- [x] How cancelled and diverted flights populate delay fields
- [x] When delay-cause columns are populated
- [x] Reporting vs marketing carrier: which one carries the flight number a traveler would search (for example, a regional flight sold under a mainline code). *Decided 2026-09-26: flight pages use the marketing carrier, airline stats the reporting carrier (DECISIONS.md). Confirmed 2026-09-26 that each marketing-table row carries both, but the table is a superset of the reporting table (see above).*
- [ ] BTS unique carrier identifiers and how code reuse is handled (BTS notes that carrier codes and names can change or be reused, and provides unique IDs for that reason)
- [ ] Lookup tables for airports and carriers, and where to download them
- [ ] A published monthly on-time figure to reproduce for validation (M2)
- [ ] Rate or usage guidance for automated downloads

### Loaded: 2023-08 .. 2026-07 (36 months, both tables, 2026-09-26)

- 22,924,918 marketing rows; 500k-630k reporting rows a month. Nothing failed;
  every month's Parquet row count equals its CSV row count.
- 2.2 GB of raw zips (about 27 MB + 32 MB a month) and 410 MB of Parquet.
- The marketing table's surplus grows from about 6% (2023-24) to about 10%
  (2025 on), because the set of reporting carriers shrank. Observed, with the
  cause not checked against BTS:

| Year | Reporting carriers | Operators in the marketing table that do not report |
|---|---|---|
| 2023, 2024 | 9E AA AS B6 DL F9 G4 HA MQ NK OH OO UA WN YX | C5 G7 PT QX YV ZW |
| 2025 | the same, less 9E (last reporting day 2024-12-31) | 9E C5 G7 PT QX YV ZW |
| 2026 (to July) | the same, less HA | 9E C5 G7 PT QX YV |

- **HA disappears from both tables after 2025-12-31**, as a marketing brand and
  as an operator. **ZW has no 2026 flights** in either. Why is not recorded
  here; check BTS before writing anything about it on a page.

### Field mapping (verified 2026-09-26 against 2025-01)

This table is the reporting carrier mapping. The marketing mapping differs only in
flight identity; see the marketing table section above and `MARKETING_FIELDS`.

This is the hypothesis `verify-source` tests, mirroring
`pipeline/models/schema.py`. A required column that turns out not to exist fails
verification and blocks ingest; an optional one becomes a typed NULL. The
canonical schema is fingerprinted, so editing this mapping invalidates an old
verification record and forces a re-check.

| Canonical field | Candidate source column | Type | Required | Notes |
|---|---|---|---|---|
| `flight_date` | `FlightDate` | DATE | yes | Local date of scheduled departure |
| `carrier` | `Reporting_Airline` | VARCHAR | yes | Reporting (operating) carrier |
| `carrier_id` | `DOT_ID_Reporting_Airline` | INTEGER | yes | BTS unique ID; stable across code reuse |
| `flight_number` | `Flight_Number_Reporting_Airline` | VARCHAR | yes | |
| `origin` | `Origin` | VARCHAR | yes | |
| `origin_airport_id` | `OriginAirportID` | INTEGER | yes | |
| `dest` | `Dest` | VARCHAR | yes | |
| `dest_airport_id` | `DestAirportID` | INTEGER | yes | |
| `sched_dep` | `CRSDepTime` | VARCHAR | yes | Stored as reported; hhmm, `2400` possible |
| `actual_dep` | `DepTime` | VARCHAR | no | Null when cancelled |
| `sched_arr` | `CRSArrTime` | VARCHAR | yes | Stored as reported |
| `actual_arr` | `ArrTime` | VARCHAR | no | Null when cancelled or diverted |
| `dep_delay_min` | `DepDelayMinutes` | DOUBLE | no | Early counts as 0, not negative |
| `arr_delay_min` | `ArrDelayMinutes` | DOUBLE | no | |
| `arr_del15` | `ArrDel15` | DOUBLE | no | 1.0 when 15+ min late |
| `cancelled` | `Cancelled` | DOUBLE | yes | |
| `cancellation_code` | `CancellationCode` | VARCHAR | no | |
| `diverted` | `Diverted` | DOUBLE | yes | |
| `carrier_delay` | `CarrierDelay` | DOUBLE | no | Only for qualifying delays |
| `weather_delay` | `WeatherDelay` | DOUBLE | no | |
| `nas_delay` | `NASDelay` | DOUBLE | no | |
| `security_delay` | `SecurityDelay` | DOUBLE | no | |
| `late_aircraft_delay` | `LateAircraftDelay` | DOUBLE | no | |
| `distance` | `Distance` | DOUBLE | no | Miles |

Plus two lineage columns the normalizer adds: `source_file`, `ingested_at`.

### Assumptions currently baked into the metrics layer

These are transformations, not source facts. Each needs confirming against the
BTS documentation, and each is isolated in `pipeline/metrics/definitions.py` so
it can be changed in one place.

| Assumption | Where | Status |
|---|---|---|
| `sched_dep` is local hhmm; departure hour is `(hhmm // 100) % 24`, so `2400` becomes hour 0 | `BASE_VIEW` | **Verified** 2026-09-26: local zero-padded hhmm; scheduled times never reach `2400`, so the `% 24` never fires |
| On-time rate counts only operated flights with a non-null `arr_del15`; that denominator is published as `ops_measurable` | `METRIC_EXPRESSIONS` | Assumption, by design |
| Delay-cause shares are of *attributed* minutes, not all delay minutes | `_delay_causes` in `pipeline/export/pages.py` | **Verified** 2026-09-26: causes exist only on flights 15+ min late, and there they sum to `ArrDelayMinutes` |

### Original field mapping template

| Canonical field | Source column | Type | Notes |
|---|---|---|---|
| `flight_date` | | | |
| `carrier` | | | |
| `flight_number` | | | |
| `origin` | | | |
| `dest` | | | |
| `sched_dep` | | | |
| `actual_dep` | | | |
| `sched_arr` | | | |
| `actual_arr` | | | |
| `dep_delay_min` | | | |
| `arr_delay_min` | | | |
| `arr_del15` | | | |
| `cancelled` | | | |
| `cancellation_code` | | | |
| `diverted` | | | |
| `carrier_delay` | | | |
| `weather_delay` | | | |
| `nas_delay` | | | |
| `security_delay` | | | |
| `late_aircraft_delay` | | | |
| `distance` | | | |

## Later sources (not v1)

### Air Travel Consumer Report (DOT)
- Monthly report covering on-time performance, mishandled baggage, mishandled wheelchairs and scooters, and consumer complaints.
- Use for airline scorecards (M9+). **To verify:** machine-readable format availability.

### TSA weekly passenger throughput
- Hourly passenger throughput by airport and checkpoint, published weekly in the TSA FOIA Reading Room. Listed on data.gov as public.
- Published as PDFs, so parsing is the main work.
- Throughput is not wait time; pages must say so.

### T-100 traffic data (BTS)
- Monthly seats, passengers, and load factor by route and carrier. For the route explorer.
- **To verify:** release lag and any confidentiality delays.

### DB1B ticket sample (BTS)
- Historically a 10% ticket sample released quarterly, with records from 1993 onward.
- As of July 2025, carriers report monthly and sample 40% of tickets. **To verify:** what the public release now looks like before planning airfare pages.

## Sources we do not use

FlightAware, Flightradar24, FlightStats, Google Flights, airline websites, or any other commercial site. Their data is proprietary or their terms restrict automated access.
