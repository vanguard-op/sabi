import { describe, expect, it } from 'vitest';
import {
  cssVariables,
  layout,
  palettes,
  space,
  radius,
  density,
  shell,
} from '../theme/tokens';

/**
 * The console's token source must implement the Desktop and Staff Console Token
 * Set exactly; these assertions pin the documented values so a drift is caught.
 */
describe('Desktop and Staff Console token set', () => {
  it('resolves the inherited role colours from the brand anchors', () => {
    expect(palettes.light.surface).toBe('#FAF8F4');
    expect(palettes.light.surfaceSecondary).toBe('#EEEFE8');
    expect(palettes.light.textPrimary).toBe('#1B1C1A');
    expect(palettes.light.textSecondary).toBe('#5B5F54');
    expect(palettes.light.border).toBe('#C6C9BE');
    expect(palettes.light.primary[500]).toBe('#12805C');
  });

  it('carries independent dark values, not sibling -dark tokens', () => {
    expect(palettes.dark.surface).toBe('#17181A');
    expect(palettes.dark.primary[500]).toBe('#3FA981');
    expect(palettes.dark.onError).toBe('#17181A');
  });

  it('pins the layout, density, and shell tokens to the documented values', () => {
    expect(layout.bpConsoleSm).toBe(1024);
    expect(layout.bpConsoleMd).toBe(1440);
    expect(layout.bpConsoleLg).toBe(1920);
    expect(layout.contentMax).toBe(1280);
    expect(layout.shellMin).toBe(1024);

    expect(density.rowHeight).toBe(40);
    expect(density.rowHeightCompact).toBe(32);
    expect(density.controlHeight).toBe(36);
    expect(density.controlHeightSm).toBe(32);
    expect(density.cellPadX).toBe(12);
    expect(density.cellPadY).toBe(8);
    expect(density.checkboxSize).toBe(16);
    expect(density.checkboxHitArea).toBe(24);

    expect(shell.sidebarWidth).toBe(240);
    expect(shell.sidebarWidthCollapsed).toBe(64);
    expect(shell.sidebarItemHeight).toBe(40);
    expect(shell.topbarHeight).toBe(56);
  });

  it('pins the inherited spacing, radius, and icon scales', () => {
    expect(space).toMatchObject({ xs: 4, sm: 8, md: 16, lg: 24, xl: 32, xxl: 48, xxxl: 64 });
    expect(radius).toEqual({ sm: 4, md: 8, lg: 12, full: 9999 });
  });

  it('emits every token as a CSS custom property for the active palette', () => {
    const vars = cssVariables(palettes.light) as Record<string, string>;
    expect(vars['--color-surface']).toBe('#FAF8F4');
    expect(vars['--color-primary-500']).toBe('#12805C');
    expect(vars['--control-height']).toBe('36px');
    expect(vars['--row-height']).toBe('40px');
    expect(vars['--sidebar-width']).toBe('240px');
    expect(vars['--content-max']).toBe('1280px');
    expect(vars['--space-lg']).toBe('24px');
    expect(vars['--radius-md']).toBe('8px');
    expect(vars['--disabled-opacity']).toBe('0.5');
  });

  it('generates all nine primary shades and five semantic scales', () => {
    for (const step of [100, 200, 300, 400, 500, 600, 700, 800, 900]) {
      expect(palettes.light.primary[step]).toMatch(/^#[0-9A-F]{6}$/);
    }
    for (const name of ['success', 'warning', 'error', 'info', 'accent']) {
      for (const step of [100, 300, 500, 700, 900]) {
        expect(palettes.light.semantic[name]?.[step]).toMatch(/^#[0-9A-F]{6}$/);
        expect(palettes.dark.semantic[name]?.[step]).toMatch(/^#[0-9A-F]{6}$/);
      }
    }
  });
});
