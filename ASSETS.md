# Sabi: assets

The build's asset ledger. Slots come from the docs: `docs/Sabi/branding.md` (Asset Style Guide),
`docs/Sabi/screens.md` (Shared Assets), and each screen spec's declared assets. The user confirmed
none exist, so every slot is sourced new.

## Ledger

| Slot | File | Family / Variant | Status |
|---|---|---|---|
| A-001 | assets/brand-mark/master.svg | Brand mark / master | Pending |
| A-002 | assets/app-icon/app-icon.png | Brand mark / app-icon | Pending |
| A-003 | assets/splash/splash.png | Brand mark / splash | Pending |
| A-004 | assets/illustrations/empty-state.svg | Empty-state illustration / single | Pending |
| A-005 | assets/illustrations/offline.svg | Offline illustration / single | Pending |
| A-006 | assets/animations/success.json | Success animation / single | Pending |
| A-007 | assets/animations/pending.json | Pending animation / single | Pending |
| A-008 | assets/animations/error.json | Error animation / single | Pending |

## Brand mark — generation prompt

**Medium**
Image (brand mark, variant family)

**Palette**
- ink            #12805C  (dark #3FA981)
- ink-deep       #0A3829  (dark #C6ECDE)
- ink-soft       #8FCDB2  (dark #236E54)
- surface        #FAF8F4  (dark #17181A)
- knockout       #FFFFFF  (dark #0A2E22)

**Invariants**
Flat single-plane vector; solid fill; no gradient, bevel, outline, shadow, glow, or 3D. A rounded
speech bubble, wider than tall, near-symmetric, with one tail at the lower right whose lower edge is
a sharp zigzag torn like a receipt edge; the tear notches are negative space, not a stroke. Reads in
a single flat colour before any accent. Centred with clear space equal to the bubble's corner radius
on all sides. Banned readings: letters, wordmark, verified tick, shopping bag, price tag, torn
envelope, map pin, smooth-tailed chat-app bubble.

**Prompt**
```text
Flat vector brand mark on a 24-unit square grid: a solid rounded speech bubble. The bubble body is a
rounded rectangle 20 units wide by 13 units tall with a uniform 4-unit corner radius. A single tail at
the lower right, 5 units wide, descends 4 units below the body; the tail's bottom edge is a sharp
zigzag torn like the bottom edge of a paper receipt, four triangular notches at 90-degree and
45-degree angles, cut as negative space so the background shows through the tear. The bubble is
near-symmetric with the torn tail as the only asymmetry. Overshoot the rounded corners slightly past
the grid line so the form looks level, and smooth the join where the tail meets the body so the sides
do not look pinched. The mark occupies 72% of the canvas, centred, with even clear space equal to the
4-unit corner radius on every side. Solid flat fill #12805C, one colour only. No outline, no gradient,
no bevel, no drop shadow, no glow, no highlight. Reads in a single flat colour. No letters, no text, no
verified tick, no shopping bag, no price tag, no torn envelope, no map pin, no smooth-tailed chat
bubble. Transparent background. Square 1:1.
```

**Settings**
- Resolution / size: 1024x1024
- Motion: —
- Seed / reference: —
- Negative prompt: text, letters, watermark, gradient, drop shadow, bevel, 3D

**Variants**
| Variant | Delta (by role) | Size |
|---|---|---|
| master | None (canonical) | 1024 |
| one-colour | fill → ink #12805C, no other colour | 1024 |
| knockout | fill → knockout #FFFFFF on transparent | 1024 |
| dark | fill → ink dark #3FA981 on transparent | 1024 |
| app-icon | background → app field ink #12805C; fill → #FFFFFF; symbol inside a rounded-square squircle container with 22% corner radius, full-bleed, mark at 86% | 1024 |
| splash | background → surface #FAF8F4; fill → ink #12805C; mark centred at 40% of the canvas | 1440x2560 |
| favicon | uniform scale of the app-icon composite | 64 |
| lockup-horizontal | mark plus wordmark "Sabi" set deterministically in Inter 700, never generated | 1024 wide |
| lockup-stacked | mark above the same set wordmark | 1024 |

**Open questions**
- Lockup variants need the wordmark set in a real typeface; the generator must not draw the letters.

## Empty-state illustration — generation prompt

**Medium**
Image (UI state illustration)

