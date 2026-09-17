# Screenshots

Renderings of the site for design review.

**Everything shown is synthetic.** These are captured from the mockup build, which
uses generated data (`scripts/make_mockup_data.py`), not BTS figures. Every page
in them carries a banner saying so, and every one is `noindex`. No real data has
been ingested yet — see `docs/DATA_NOTES.md`.

What is real: the layout, the templates, the charts, the gate decisions and the
summary sentences, all of which came out of the actual pipeline and the actual
Astro build rather than being drawn by hand.

## Regenerating

```
make mockup        # synthetic data -> data/mockup/ -> site/dist-mockup/
make screenshots   # -> docs/screenshots/
```

`make screenshots` needs Playwright, which is not currently a project dependency:
`cd site && npm i -D playwright` if you want it.

The data generator is seeded, so re-running it produces the same numbers and the
screenshots only change when the design does.

## The set

| File | Page |
|---|---|
| `01-home-*` | Home, with search |
| `02-route-*` | Route page |
| `03-flight-*` | Flight page — the fullest template |
| `04-airport-*` | Airport page |
| `05-airline-*` | Airline page |
| `06-routes-index-*` | Routes section index |
| `07-connections-*` | Connection checker (interface only; M7 not built) |

Each comes in `-light`, `-dark` and `-mobile` (390px).
