/**
 * Shared Google Maps loader + style tokens.
 *
 * One loader so both map sections get the same script (idempotent — a repeat
 * call while the script is already attached resolves on the existing tag's
 * load event). One style array so both maps share the same identity: dark
 * empty canvas, state outlines only, no roads, no place labels, no POIs.
 *
 * Advanced Markers would require a cloud-registered mapId, which would move
 * the style decision out of this repo and into the Google Cloud Console.
 * We use legacy google.maps.Marker here so the `styles` array below is the
 * single source of truth for how both maps look.
 */

/**
 * Install the Google Maps Dynamic Library Import bootstrap.
 *
 * The traditional `<script src="…/js?libraries=…">` loader only exposes
 * the classic globals and does NOT install `google.maps.importLibrary`.
 * The Places API (New) classes — `AutocompleteSuggestion`, `Place`, etc.
 * — are only reachable via `importLibrary`, so the Hero autocomplete
 * fails without this bootstrap.
 *
 * Bootstrap snippet is verbatim from the 2024+ Maps JS API docs, wrapped
 * to take `key` and `v` as config. It synchronously defines
 * `google.maps.importLibrary`; callers then each `await importLibrary(X)`
 * for exactly the library they need — Hero needs 'places', MapSection
 * needs 'maps' + 'geometry', H3Density needs 'maps'. The bootstrap
 * batches concurrent requests into a single script tag, so four callers
 * asking for four libraries still trigger one network fetch. A 15 s
 * `setTimeout` watchdog rejects the load promise if the script is blocked
 * by a privacy tool or CSP without firing `onerror`.
 *
 * Do not pre-import libraries here. Each caller is responsible for
 * requesting the scope it uses — that's the whole point of dynamic
 * import (billing is per-library, unused libraries shouldn't load at
 * all). Loading 'places' alongside 'maps' meant every landing-page view
 * pulled the Places API even when the user never typed into the input.
 */
export function loadGoogleMaps() {
	if (globalThis.window === undefined) {
		return Promise.reject(new Error('loadGoogleMaps can only run in the browser'));
	}
	if (typeof globalThis.google?.maps?.importLibrary === 'function') {
		return Promise.resolve();
	}
	const key = import.meta.env.VITE_GOOGLE_MAPS_KEY || '';
	if (!key) {
		return Promise.reject(new Error('VITE_GOOGLE_MAPS_KEY not set — map cannot load'));
	}

	_installMapsBootstrap({ key, v: 'weekly' });
	return Promise.resolve();
}

// Converts camelCase config keys to snake_case URL params (e.g. apiVersion → api_version).
function _toSnakeParam(k) {
	return k.replaceAll(/[A-Z]/g, (ch) => '_' + ch.toLowerCase());
}

// Installs google.maps.importLibrary using the Dynamic Library Import bootstrap
// (verbatim logic from Maps JS API 2024+ docs, rewritten for readability and lint).
// Batches concurrent importLibrary calls into one <script> tag; idempotent on repeat calls.
function _installMapsBootstrap(config) {
	const NS = 'The Google Maps JavaScript API';
	const G = 'google';
	const IMPORT_LIB = 'importLibrary';
	const CB = '__ib__';

	const doc = document;
	let loadPromise;
	let scriptTag;

	const gObj = globalThis[G] || (globalThis[G] = {});
	const mapsObj = gObj.maps || (gObj.maps = {});
	const libs = new Set();
	const params = new URLSearchParams();

	const LOAD_TIMEOUT_MS = 15_000;

	const load = () => loadPromise || (loadPromise = new Promise((resolve, reject) => {
		const timer = setTimeout(() => {
			loadPromise = undefined;
			reject(new Error(NS + ' timed out after 15 s — check network or Content-Security-Policy.'));
		}, LOAD_TIMEOUT_MS);

		scriptTag = doc.createElement('script');
		params.set('libraries', [...libs] + '');
		for (const k in config) {
			params.set(_toSnakeParam(k), config[k]);
		}
		params.set('callback', `${G}.maps.${CB}`);
		scriptTag.src = `https://maps.${G}apis.com/maps/api/js?` + params;
		mapsObj[CB] = () => { clearTimeout(timer); resolve(); };
		scriptTag.onerror = () => {
			clearTimeout(timer);
			loadPromise = undefined;
			reject(new Error(NS + ' could not load.'));
		};
		scriptTag.nonce = doc.querySelector('script[nonce]')?.nonce || '';
		doc.head.append(scriptTag);
	}));

	if (mapsObj[IMPORT_LIB]) {
		// eslint-disable-next-line no-console
		console.warn(NS + ' only loads once. Ignoring:', config);
	} else {
		mapsObj[IMPORT_LIB] = (lib, ...rest) => {
			libs.add(lib);
			return load().then(() => mapsObj[IMPORT_LIB](lib, ...rest));
		};
	}
}