**Prompt**
```text
Flat vector illustration for a mobile app empty state: an open receipt book with no pages written
yet. Built from simple rounded geometric forms that echo a speech bubble and a torn receipt edge: the
book cover is a rounded rectangle with a 4-unit corner radius, the open pages are two nested rounded
rectangles, and a single receipt edge curls from the cover with a zigzag torn edge of triangular
notches. Duotone: main shapes #12805C and #5B5F54, with one #D9643A highlight on the curling receipt
edge. Line-weight hierarchy: bold outline on the book's dominant form, medium on the pages, fine on
the torn edge. Centred, generous negative space. Transparent background. No text, no letters, no
people, no gradients, no texture, no detail below 2px. Square 1:1.
```

**Settings**
- Resolution / size: 1024x1024
- Motion: —
- Seed / reference: —
- Negative prompt: text, letters, people, gradient, texture, 3D, drop shadow

## Offline illustration — generation prompt

**Medium**
Image (UI state illustration)

**Prompt**
```text
Flat vector illustration for a mobile app offline state: a smartphone on the left and a small distant
service node on the right, with a broken signal between them. The phone is a rounded rectangle with a
4-unit corner radius; the service node is a small rounded square; two concentric signal arcs travel
between them and are broken at the midpoint by a jagged torn gap that echoes a torn receipt edge.
Duotone: shapes in #12805C and #5B5F54, with one #D9643A highlight on the broken signal. Line-weight
hierarchy: bold outline on the phone, medium on the node, fine on the signal arcs. Centred, generous
negative space. Transparent background. No text, no letters, no people, no gradients, no texture, no
detail below 2px. Square 1:1.
```

**Settings**
- Resolution / size: 1024x1024
- Motion: —
- Seed / reference: —
- Negative prompt: text, letters, people, gradient, texture, 3D, drop shadow

## Success animation — generation prompt

**Medium**
Animation (one-shot state sting)

**Prompt**
```text
Animated state sting on a transparent frame: a torn receipt edge sweeps in and settles into a check
mark. Starting empty, a torn zigzag edge in #12805C sweeps in from the lower left along a gentle arc;
as it comes to rest its notches flatten and resolve into a single smooth check-mark stroke. One lead
action, fixed camera, no background. The check resolves to #16A34A at rest, over an #12805C trail.
One-shot, ease-out into the settle with a slight overshoot that eases back, no bounce, no confetti, no
particles, no gradient, no audio. Flat vector, brand colours only. 500ms at 24fps, loop off, final
frame held. Square 1:1.
```

**Settings**
- Resolution / size: 1024x1024
- Motion: 500ms at 24fps, one-shot, final frame held, no loop
- Seed / reference: —
- Negative prompt: confetti, particles, gradient, bounce, text, background

## Pending animation — generation prompt

**Medium**
Animation (seamless loop)

**Prompt**
```text
Animated pending loop on a transparent frame: a small torn receipt edge travels around the outline of
a rounded speech bubble, leaving a soft trail. The bubble outline stays in #C6C9BE; a short torn
zigzag segment in #12805C moves clockwise around the perimeter at constant speed with a faint trailing
tail in #8FCDB2. One continuous motion, fixed camera, no background. Seamless loop with identical first
and last frame, 2 seconds at 24fps. Flat vector, brand colours only, no gradient fill, no particles,
no bounce, no audio. Square 1:1.
```

**Settings**
- Resolution / size: 1024x1024
- Motion: 2s at 24fps, seamless loop, first and last frame identical
- Seed / reference: —
- Negative prompt: particles, gradient, bounce, text, background

## Error animation — generation prompt

**Medium**
Animation (one-shot state sting)

**Prompt**
```text
Animated state sting on a transparent frame: a smooth receipt edge re-tears and settles flat. A clean
straight receipt edge in #12805C tears into a jagged zigzag with one quick motion, the notches opening
from left to right, then the torn edge settles flat. One lead action, fixed camera, no background. The
final torn edge reads #DC2626. One-shot, ease-in with a firm stop, no bounce, no overshoot, no
particles, no gradient, no audio. Flat vector, brand colours only. 450ms at 24fps, loop off, final
frame held. Square 1:1.
```

**Settings**
- Resolution / size: 1024x1024
- Motion: 450ms at 24fps, one-shot, final frame held, no loop
- Seed / reference: —
- Negative prompt: bounce, overshoot, particles, gradient, text, background
