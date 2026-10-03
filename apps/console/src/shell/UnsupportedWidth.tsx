import { ConsoleIcon } from './ConsoleIcon';

/**
 * The clear unsupported-width state for viewports narrower than `shell-min`
 * (branding.md: "below that width the console is not supported, and the smallest
 * console layout is the one at `bp-console-sm`"). The console is a desktop,
 * pointer-and-keyboard surface and is never shown as a broken mobile layout; it
 * names the supported minimum and asks the operator to widen the window.
 */
export function UnsupportedWidth(): JSX.Element {
  return (
    <div className="unsupported-width" role="alert">
      <div className="unsupported-card">
        <ConsoleIcon name="health" size="var(--icon-lg)" />
        <h1 className="type-h3">This console needs a wider window</h1>
        <p className="type-body">
          The Sabi Operations Console is a desktop surface and starts at{' '}
          <span className="type-mono">1024px</span> wide. Widen the window or use a
          desktop display to continue.
        </p>
      </div>
    </div>
  );
}
