import '@testing-library/jest-dom/vitest';

// jsdom doesn't ship IntersectionObserver. Components that mount under
// `use:reveal` (every section wrapper) instantiate one on construction, so
// we provide a no-op stub that satisfies the constructor and disconnect
// contracts. Individual tests can stub a richer observer if they need to
// trigger intersections manually.
if (globalThis.IntersectionObserver === undefined) {
	globalThis.IntersectionObserver = class {
		observe() { /* jsdom stub */ }
		unobserve() { /* jsdom stub */ }
		disconnect() { /* jsdom stub */ }
		takeRecords() { return []; }
	};
}
