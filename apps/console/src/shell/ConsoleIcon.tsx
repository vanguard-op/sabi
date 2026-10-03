import type { CSSProperties } from 'react';

/**
 * The console's navigation icons, drawn inline on the brand's 24px grid
 * (branding.md, "Iconography Direction": 24px grid, 2px stroke, round caps and
 * joins, outlined, 2px corner radius). `ASSETS.md` A-009 delivers the custom set
 * as artboards in `assets/sabi.riv`, a Rive runtime the web console does not
 * bundle; these are the same forms rendered as inline SVG so the shell has no
 * raster decode and no icon runtime, and stay crisp at every desktop size.
 *
 * The paths are stroke-only and inherit `currentColor`, so the sidebar's
 * default, hover, and active states tint the whole icon from one rule exactly as
 * the Rive artboard is tinted per state (ASSETS.md, "Colour").
 */
export type ConsoleIconName = 'home' | 'documents' | 'health' | 'audit';

const PATHS: Record<ConsoleIconName, JSX.Element> = {
  // A house: the roster's `home` form.
  home: (
    <>
      <path d="M4 10.5 12 4l8 6.5" />
      <path d="M6 9.5V19a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V9.5" />
      <path d="M10 20v-3.5a2 2 0 0 1 4 0V20" />
    </>
  ),
  // Stacked pages: the roster's `copy` form, read as a schema.
  documents: (
    <>
      <rect x="8" y="8" width="11" height="11" rx="2" />
      <path d="M5 15V6a2 2 0 0 1 2-2h9" />
    </>
  ),
  // A pulse in a circle: health, distinct from the status shield set.
  health: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M8 12h2.5l1.5-2.5 1.5 5 1.5-2.5H16" />
    </>
  ),
  // A magnifier over a line: the roster's `search` form, read as an audit log.
  audit: (
    <>
      <circle cx="11" cy="11" r="6" />
      <path d="M15.5 15.5 20 20" />
      <path d="M8.5 11h5" />
    </>
  ),
};

/**
 * An inline icon sized from the inherited icon scale. `size` is a CSS length so
 * call sites pass `var(--icon-md)` rather than a literal; the 24px viewBox keeps
 * the documented grid regardless of the rendered size.
 */
export function ConsoleIcon({
  name,
  size = 'var(--icon-md)',
  className,
  style,
  title,
}: {
  name: ConsoleIconName;
  size?: string;
  className?: string;
  style?: CSSProperties;
  title?: string;
}): JSX.Element {
  return (
    <svg
      className={className}
      style={{ width: size, height: size, flex: '0 0 auto', ...style }}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : true}
      role={title ? 'img' : undefined}
    >
      {title ? <title>{title}</title> : null}
      {PATHS[name]}
    </svg>
  );
}
