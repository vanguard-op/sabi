import { describe, expect, it, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ConsoleIcon } from '../shell/ConsoleIcon';
import { Sidebar } from '../shell/Sidebar';
import { UnsupportedWidth } from '../shell/UnsupportedWidth';
import { ConsoleShell, useCollapsedSidebar, useSupportedWidth } from '../shell/ConsoleShell';
import { AuthProvider } from '../auth/AuthProvider';
import { ThemeProvider } from '../theme/ThemeProvider';
import { layout, cssVariables, palettes } from '../theme/tokens';
import type { Staff, StaffRole } from '../api/types';

/**
 * Answers `window.matchMedia` from a viewport width so the documented console
 * breakpoints can be exercised. `setup.ts` provides a frozen stub, so each test
 * that needs a width installs this one.
 */
function installViewport(width: number) {
  const matches = (query: string): boolean => {
    const min = /min-width:\s*(\d+)px/.exec(query);
    const max = /max-width:\s*(\d+)px/.exec(query);
    if (min && width < Number(min[1])) return false;
    if (max && width > Number(max[1])) return false;
    return Boolean(min || max);
  };
  const impl = (query: string) =>
    ({
      matches: matches(query),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }) as unknown as MediaQueryList;
  Object.defineProperty(window, 'matchMedia', { writable: true, configurable: true, value: impl });
}

function setStaff(role: StaffRole) {
  const staff: Staff = { staffId: 's1', email: 'a.okafor@sabi.ng', role };
  sessionStorage.setItem('sabi.console.staff', JSON.stringify(staff));
}

function renderShell(width: number) {
  installViewport(width);
  render(
    <ThemeProvider>
      <AuthProvider>
        <MemoryRouter initialEntries={['/providers']}>
          <ConsoleShell />
        </MemoryRouter>
      </AuthProvider>
    </ThemeProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe('ConsoleIcon', () => {
  it('draws on the 24px grid at the inherited navigation icon size', () => {
    const { container } = render(<ConsoleIcon name="home" />);
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute('viewBox', '0 0 24 24');
    expect(svg).toHaveStyle({ width: 'var(--icon-md)', height: 'var(--icon-md)' });
    expect(svg).toHaveAttribute('stroke', 'currentColor');
    expect(svg).toHaveAttribute('stroke-width', '2');
    expect(svg).toHaveAttribute('aria-hidden', 'true');
  });

  it('keeps the icon the same size across every nav glyph', () => {
    const names = ['home', 'documents', 'health', 'audit'] as const;
    const sizes = names.map((name) => {
      const { container, unmount } = render(<ConsoleIcon name={name} />);
      const width = container.querySelector('svg')?.getAttribute('style') ?? '';
      unmount();
      return width;
    });
    expect(new Set(sizes).size).toBe(1);
    expect(sizes[0]).toContain('var(--icon-md)');
  });

  it('exposes an image role only when a title is supplied', () => {
    const plain = render(<ConsoleIcon name="audit" />);
    expect(plain.container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
    plain.unmount();

    const titled = render(<ConsoleIcon name="audit" title="Audit" />);
    expect(titled.container.querySelector('svg')).toHaveAttribute('role', 'img');
  });
});

describe('Sidebar icons', () => {
  function renderSidebar(collapsed: boolean) {
    return render(
      <AuthProvider>
        <MemoryRouter>
          <Sidebar collapsed={collapsed} />
        </MemoryRouter>
      </AuthProvider>,
    );
  }

  it('renders the branded icon set rather than bare unicode glyphs', () => {
    setStaff('administrator');
    const { container } = renderSidebar(false);
    expect(container.querySelectorAll('a.sidebar-item')).toHaveLength(4);
    expect(container.querySelectorAll('a.sidebar-item svg')).toHaveLength(4);
    expect(container.textContent).not.toMatch(/[⌂⌗◉⌸]/);
  });

  it('labels every icon in the expanded rail and hides the label when collapsed', () => {
    setStaff('administrator');
    const expanded = renderSidebar(false);
    expect(screen.getByText('Providers')).toBeInTheDocument();
    expanded.unmount();

    renderSidebar(true);
    expect(screen.getByText('Providers')).toHaveClass('visually-hidden');
  });
});

describe('Console breakpoint behaviour', () => {
  it('reports the supported width at and above shell-min only', () => {
    function Probe() {
      const supported = useSupportedWidth();
      return <span>{supported ? 'supported' : 'unsupported'}</span>;
    }
    function supportedAt(width: number): boolean {
      installViewport(width);
      const probe = render(<Probe />);
      const text = probe.container.textContent;
      probe.unmount();
      return text === 'supported';
    }
    expect(supportedAt(layout.shellMin)).toBe(true);
    expect(supportedAt(layout.shellMin - 1)).toBe(false);
  });

  it('collapses the sidebar between shell-min and bp-console-md, expands at and above bp-console-md', () => {
    function Probe() {
      const collapsed = useCollapsedSidebar();
      return <span>{collapsed ? 'collapsed' : 'expanded'}</span>;
    }
    function stateAt(width: number): string {
      installViewport(width);
      const probe = render(<Probe />);
      const text = probe.container.textContent;
      probe.unmount();
      return text ?? '';
    }
    expect(stateAt(layout.shellMin)).toBe('collapsed');
    expect(stateAt(layout.bpConsoleMd - 1)).toBe('collapsed');
    expect(stateAt(layout.bpConsoleMd)).toBe('expanded');
    expect(stateAt(layout.bpConsoleLg)).toBe('expanded');
  });

  it('shows the unsupported-width state below shell-min instead of the shell', () => {
    setStaff('administrator');
    renderShell(layout.shellMin - 1);
    expect(screen.getByRole('alert')).toHaveTextContent(/needs a wider window/i);
    expect(screen.queryByRole('navigation', { name: /console sections/i })).not.toBeInTheDocument();
  });

  it('renders the shell with a collapsed sidebar at shell-min', () => {
    setStaff('administrator');
    renderShell(layout.shellMin);
    expect(screen.getByRole('navigation', { name: /console sections/i })).toBeInTheDocument();
    expect(document.querySelector('.sidebar-collapsed')).not.toBeNull();
  });

  it('renders the shell with an expanded sidebar at bp-console-md', () => {
    setStaff('administrator');
    renderShell(layout.bpConsoleMd);
    expect(document.querySelector('.sidebar-collapsed')).toBeNull();
    expect(document.querySelector('.sidebar')).not.toBeNull();
  });
});

describe('UnsupportedWidth state', () => {
  it('names the supported minimum in the copy', () => {
    render(<UnsupportedWidth />);
    expect(screen.getByRole('alert')).toHaveTextContent(/1024px/);
  });
});

describe('interaction tokens', () => {
  it('emits the documented desktop interaction states as CSS custom properties', () => {
    const vars = cssVariables(palettes.light) as Record<string, string>;
    expect(vars['--hover-bg']).toBe('var(--color-primary-100)');
    expect(vars['--hover-text']).toBe('var(--color-primary-700)');
    expect(vars['--active-bg']).toBe('var(--color-primary-300)');
    expect(vars['--selected-bg']).toBe('var(--color-primary-100)');
    expect(vars['--skeleton-bg']).toBe('var(--color-surface-secondary)');
  });
});
