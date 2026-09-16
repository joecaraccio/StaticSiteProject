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

### Field mapping (fill in during M1)

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
