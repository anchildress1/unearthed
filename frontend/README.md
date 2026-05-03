# unearthed — frontend

SvelteKit 2 + Svelte 5 runes, served as a static site via `adapter-static`. All API calls proxy to the FastAPI backend (`/api/*` → `http://localhost:8001` in dev).

## Dev

```sh
pnpm install
pnpm dev          # :5173, proxies /api to :8001
```

Backend must be running separately (`make server` from repo root).

## Build

```sh
pnpm build        # output to .svelte-kit/output/
pnpm preview      # preview the production build locally
```

## Testing

```sh
pnpm test           # Vitest unit/component (watch mode)
pnpm test:run       # Vitest single run
pnpm test:coverage  # coverage report
pnpm test:e2e       # Playwright (requires `pnpm build && pnpm preview` running)
pnpm lhci           # Lighthouse CI against preview server
```

### Test tiers

| Command | Stack | Scope |
|---|---|---|
| `pnpm test:run` | Vitest + jsdom + @testing-library/svelte | Unit: `geo.js`, `api.js`, `reveal.js` + edge suites; Component: `SectionRail`, `PlantReveal` (+ emissions), `CortexChat`, `Ticker` |
| `pnpm test:e2e` | Playwright (Chromium) | Share-URL replay, pushState refresh, editorial rail integrity, error states, Google Maps runtime via behavioral stub |
| `pnpm lhci` | @lhci/cli | Audits `/` against thresholds: a11y=1.0, SEO=1.0, Best Practices≥0.98, Performance≥0.90 |

Lighthouse thresholds are non-negotiable — see `lighthouserc.cjs`. Fix root causes, don't relax gates.

## Sections

| File | Section | What it renders |
|---|---|---|
| `src/lib/sections/Hero.svelte` | N° 01 | Address input + Google Places suggestions + geolocation |
| `src/lib/sections/PlantReveal.svelte` | N° 02 | Mine name, operator, tonnage, MSHA safety ledger, cost block |
| `src/lib/sections/MapSection.svelte` | N° 03 | Animated mine → plant → meter arc, eGRID label, eGRID boundary overlay |
| `src/lib/sections/H3Density.svelte` | N° 04 | National hexbin density map, Cortex summary byline |
| `src/lib/sections/CortexChat.svelte` | N° 05 | Chip questions + free-text Q&A, visible SQL per turn |
| `src/lib/sections/Ticker.svelte` | N° 06 | Live tonnage counter, emissions anchor block |

All sections use `src/lib/components/SectionRail.svelte` for the left-gutter N° / hairline / rotated-label chrome.

## Key lib files

| File | Purpose |
|---|---|
| `src/lib/maps.js` | Idempotent Google Maps bootstrap (`importLibrary` shim) shared by Hero, MapSection, H3Density |
| `src/lib/api.js` | Typed fetch wrappers for all backend endpoints |
| `src/lib/geo.js` | Point-in-polygon (eGRID GeoJSON), coordinate helpers |
| `src/lib/reveal.js` | State machine for the sequential reveal flow |

## E2E fixtures

`e2e/fixtures.js` exports:

- `mockBackend(page)` — Playwright route mocks for `/mine-for-me`, `/emissions/*`, `/h3-density`, `/ask`, and a swallow-route for `maps.googleapis.com`
- `installGoogleMapsStub(page)` — behavioral `google.maps` double that records `new Map`, `new Marker`, and `OverlayView.setMap` calls on `globalThis.__gmapsCalls`

Register test-specific routes **after** `mockBackend` — Playwright matches most-recent-first.

## Environment

`VITE_GOOGLE_MAPS_KEY` is required for Places autocomplete and Maps rendering. Restrict the key to your dev origin (`http://localhost:5173`) and production domain. Enable: Maps JavaScript API, Places API (New).
