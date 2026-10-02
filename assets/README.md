# Sabi — foundation visual assets

Authored with the **Rive CLI** (`.riv` runtime files), not an image generator. Every graphic is a
flat vector scene graph built to the construction spec in
[`ASSETS.md`](../ASSETS.md) and the style rules in
[`docs/Sabi/branding.md`](../docs/Sabi/branding.md).

The editable source is the Rive project in [`rive/`](rive/): `brand.rml`, `illustrations.rml`,
`animations.rml`, `icons.rml` (`rive.yaml`, `scene` split by concern). Build and render with:

```bash
cd assets/rive
rive . --once                              # writes build/sabi.riv
rive . --verify                            # compile check, no output
rive . --screenshot=out.png --artboard=BrandMark --viewport=1024x1024
rive . --screenshot=out.png --artboard=Success --advance=500ms
```

`assets/sabi.riv` is the built runtime file. Per **D-016** it is the *single* runtime file: it
holds all 36 artboards (8 graphics, 28 icons) and callers load the artboard they need by name. The
former per-slot `.riv` copies have been removed; nothing is duplicated per slot.

## Ledger mapping

| Slot | Ledger file | Delivered | Rive artboard |
|---|---|---|---|
| A-001 | `assets/sabi.riv` (artboard) | `assets/sabi.riv` + `brand-mark/master.png` | `BrandMark` |
| A-002 | `app-icon/app-icon.png` | `app-icon/app-icon.png` (1024×1024) | `AppIcon` |
| A-003 | `splash/splash.png` | `splash/splash.png` (1440×2560) | `Splash` |
| A-004 | `assets/sabi.riv` (artboard) | `assets/sabi.riv` + `illustrations/empty-state.png` | `EmptyState` |
| A-005 | `assets/sabi.riv` (artboard) | `assets/sabi.riv` + `illustrations/offline.png` | `Offline` |
| A-006 | `assets/sabi.riv` (artboard) | `assets/sabi.riv` + `animations/success.png` (final frame) | `Success` |
| A-007 | `assets/sabi.riv` (artboard) | `assets/sabi.riv` + `animations/pending.png` (mid-loop frame) | `Pending` |
| A-008 | `assets/sabi.riv` (artboard) | `assets/sabi.riv` + `animations/error.png` (final frame) | `Error` |
| A-009 | `icons/*` | `assets/sabi.riv` (28 `Icon*` artboards) + `icons/*.png` + `icons/icon-set.png` | `IconHome` … `IconPaymentMethod` |
| A-010 | `fonts/inter/*.woff2` | `fonts/inter/*.woff2` + `*.ttf` | — |
| A-011 | `fonts/jetbrains-mono/*.woff2` | `fonts/jetbrains-mono/*.woff2` + `*.ttf` | — |

### Format substitution

The ledger originally named `.svg` for the vectors and `.json` for the animations; the icon family
also names `.svg`. The Rive CLI produces the Rive runtime format (`.riv`), a lightweight
vector/runtime animation — the form branding.md allows for motion ("Lightweight vector or runtime
animation; no video and no heavy animation bundles", NFR-001). The CLI cannot emit SVG or Lottie
JSON, and `rendering-vector-images` (the only SVG emitter) is retired. The per-icon files under
`icons/` are transparent PNG previews rendered from the build; the live, scalable icon is the
artboard in `sabi.riv`.

## Icon set (A-009)

Custom 24px outlined set, 2px stroke, round caps/joins, 2px corner radius, drawn to the mark's
rounded geometry. 28 artboards named `Icon<Name>`, one per semantic name in `SabIcons`:

- Navigation — `IconHome`, `IconReceipts`, `IconAccount`
- Actions — `IconSend`, `IconClose`, `IconChevronRight`, `IconSearch`, `IconRetry`, `IconCopy`,
  `IconCheck`, `IconInfo`, `IconOffline`, `IconHelp`, `IconAdd`, `IconSignOut`, `IconLanguage`
- Status — `IconStatusPending`, `IconStatusSettled`, `IconStatusFailed`,
  `IconStatusAwaitingReceipt`, `IconStatusUnverified`, `IconStatusVerified`,
  `IconStatusSuspended`, `IconError`
- Channels — `IconChannelUssd`, `IconChannelSms`, `IconChannelWhatsapp`
- Other — `IconPaymentMethod`

The artboards are authored one-colour in `grey-600 #5B5F54` (`text-secondary`). The client tints the
whole 24px artboard per state (default `text-secondary`, active `primary-500`, disabled
`text-secondary` at reduced opacity), so there are no per-state files. `empty-receipts` reuses
`IconReceipts`. `icons/icon-set.png` is a labelled contact sheet; `icons/<name>.png` are per-icon
24px transparent previews.

## Brand fonts (A-010, A-011)

Self-hosted, subset to Latin per **D-014**. Each family ships both `.woff2` (the ledger name) and
`.ttf` (what Flutter bundles):

| Family | Weights | Files |
|---|---|---|
| Inter | 400 / 500 / 600 / 700 | `fonts/inter/Inter-{Regular,Medium,SemiBold,Bold}.{woff2,ttf}` |
| JetBrains Mono | 400 / 500 | `fonts/jetbrains-mono/JetBrainsMono-{Regular,Medium}.{woff2,ttf}` |

Subset ranges: Basic Latin + Latin-1, Latin Extended-A and -B, combining diacritics, Latin
Extended Additional (covers Yoruba/Igbo `ẹ ọ ṣ ụ ị`), General Punctuation, Currency Symbols
(includes the Naira sign `₦`), plus `ℓ ™ → − ∕`. Hinting is removed (NFR-001; FreeType autohints on
device). Both fonts are SIL OFL 1.1 — see `OFL.txt` in each directory. Source: `Inter-4.1` and
`JetBrainsMono-2.304` releases.

> **Constraint:** JetBrains Mono, as distributed by JetBrains, has no `ṣ`, `₦`, or `ṛ` glyph.
> References and tokens (alphanumeric) are unaffected; do not set a currency amount in monospace,
> where `₦` would fall back. Inter covers every launch and later-locale character.

## Colours used

| Role | Hex | Where |
|---|---|---|
| `primary-500` ink | `#12805C` | brand mark, app-icon field, illustrations, pending segment, success trail |
| `primary-300` ink-soft | `#8FCDB2` | pending trailing tail |
| `grey-600` secondary | `#5B5F54` | illustration duotone (book cover, service node); icon set default |
| `grey-300` border | `#C6C9BE` | pending bubble outline |
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
  write alpha. `brand-mark/master.png`, the illustration/animation `.png`s and the raw icon captures
  are previews only. The icon previews under `icons/` were keyed to transparency from the raw
  capture; true transparency lives in the `.riv` (the artboards carry no background fill).
- **App icon is full-bleed.** For the same reason, `app-icon.png` is a full square of app field ink
  with the white mark; the 22% squircle container is kept in the geometry for masked use. Platform
  icon masks supply the rounded corners.
- **Reduced motion.** Motion carries no meaning on its own — the state is also shown by the Status
  Pill and its label, per the Accessibility rules.
- **One runtime file.** All artboards live in `assets/sabi.riv`; load by artboard name. The client
  integration that repoints the art loader is T-017.