/**
 * A styled roadmap with state (province) outlines only.
 *
 * Every feature type is set to `visibility: off` except
 * `administrative.province` (US state borders) and `administrative.country`
 * (national border). Water uses near-black so oceans read as emptiness, not
 * maps. Stroke colors are muted but still readable against the #141210
 * landscape fill — anything darker disappears.
 */
export const DARK_STATE_STYLES = [
	{ elementType: 'geometry', stylers: [{ color: '#141210' }] },
	{ elementType: 'labels', stylers: [{ visibility: 'off' }] },
	{ featureType: 'administrative', stylers: [{ visibility: 'off' }] },
	{
		featureType: 'administrative.country',
		elementType: 'geometry.stroke',
		stylers: [{ visibility: 'on' }, { color: '#6e6359' }, { weight: 1.2 }],
	},
	{
		featureType: 'administrative.province',
		elementType: 'geometry.stroke',
		stylers: [{ visibility: 'on' }, { color: '#4a423a' }, { weight: 0.9 }],
	},
	{ featureType: 'landscape', stylers: [{ color: '#141210' }] },
	{ featureType: 'poi', stylers: [{ visibility: 'off' }] },
	{ featureType: 'road', stylers: [{ visibility: 'off' }] },
	{ featureType: 'transit', stylers: [{ visibility: 'off' }] },
	{ featureType: 'water', stylers: [{ color: '#070605' }] },
	{ featureType: 'water', elementType: 'labels', stylers: [{ visibility: 'off' }] },
];

/**
 * Palette shared across both maps. The CSS layer uses the same tokens as
 * custom properties (`--rust`, `--green`, …), but Google Maps icons and
 * polylines need raw hex strings — icons are drawn on a separate canvas
 * that doesn't see CSS vars. Keeping one JS source of truth avoids drift.
 * `rust` matches the OKLCH `--rust` dim tier; reserve `rustBright` for
 * charged moments (selection, active state).
 */
export const MAP_COLORS = Object.freeze({
	rust: '#be573b',
	rustBright: '#f47249',
	moss: '#5a7a5a',
	you: '#e8dfcc',
	ash: '#a89e92',
	white: '#ffffff',
});

export function circleIcon({ color, scale = 7, strokeWeight = 2, strokeColor = MAP_COLORS.white }) {
	return {
		path: google.maps.SymbolPath.CIRCLE,
		scale,
		fillColor: color,
		fillOpacity: 1,
		strokeColor,
		strokeWeight,
	};
}

/**
 * Build a map element with the site's shared visual identity. Local styles
 * are the source of truth, so no `mapId` — setting one disables the styles
 * array silently.
 */
export function createDarkMap(el, extra = {}) {
	return new google.maps.Map(el, {
		mapTypeId: 'roadmap',
		styles: DARK_STATE_STYLES,
		backgroundColor: '#141210',
		disableDefaultUI: true,
		zoomControl: true,
		scrollwheel: false,
		disableDoubleClickZoom: true,
		keyboardShortcuts: false,
		...extra,
	});
}

/**
 * Attach a dark HTML pin card above a marker. Uses OverlayView so the card
 * rides the map's own transform: the floatPane is translated on pan/zoom by
 * Google, so we only reposition on projection-relevant events (draw() fires
 * whenever zoom or bounds change). InfoWindow was the old fallback — its
 * white chrome read as a tooltip, not as editorial labelling, and it stole
 * click focus. Returns the OverlayView so the caller can setMap(null) to
 * remove it.
 *
 * `placement` (optional): `'above' | 'below' | 'left' | 'right'` — which
 * side of the marker the card floats on. Used for fan-out when two markers
 * are close enough that their default (above) cards would stack.
 *
 * `offsetPx` (optional, default 14): pixel gap between marker and card edge.
 * Boost this when markers cluster tightly — above+below cards separated by
 * only 14px each intersect once the cluster shrinks below ~140px in pixel
 * space. MapSection scales it with cluster density; callers with a single
 * label (H3Density's mine anchor) can leave it at the default.
 *
 * `subtitle` (optional): a third mono line under the name, used to surface
 * identifiers/geography ("MSHA 46-09627 · Raleigh Co., WV"). All three tag
 * kinds (MINE / PLANT / METER) share chrome and typography; only the glyph
 * shape changes so the reader can tell them apart at a glance.
 */
