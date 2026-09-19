# Colour scheme comparison

Three schemes, same layout, same data. Pick one with `SITE_THEME` at build time;
`voyager` is the default.

| Scheme | Feel |
|---|---|
| `voyager` | Navy chrome, blue primary, white cards on a soft canvas. The default — the online-travel-agency idiom. |
| `ocean` | The same layout in the original blue-on-warm-neutral palette. Quieter. |
| `harbor` | Teal on cool slate. Crisper and more technical. |

```
make themes                      # build all three into site/dist-<theme>/
make mockup-site THEME=harbor    # just one
```

## What a theme controls

Surfaces, text, borders, the brand and primary hues, the delay-severity chart
ramp, the hero gradient, and elevation.

## What it does not

The status roles: on-time green, cancelled neutral, and the four reliability band
colours. Those are declared once, outside every theme block, because a red chip
has to mean the same thing whatever the site looks like — and the band thresholds
come from `pipeline/summaries/rules.py`, not from CSS.

## Every scheme is validated

Each theme's chart ramp is checked for monotone lightness, adjacent-step gaps and
a light end that clears the surface, in both modes; text, link, series and
button-label colours are checked for contrast against that theme's own surfaces.
Two ramps failed on the first attempt and were re-stepped: harbor's light end at
1.72:1 and voyager's at 1.80:1, both against a 2:1 floor. Run the checks before
writing the CSS for a fourth scheme, not after.
