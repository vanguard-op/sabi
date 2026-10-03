/**
 * Sabi Operations Console design tokens.
 *
 * The single source of truth for the console, implementing the
 * "Desktop and Staff Console Token Set" in `docs/Sabi/branding.md`. It inherits
 * the brand colour, type, spacing, radius, elevation, and component grammar and
 * adds the desktop layout, density, table, form, interaction, and shell tokens.
 *
 * Colours are emitted as CSS custom properties and consumed as `var(--...)` at
 * call sites; the typed scales below carry the same values for TS and tests so no
 * call site hardcodes a design value. Documented anchors are the only literals,
 * and the implicit intermediate shades are interpolated from them, matching the
 * mobile token source.
 */

import type { CSSProperties } from 'react';

// --- Documented anchors (branding.md, "Color Palette") ---------------------

interface Ramp {
  readonly [step: number]: string;
}

const PRIMARY_LIGHT: Ramp = {
  100: '#E3F2EC',
  300: '#8FCDB2',
  500: '#12805C',
  700: '#0E5940',
  900: '#0A3829',
};
const PRIMARY_DARK: Ramp = {
  100: '#14382B',
  300: '#236E54',
  500: '#3FA981',
  700: '#8AD0B6',
  900: '#C6ECDE',
};

const GREY_LIGHT: Ramp = {
  50: '#FAF8F4',
  100: '#EEEFE8',
  300: '#C6C9BE',
  600: '#5B5F54',
  900: '#1B1C1A',
};
const GREY_DARK: Ramp = {
  50: '#17181A',
  100: '#202219',
  300: '#3F4238',
  600: '#A8AC9E',
  900: '#F4F5F1',
};

const SEMANTIC_LIGHT: Record<string, string> = {
  success: '#16A34A',
  warning: '#D97706',
  error: '#DC2626',
  info: '#2563EB',
  accent: '#D9643A',
};
const SEMANTIC_DARK: Record<string, string> = {
  success: '#4ADE80',
  warning: '#FBBF24',
  error: '#F87171',
  info: '#60A5FA',
  accent: '#F0A088',
};

const PRIMARY_STEPS = [100, 200, 300, 400, 500, 600, 700, 800, 900] as const;
const GREY_STEPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900] as const;

// --- Colour math (mirrors the mobile token source) -------------------------

function hexToRgb(hex: string): [number, number, number] {
  const v = parseInt(hex.slice(1), 16);
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
}

function rgbToHex(rgb: [number, number, number]): string {
  const to2 = (n: number) => Math.round(n).toString(16).padStart(2, '0');
  return `#${to2(rgb[0])}${to2(rgb[1])}${to2(rgb[2])}`.toUpperCase();
}

function mix(a: string, b: string, t: number): string {
  const [ar, ag, ab] = hexToRgb(a);
  const [br, bg, bb] = hexToRgb(b);
  return rgbToHex([ar + (br - ar) * t, ag + (bg - ag) * t, ab + (bb - ab) * t]);
}

/** Fills every step across the documented anchors, interpolating the implicit ones. */
function ramp(anchors: Ramp, steps: readonly number[]): Record<number, string> {
  const keys = Object.keys(anchors)
    .map(Number)
    .sort((a, b) => a - b);
  const out: Record<number, string> = {};
  for (const step of steps) {
    if (anchors[step] !== undefined) {
      out[step] = anchors[step];
      continue;
    }
    const lower = [...keys].reverse().find((k) => k < step) ?? keys[0]!;
    const upper = keys.find((k) => k > step) ?? keys[keys.length - 1]!;
    out[step] = lower === upper ? anchors[lower]! : mix(anchors[lower]!, anchors[upper]!, (step - lower) / (upper - lower));
  }
  return out;
}

