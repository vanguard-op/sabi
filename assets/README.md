# Sabi — foundation visual assets

Authored with the **Rive CLI** (`.riv` runtime files), not an image generator. Every asset is a
flat vector scene graph built to the construction spec in
[`ASSETS.md`](../ASSETS.md) and the style rules in
[`docs/Sabi/branding.md`](../docs/Sabi/branding.md).

The editable source is the Rive project in [`rive/`](rive/): `brand.rml`, `illustrations.rml`,
`animations.rml` (`rive.yaml`, `scene` split by concern). Build and render with:

```bash
cd assets/rive
rive . --once                              # writes build/sabi.riv
rive . --screenshot=out.png --artboard=BrandMark --viewport=1024x1024
rive . --screenshot=out.png --artboard=Success --advance=500ms
```

`assets/sabi.riv` is the built runtime file. It holds all eight artboards; the artboards named after
each ledger slot are the ones to load. The per-slot `.riv` files in this tree are copies of that one
file (aliases), so any single slot is loadable on its own.

## Ledger mapping

| Slot | Ledger file | Delivered | Rive artboard |
|---|---|---|---|
| A-001 | `brand-mark/master.svg` | `brand-mark/master.riv` + `brand-mark/master.png` | `BrandMark` |
| A-002 | `app-icon/app-icon.png` | `app-icon/app-icon.png` (1024×1024) | `AppIcon` |
| A-003 | `splash/splash.png` | `splash/splash.png` (1440×2560) | `Splash` |
| A-004 | `illustrations/empty-state.svg` | `illustrations/empty-state.riv` + `.png` | `EmptyState` |
| A-005 | `illustrations/offline.svg` | `illustrations/offline.riv` + `.png` | `Offline` |
| A-006 | `animations/success.json` | `animations/success.riv` + `.png` (final frame) | `Success` |
| A-007 | `animations/pending.json` | `animations/pending.riv` + `.png` (mid-loop frame) | `Pending` |
| A-008 | `animations/error.json` | `animations/error.riv` + `.png` (final frame) | `Error` |

### Format substitution

The ledger names `.svg` for the vectors and `.json` for the animations. The adapted skill produces
the Rive runtime format (`.riv`), which is a lightweight vector/runtime animation — the form the
branding doc allows for motion ("Lightweight vector or runtime animation; no video and no heavy
animation bundles", NFR-001). The CLI cannot emit SVG or Lottie JSON, and
`rendering-vector-images` (the only SVG emitter) is retired. `master.riv` is the editable vector
master; the `.png` beside each vector slot is a raster preview.

## Colours used

| Role | Hex | Where |
|---|---|---|
| `primary-500` ink | `#12805C` | brand mark, app-icon field, illustrations, pending segment, success trail |
| `primary-300` ink-soft | `#8FCDB2` | pending trailing tail |
| `grey-300` border | `#C6C9BE` | pending bubble outline |
| `grey-600` secondary | `#5B5F54` | illustration duotone (book cover, service node) |
| `accent-500` | `#D9643A` | illustration highlight (torn receipt, broken signal) |
| `success-500` | `#16A34A` | settled check at rest |
| `error-500` | `#DC2626` | re-torn receipt edge at rest |
| knockout | `#FFFFFF` | mark on the app-icon field |
| `surface` | `#FAF8F4` | splash background |

## Motion spec

- **Success** — 12 frames @ 24fps, one-shot, final frame held. Torn receipt edge sweeps in from the
  lower left, settles, and resolves into a check that lands on `#16A34A`.
- **Pending** — 48 frames @ 24fps, seamless loop (frame 0 = frame 48). A short torn segment in
  `#12805C` travels clockwise around the bubble outline in `#C6C9BE` with an `#8FCDB2` trail.
- **Error** — 11 frames @ 24fps, one-shot, final frame held. A clean straight edge tears into a
  zigzag with an ease-in and a firm stop, settling in `#DC2626`.

## Known constraints

- **Raster previews are opaque.** The CLI screenshot renders onto a fixed `#1D1D1D` clear; it cannot
  write alpha. `brand-mark/master.png` and the illustration/animation `.png`s are therefore previews
  only. True transparency lives in the `.riv` (the artboards carry no background fill).
- **App icon is full-bleed.** For the same reason, `app-icon.png` is a full square of app field ink
  with the white mark; the 22% squircle container is kept in the geometry for masked use. Platform
  icon masks supply the rounded corners.
- **Reduced motion.** Motion carries no meaning on its own — the state is also shown by the Status
  Pill and its label, per the Accessibility rules.
