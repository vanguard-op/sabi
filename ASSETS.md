# Sabi: assets

The build's asset ledger. Slots come from the docs: `docs/Sabi/branding.md` (Asset Style Guide),
`docs/Sabi/screens.md` (Shared Assets), and each screen spec's declared assets. The user confirmed
none exist, so every slot is sourced new.

## Ledger

| Slot | File | Family / Variant | Status |
|---|---|---|---|
| A-001 | assets/sabi.riv (artboard BrandMark) | Brand mark / master | Done |
| A-002 | assets/app-icon/app-icon.png | Brand mark / app-icon | Done |
| A-003 | assets/splash/splash.png | Brand mark / splash | Done |
| A-004 | assets/sabi.riv (artboard EmptyState) | Empty-state illustration / single | Done |
| A-005 | assets/sabi.riv (artboard Offline) | Offline illustration / single | Done |
| A-006 | assets/sabi.riv (artboard Success) | Success animation / single | Done |
| A-007 | assets/sabi.riv (artboard Pending) | Pending animation / single | Done |
| A-008 | assets/sabi.riv (artboard Error) | Error animation / single | Done |
| A-009 | assets/sabi.riv (artboards Icon*) + assets/icons/*.png | Icon set / custom 24px outlined | Done |
| A-010 | assets/fonts/inter/*.woff2 (+ *.ttf) | Brand type / Inter | Done |
| A-011 | assets/fonts/jetbrains-mono/*.woff2 (+ *.ttf) | Brand type / JetBrains Mono | Done |

Per **D-016** the runtime graphics ship as one file, `assets/sabi.riv`; every ledger slot that
names an artboard is loaded from it by name. The former per-slot `.riv` copies are removed.

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

## Icon set — family block (A-009)

**Medium**
Vector (UI icon family; authored with the Rive CLI, shipped as artboards in `assets/sabi.riv`)

**Grid & style** (branding.md, "Iconography Direction")
- 24×24 grid; drawable band inset 2 units so the stroke stays inside the box.
- 2px stroke, round caps and joins; outlined, single weight.
- 2px corner radius on axis-aligned forms; curved forms use true arcs.
- Drawn to the mark's rounded geometry. Small solid dots (2.3–2.8px) are allowed where an
  outlined dot would not read at the weight; nothing else is filled except the retry arrow head.

**Colour**
- Authored one-colour in `grey-600 #5B5F54` (`text-secondary`), the default icon state.
- States are carried by tint, not by separate art: default `text-secondary`; active `primary-500`;
  disabled `text-secondary` at reduced opacity. The client tints the whole 24px artboard with a
  colour filter, so one artboard serves every state and both themes.
- Retry arrow head is the only non-stroke mark; it is the same colour.

**Roster (28)** — one artboard per semantic name; `SabIcons` in the client maps one-to-one.

| Group | Semantic names | Rive artboards |
|---|---|---|
| Navigation | home, receipts, account | IconHome, IconReceipts, IconAccount |
| Actions | send, close, chevron-right, search, retry, copy, check, info, offline, help, add, sign-out, language | IconSend … IconLanguage |
| Status | status-pending, status-settled, status-failed, status-awaiting-receipt, status-unverified, status-verified, status-suspended, error | IconStatus… , IconError |
| Channels | channel-ussd, channel-sms, channel-whatsapp | IconChannelUssd, IconChannelSms, IconChannelWhatsapp |
| Other | payment-method | IconPaymentMethod |

`empty-receipts` reuses the `receipts` artboard. `status-failed` is a cross in a circle;
`error` is a warning triangle, so an inline error is distinguishable from a failed payment.
Status icons always pair with a text label (branding.md, Accessibility).

**Delivery / format substitution (D-016)**
- The ledger names `assets/icons/*.svg`. The Rive CLI emits the Rive runtime format and cannot
  write SVG, and `rendering-vector-images` (the only SVG emitter) is retired. The set is therefore
  delivered as `assets/sabi.riv` artboards loaded by name, per D-016, with per-icon PNG previews in
  `assets/icons/`. Recolour at runtime rather than shipping per-state variants.

**Open questions**
- Whether the client tints via a colour filter or binds an icon-colour view-model property is
  T-017's call; both read the same one-colour artboard.
