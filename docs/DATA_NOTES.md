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

**The BTS source is NOT yet verified.** No code depends on an unverified fact: the
pipeline's `verify-source` command must run and write
`data/verification/bts_ontime_reporting_carrier.json` before `ingest` will do
anything (see `pipeline/sources/verify.py`). Until then `pipeline status` reports
`NOT VERIFIED` and ingest exits with an error.

Verification could not be completed in the session that wrote the adapter: the
development environment's network policy denies `transtats.bts.gov`
(`CONNECT` returned 403), and `extensions.duckdb.org` is likewise blocked. Run
this from a machine that can reach BTS:

```
make verify-source MONTH=2025-01        # or: uv run python -m pipeline verify-source --month 2025-01
```

It probes the candidate URLs, downloads one month, reads the real CSV header out
of the zip, diffs it against the candidate mapping below, and prints a markdown
block to paste into this file. If a candidate URL 404s, it says so and tells you
where to find the current link.

### Candidate download URLs (unverified)

Tried in order by `verify-source`; see `URL_CANDIDATES` in
`pipeline/sources/bts_ontime.py`.

1. `https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip`
2. `https://transtats.bts.gov/PREZIP/On_Time_On_Time_Performance_{year}_{month}.zip`

These come from prior familiarity with the dataset, not from checking the live
site. Treat them as a starting guess that the verifier either confirms or
replaces.

### Verification checklist (M1)

- [ ] Current bulk download method (prezipped monthly files vs field-selection download). Community tools commonly reference a prezipped monthly file pattern on transtats.bts.gov; **confirm the exact URL on the live site before coding against it.**
- [ ] File format, delimiter, encoding, header names
- [ ] Column list and types for the chosen table
- [ ] Meaning of time fields (local time, `hhmm` format, handling of `2400`)
- [ ] How cancelled and diverted flights populate delay fields
- [ ] When delay-cause columns are populated
- [ ] Reporting vs marketing carrier: which one carries the flight number a traveler would search (for example, a regional flight sold under a mainline code)
- [ ] BTS unique carrier identifiers and how code reuse is handled (BTS notes that carrier codes and names can change or be reused, and provides unique IDs for that reason)
- [ ] Lookup tables for airports and carriers, and where to download them
- [ ] A published monthly on-time figure to reproduce for validation (M2)
- [ ] Rate or usage guidance for automated downloads

### Candidate field mapping (unverified)

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
| `sched_dep` is local hhmm; departure hour is `(hhmm // 100) % 24`, so `2400` becomes hour 0 | `BASE_VIEW` | **To verify** |
| On-time rate counts only operated flights with a non-null `arr_del15`; that denominator is published as `ops_measurable` | `METRIC_EXPRESSIONS` | Assumption, by design |
| Delay-cause shares are of *attributed* minutes, not all delay minutes | `_delay_causes` in `pipeline/export/pages.py` | Follows BTS behaviour; **to verify** |

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
