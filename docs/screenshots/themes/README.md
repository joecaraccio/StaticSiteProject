# Colour scheme comparison

Three schemes, same page, same data. Pick one with `SITE_THEME` at build time;
`ocean` is the default.

| Scheme | Feel |
|---|---|
| `ocean` | Blue on warm neutral. The original — closest to a standard data tool. |
| `harbor` | Teal on cool slate. Crisper and more technical; the dark mode is the strongest of the three. |
| `paper` | Indigo on warm cream. Softer and more editorial, closer to print. |

```
make themes                      # build all three into site/dist-<theme>/
make mockup-site THEME=harbor    # just one
```

## What a theme controls

Surfaces, text, borders, the primary hue, the delay-severity chart ramp, and the
hero gradient.

## What it does not

The status roles: on-time green, cancelled neutral, and the four reliability band
colours. Those are declared once, outside every theme block, because a red chip
has to mean the same thing whatever the site looks like — and the band thresholds
come from `pipeline/summaries/rules.py`, not from CSS.

## Every scheme is validated

Each theme's chart ramp is checked for monotone lightness, adjacent-step gaps and
a light end that clears the surface, in both modes; text, link and series colours
are checked for contrast against that theme's surface. The first teal ramp failed
its light end at 1.72:1 against a 2:1 floor and was re-stepped. Run the checks
before writing the CSS for a fourth scheme, not after.