/** Builds the 5-shade semantic scale; direction reverses in dark mode. */
function semanticScale(anchor: string, isDark: boolean): Record<number, string> {
  if (isDark) {
    return {
      100: mix(anchor, '#000000', 0.62),
      300: mix(anchor, '#000000', 0.34),
      500: anchor,
      700: mix(anchor, '#FFFFFF', 0.25),
      900: mix(anchor, '#FFFFFF', 0.52),
    };
  }
  return {
    100: mix(anchor, '#FFFFFF', 0.86),
    300: mix(anchor, '#FFFFFF', 0.55),
    500: anchor,
    700: mix(anchor, '#000000', 0.3),
    900: mix(anchor, '#000000', 0.55),
  };
}

export type ThemeMode = 'light' | 'dark';

export interface ConsolePalette {
  mode: ThemeMode;
  primary: Record<number, string>;
  grey: Record<number, string>;
  semantic: Record<string, Record<number, string>>;
  surface: string;
  surfaceSecondary: string;
  textPrimary: string;
  textSecondary: string;
  border: string;
  onPrimary: string;
  onError: string;
}

function buildPalette(mode: ThemeMode): ConsolePalette {
  const isDark = mode === 'dark';
  const primary = ramp(isDark ? PRIMARY_DARK : PRIMARY_LIGHT, PRIMARY_STEPS);
  const grey = ramp(isDark ? GREY_DARK : GREY_LIGHT, GREY_STEPS);
  const semantic: Record<string, Record<number, string>> = {};
  const source = isDark ? SEMANTIC_DARK : SEMANTIC_LIGHT;
  for (const [name, anchor] of Object.entries(source)) {
    semantic[name] = semanticScale(anchor, isDark);
  }
  return {
    mode,
    primary,
    grey,
    semantic,
    surface: grey[50]!,
    surfaceSecondary: grey[100]!,
    textPrimary: grey[900]!,
    textSecondary: grey[600]!,
    border: grey[300]!,
    onPrimary: isDark ? '#0A2E22' : '#FFFFFF',
    onError: isDark ? '#17181A' : '#FFFFFF',
  };
}

export const palettes: Record<ThemeMode, ConsolePalette> = {
  light: buildPalette('light'),
  dark: buildPalette('dark'),
};

// --- Non-colour tokens (branding.md, "Desktop and Staff Console Token Set") --

/** Layout and breakpoints. */
export const layout = {
  bpConsoleSm: 1024,
  bpConsoleMd: 1440,
  bpConsoleLg: 1920,
  contentMax: 1280,
  shellMin: 1024,
} as const;

/** Density — the documented desktop exception to the 44px touch minimum. */
export const density = {
  rowHeight: 40,
  rowHeightCompact: 32,
  controlHeight: 36,
  controlHeightSm: 32,
  cellPadX: 12,
  cellPadY: 8,
  checkboxSize: 16,
  checkboxHitArea: 24,
} as const;

/** Data-table tokens. */
export const table = {
  headerHeight: 44,
  rowHoverBg: 'var(--color-primary-100)',
  rowSelectedBg: 'var(--color-primary-100)',
  rowBorder: 'var(--color-border)',
  zebraBg: 'var(--color-surface)',
  sortIndicator: 'var(--color-primary-500)',
} as const;

/** Shell / sidebar / topbar tokens. */
export const shell = {
  sidebarWidth: 240,
  sidebarWidthCollapsed: 64,
  sidebarItemHeight: 40,
  topbarHeight: 56,
} as const;

/** Interaction tokens (hover, active, focus, disabled, skeleton). */
export const interaction = {
  hoverBg: 'var(--color-primary-100)',
  hoverText: 'var(--color-primary-700)',
  activeBg: 'var(--color-primary-300)',
  selectedBg: 'var(--color-primary-100)',
  disabledOpacity: 0.5,
  skeletonBg: 'var(--color-surface-secondary)',
} as const;

/** Spacing (inherited). */
export const space = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32, xxl: 48, xxxl: 64 } as const;

/** Radius (inherited). */
export const radius = { sm: 4, md: 8, lg: 12, full: 9999 } as const;

/** Icon sizes (inherited). */
export const icon = { sm: 16, md: 24, lg: 32 } as const;

