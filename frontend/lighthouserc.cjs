/**
 * Lighthouse CI configuration.
 *
 * Thresholds are load-bearing: accessibility and SEO must ship at 100,
 * best-practices at 98, performance at 90. Anything softer would let
 * regressions slip through and the project's whole pitch is "a credible
 * data product people can actually use" — so a11y / SEO / BP are
 * non-negotiable, and perf stays tight enough to keep hero interactions
 * snappy without demanding impossible bundle splits from a map-heavy app.
 *
 * We audit the built preview (`vite preview`, NOT dev) because the bundle
 * is what the user ships; dev-server code-splitting and HMR would make
 * every run a lie.
 */
module.exports = {
	ci: {
		collect: {
			// LHCI boots `vite preview` for each run, then tears it down.
			// Audit the landing page only. The share-URL path hits Snowflake
			// via the backend proxy, so auditing it here would report stale
			// "page failed to load" scores when the backend isn't running —
			// e2e covers that flow with a mocked backend instead.
			url: ['http://localhost:4173/'],
			startServerCommand: 'pnpm build && pnpm preview --port 4173',
			startServerReadyPattern: 'Local:.*4173',
			startServerReadyTimeout: 180_000,
			numberOfRuns: 1,
			settings: {
				preset: 'desktop',
				chromeFlags: '--no-sandbox --headless=new',
			},
		},
		assert: {
			assertions: {
				'categories:accessibility': ['error', { minScore: 1.0 }],
				'categories:seo': ['error', { minScore: 1.0 }],
				'categories:performance': ['error', { minScore: 0.9 }],
				'categories:best-practices': ['error', { minScore: 0.98 }],
			},
		},
		upload: {
			target: 'temporary-public-storage',
		},
	},
};
