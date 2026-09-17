# Test fixtures

## `synthetic_ontime_sample.csv`

**This file is synthetic. It is not BTS data and must never be used to produce a
published page.** It exists so metric logic can be checked against numbers
computed by hand, which CLAUDE.md requires.

What is real about it: the *column names* are the candidate BTS source names from
`pipeline/models/schema.py`, and the shape (empty strings for absent values,
`1.00`-style flag encoding) mirrors what the adapter expects. Once
`pipeline verify-source` has confirmed the live header, any mismatch here will
show up as a normalization failure — which is the point.

What is invented: every value. Airport IDs (`90001`, `90002`), carrier DOT IDs
(`90010`, `90020`, `90030`) and tail numbers are deliberately outside real BTS ID
ranges so this data cannot be mistaken for the genuine article.

### Contents

| Group | Month | Rows | Purpose |
|---|---|---|---|
| AA 100 BOS→LGA | 2025-01 | 10 | The hand-computed reference set (see below) |
| DL 200 BOS→LGA | 2025-01 | 5 | All on time; proves grouping and route rollup |
| UA 300 LGA→BOS | 2025-01 | 4 | Reverse direction; exercises airport arrival/departure roles |
| AA 100 BOS→LGA | 2023-12 | 3 | All cancelled, **outside** the trailing-12 window; must be excluded |

`Tail_Number` is present but unmapped, proving extra source columns are ignored
rather than breaking normalization. One AA row has `CRSDepTime = 2400`, which must
bucket as departure hour 0.

### Hand-computed reference: AA 100 BOS→LGA, trailing 12 months

The ten 2025-01 rows have arrival delays of −5, 0, 10, 20, 45, 90, 150, 200
minutes, plus one cancellation and one diversion.

| Metric | Value | Working |
|---|---|---|
| `ops_scheduled` | 10 | all rows in window |
| `ops_operated` | 8 | 10 − 1 cancelled − 1 diverted |
| `ops_cancelled` | 1 | |
| `ops_diverted` | 1 | |
| `ops_measurable` | 8 | operated rows with an `ArrDel15` value |
| `on_time_rate` | 0.375 | 3 of 8 (delays −5, 0, 10 are under 15 min) |
| `cancellation_rate` | 0.1 | 1 ÷ 10 scheduled |
| `diversion_rate` | 0.1 | 1 ÷ 10 scheduled |
| `avg_arr_delay_min` | 63.75 | 510 ÷ 8 |
| `avg_arr_delay_when_late_min` | 101.0 | (20+45+90+150+200) ÷ 5 = 505 ÷ 5 |
| `median_arr_delay_when_late_min` | 90 | middle of 20, 45, 90, 150, 200 |
| `share_3h_plus` | 0.125 | 1 of 8 operated at ≥180 min |
| buckets | 3 / 1 / 1 / 1 / 1 / 1 | on time, 15–30, 30–60, 60–120, 120–180, 180+ |
| `bucket_cancelled_diverted` | 2 | |
| `carrier_delay_min` | 140 | 20 + 20 + 100 |
| `weather_delay_min` | 75 | 25 + 50 |
| `nas_delay_min` | 120 | 90 + 30 |
| `security_delay_min` | 20 | |
| `late_aircraft_delay_min` | 150 | |
| `attributed_delay_min` | 505 | equals the total delay of the five late flights |

Route BOS→LGA over the same window: 15 scheduled, 13 operated, 8 on time
(3 from AA + 5 from DL), so `on_time_rate` = 8 ÷ 13.