/** Motion. */
export const motion = {
  fast: 150,
  base: 250,
  emphasized: 500,
  skeletonPulse: 1100,
} as const;

/**
 * Emits the CSS custom properties for a palette. Structural role tokens and
 * every scale step are exposed so call sites style only through `var(--...)`.
 */
export function cssVariables(palette: ConsolePalette): CSSProperties {
  const vars: Record<string, string> = {};
  for (const [step, value] of Object.entries(palette.primary)) {
    vars[`--color-primary-${step}`] = value;
  }
  for (const [step, value] of Object.entries(palette.grey)) {
    vars[`--color-grey-${step}`] = value;
  }
  for (const [name, scale] of Object.entries(palette.semantic)) {
    for (const [step, value] of Object.entries(scale)) {
      vars[`--color-${name}-${step}`] = value;
    }
  }
  vars['--color-surface'] = palette.surface;
  vars['--color-surface-secondary'] = palette.surfaceSecondary;
  vars['--color-text-primary'] = palette.textPrimary;
  vars['--color-text-secondary'] = palette.textSecondary;
  vars['--color-border'] = palette.border;
  vars['--color-on-primary'] = palette.onPrimary;
  vars['--color-on-error'] = palette.onError;

  vars['--space-xs'] = `${space.xs}px`;
  vars['--space-sm'] = `${space.sm}px`;
  vars['--space-md'] = `${space.md}px`;
  vars['--space-lg'] = `${space.lg}px`;
  vars['--space-xl'] = `${space.xl}px`;
  vars['--space-2xl'] = `${space.xxl}px`;
  vars['--space-3xl'] = `${space.xxxl}px`;

  vars['--radius-sm'] = `${radius.sm}px`;
  vars['--radius-md'] = `${radius.md}px`;
  vars['--radius-lg'] = `${radius.lg}px`;
  vars['--radius-full'] = `${radius.full}px`;

  vars['--icon-sm'] = `${icon.sm}px`;
  vars['--icon-md'] = `${icon.md}px`;
  vars['--icon-lg'] = `${icon.lg}px`;

  vars['--row-height'] = `${density.rowHeight}px`;
  vars['--row-height-compact'] = `${density.rowHeightCompact}px`;
  vars['--control-height'] = `${density.controlHeight}px`;
  vars['--control-height-sm'] = `${density.controlHeightSm}px`;
  vars['--cell-pad-x'] = `${density.cellPadX}px`;
  vars['--cell-pad-y'] = `${density.cellPadY}px`;
  vars['--checkbox-size'] = `${density.checkboxSize}px`;
  vars['--checkbox-hit-area'] = `${density.checkboxHitArea}px`;

  vars['--table-header-height'] = `${table.headerHeight}px`;
  vars['--sidebar-width'] = `${shell.sidebarWidth}px`;
  vars['--sidebar-width-collapsed'] = `${shell.sidebarWidthCollapsed}px`;
  vars['--sidebar-item-height'] = `${shell.sidebarItemHeight}px`;
  vars['--topbar-height'] = `${shell.topbarHeight}px`;

  vars['--content-max'] = `${layout.contentMax}px`;
  vars['--shell-min'] = `${layout.shellMin}px`;

  vars['--hover-bg'] = interaction.hoverBg;
  vars['--hover-text'] = interaction.hoverText;
  vars['--active-bg'] = interaction.activeBg;
  vars['--selected-bg'] = interaction.selectedBg;
  vars['--skeleton-bg'] = interaction.skeletonBg;
  vars['--disabled-opacity'] = `${interaction.disabledOpacity}`;

  vars['--motion-fast'] = `${motion.fast}ms`;
  vars['--motion-base'] = `${motion.base}ms`;
  vars['--motion-emphasized'] = `${motion.emphasized}ms`;
  vars['--motion-skeleton-pulse'] = `${motion.skeletonPulse}ms`;

  return vars as CSSProperties;
}
