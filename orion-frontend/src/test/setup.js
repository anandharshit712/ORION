// Vitest setup: jest-dom matchers plus a clean slate between tests.
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  // document.cookie persists across tests in jsdom, and the CSRF tests would
  // otherwise pass on a value a previous test left behind.
  document.cookie.split(';').forEach((c) => {
    const name = c.split('=')[0].trim();
    if (name) document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/`;
  });
});

// jsdom implements neither ResizeObserver nor element geometry, and Recharts'
// ResponsiveContainer needs both: without them it throws on mount, so any test
// that renders a chart fails for a reason that has nothing to do with the
// chart. The container is given a fixed size so the SVG actually renders and
// assertions can reach its contents.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = ResizeObserverStub;
}

for (const [prop, value] of [
  ['offsetWidth', 640],
  ['offsetHeight', 320],
  ['clientWidth', 640],
  ['clientHeight', 320],
]) {
  if (!Object.getOwnPropertyDescriptor(HTMLElement.prototype, prop)?.get) {
    Object.defineProperty(HTMLElement.prototype, prop, {
      configurable: true,
      get() {
        return value;
      },
    });
  }
}