// Card transform relative to the marker's pixel position. `offsetPx` is the
// gap between marker and card edge; callers boost it when markers cluster
// so close that a default 14px gap lets neighboring cards intersect.
function pinTransform(placement, offsetPx) {
	switch (placement) {
		case 'below':
			return `translate(-50%, ${offsetPx}px)`;
		case 'left':
			return `translate(calc(-100% - ${offsetPx}px), -50%)`;
		case 'right':
			return `translate(${offsetPx}px, -50%)`;
		case 'above':
		default:
			return `translate(-50%, calc(-100% - ${offsetPx}px))`;
	}
}

// Semantic glyph per tag type. MINE → rotated square reads as diamond,
// PLANT → flat square reads as industrial, METER/YOU → circle reads as
// endpoint. All render at 8px in rust so the tag family stays one voice.
function glyphShapeFor(type) {
	const upper = (type || '').toUpperCase();
	if (upper === 'MINE') return 'diamond';
	if (upper === 'PLANT') return 'square';
	return 'circle'; // METER, YOU, and any future point-of-delivery kinds
}

function buildGlyph(shape) {
	const el = document.createElement('span');
	const base = [
		'display:inline-block',
		'width:8px',
		'height:8px',
		`background:${MAP_COLORS.rust}`,
		'vertical-align:middle',
		'margin-right:6px',
		'flex-shrink:0',
	];
	if (shape === 'diamond') base.push('transform:rotate(45deg)');
	else if (shape === 'circle') base.push('border-radius:50%');
	// square: no extra
	el.style.cssText = base.join(';');
	return el;
}

export function createLabeledMarker(
	map,
	marker,
	{ type, name, subtitle = '', placement = 'above', offsetPx = 14 },
) {
	const card = document.createElement('div');
	card.style.cssText = [
		'position:absolute',
		`transform:${pinTransform(placement, offsetPx)}`,
		'padding:6px 10px',
		'background:rgba(20,18,16,0.92)',
		'border:1px solid rgba(255,255,255,0.08)',
		'border-radius:6px',
		'pointer-events:none',
		'white-space:nowrap',
		'line-height:1.25',
		'backdrop-filter:blur(8px)',
		'-webkit-backdrop-filter:blur(8px)',
		'box-shadow:0 4px 14px rgba(0,0,0,0.4)',
	].join(';');

	// Row 1 — glyph + type eyebrow. Flex so the glyph centers to the cap
	// height instead of floating above baseline.
	const typeRow = document.createElement('div');
	typeRow.style.cssText = 'display:flex;align-items:center';
	typeRow.appendChild(buildGlyph(glyphShapeFor(type)));
	const typeEl = document.createElement('span');
	typeEl.style.cssText =
		`font-family:'JetBrains Mono',monospace;font-size:9px;color:${MAP_COLORS.rust};text-transform:uppercase;letter-spacing:0.12em`;
	typeEl.textContent = type;
	typeRow.appendChild(typeEl);
	card.appendChild(typeRow);

	if (name) {
		const nameEl = document.createElement('div');
		nameEl.style.cssText =
			`font-family:Newsreader,serif;font-size:12px;color:${MAP_COLORS.you};margin-top:1px`;
		nameEl.textContent = name;
		card.appendChild(nameEl);
	}
	if (subtitle) {
		const subEl = document.createElement('div');
		subEl.style.cssText =
			`font-family:'JetBrains Mono',monospace;font-size:9px;color:${MAP_COLORS.ash};margin-top:2px;letter-spacing:0.04em`;
		subEl.textContent = subtitle;
		card.appendChild(subEl);
	}

	class PinCardOverlay extends google.maps.OverlayView {
		onAdd() {
			this.getPanes().floatPane.appendChild(card);
		}
		draw() {
			const proj = this.getProjection();
			if (!proj) return;
			const pos = marker.getPosition();
			if (!pos) return;
			const px = proj.fromLatLngToDivPixel(pos);
			card.style.left = `${px.x}px`;
			card.style.top = `${px.y}px`;
		}
		onRemove() {
			card.remove();
		}
	}

	const overlay = new PinCardOverlay();
	overlay.setMap(map);
	return overlay;
}

/**
 * Draw a single connected flow line through `waypoints` as an SVG path in
 * the map's overlay pane. Animates with two distinct beats:
 *   1. Reveal — stroke-dashoffset falls from totalLength → 0 over `revealMs`,
 *      so the line draws itself from the first waypoint to the last.
 *   2. Pulse — once drawn, a small circle rides the path via
 *      `getPointAtLength`, looping every `pulseMs` so the reader sees the
 *      coal *moving*, not just sitting there.
 *
 * The geodesic between each pair of waypoints is sampled into `arcSegments`
 * points and concatenated into one SVG `d` string, so the pulse never
 * teleports across a segment boundary. `draw()` re-projects the path on
 * every zoom/pan so the SVG stays registered with the map. Animation state
 * (reveal progress, pulse phase) is stored outside draw() so a redraw
 * mid-reveal continues from the current progress against the new path
 * length instead of restarting.
 *
 * Returns the OverlayView so the caller can detach via `setMap(null)`; the
 * internal rAF loop is canceled in `onRemove()`.
 *
 * Replaces the old `google.maps.Polyline` + `setInterval`-driven marker,
 * which drew the path as one static line with an icon bouncing between two
 * endpoints. The SVG path lets us express the "coal is flowing" metaphor
 * as motion along the visible line instead of a separate marker.
 */
export function createFlowOverlay(
	map,
	waypoints,
	{
		color = MAP_COLORS.rust,
		weight = 2.5,
		revealMs = 1400,
		pulseMs = 2600,
		arcSegments = 60,
	} = {},
) {
	const svgNS = 'http://www.w3.org/2000/svg';
	const svg = document.createElementNS(svgNS, 'svg');
	svg.setAttribute(
		'style',
		'position:absolute;top:0;left:0;width:1px;height:1px;overflow:visible;pointer-events:none',
	);

	const path = document.createElementNS(svgNS, 'path');
	path.setAttribute('fill', 'none');
	path.setAttribute('stroke', color);
	path.setAttribute('stroke-width', String(weight));
	path.setAttribute('stroke-opacity', '0.65');
	path.setAttribute('stroke-linecap', 'round');
	path.setAttribute('stroke-linejoin', 'round');
	svg.appendChild(path);

	const pulse = document.createElementNS(svgNS, 'circle');
	pulse.setAttribute('r', '4');
	// Coal-dark fill with a rust ring. The bead reads as a piece of coal
	// riding the route — the same dark as the map canvas (#141210), so
	// the dot "punches through" the rust line rather than competing with
	// it. The rust stroke keeps it legible at small size against the
	// dark landscape where a pure-black dot would vanish on pan.
	pulse.setAttribute('fill', '#141210');
	pulse.setAttribute('stroke', color);
	pulse.setAttribute('stroke-width', '1.5');
	pulse.setAttribute('opacity', '0');
	svg.appendChild(pulse);

	const latLngs = waypoints.map((w) => new google.maps.LatLng(w.lat, w.lng));
	let raf = null;
	let animStart = null;
	let pathLength = 0;

	class FlowOverlay extends google.maps.OverlayView {
		onAdd() {
			this.getPanes().overlayLayer.appendChild(svg);
		}
		draw() {
			const proj = this.getProjection();
			if (!proj) return;

			const parts = [];
			for (let i = 0; i < latLngs.length - 1; i++) {
				const a = latLngs[i];
				const b = latLngs[i + 1];
				for (let j = 0; j <= arcSegments; j++) {
					const p = google.maps.geometry.spherical.interpolate(
						a,
						b,
						j / arcSegments,
					);
					const px = proj.fromLatLngToDivPixel(p);
					parts.push(
						i === 0 && j === 0 ? `M${px.x},${px.y}` : `L${px.x},${px.y}`,
					);
				}
			}
			path.setAttribute('d', parts.join(' '));
			pathLength = path.getTotalLength();
			path.style.strokeDasharray = String(pathLength);

			if (animStart == null) {
				path.style.strokeDashoffset = String(pathLength);
				animStart = performance.now();
				this.#tick(animStart);
			}
		}
		#tick(now) {
			const elapsed = now - animStart;
			const revealT = Math.min(1, elapsed / revealMs);
			path.style.strokeDashoffset = String(pathLength * (1 - revealT));

			if (revealT >= 1 && pathLength > 0) {
				pulse.setAttribute('opacity', '1');
				const phase = ((elapsed - revealMs) % pulseMs) / pulseMs;
				const pt = path.getPointAtLength(phase * pathLength);
				pulse.setAttribute('cx', String(pt.x));
				pulse.setAttribute('cy', String(pt.y));
			}
			raf = requestAnimationFrame((t) => this.#tick(t));
		}
		onRemove() {
			if (raf) cancelAnimationFrame(raf);
			raf = null;
			svg.remove();
		}
	}

	const overlay = new FlowOverlay();
	overlay.setMap(map);
	return overlay;
}
