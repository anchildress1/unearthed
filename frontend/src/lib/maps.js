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
 * Idiomatic reimplementation of the 2024+ Google Maps dynamic library
 * import bootstrap (see developers.google.com/maps/documentation/
 * javascript/load-maps-js-api). The published snippet is minified;
 * this rewrite preserves the exact contract — exposes
 * `google.maps.importLibrary(name)`, lazily injects the API script on
 * first call, and batches concurrent `importLibrary` calls into a
 * single network fetch — while using let/const, non-async executors,
 * and idiomatic control flow. Callers each `await importLibrary(X)`
 * for exactly the library they need (Hero → 'places',
 * MapSection → 'maps' + 'geometry', H3Density → 'maps'). Once the
 * script loads, Google replaces `google.maps.importLibrary` with its
 * real implementation and the shim's recursive call hits that.
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

	installImportLibraryShim({ key, v: 'weekly' });
	return Promise.resolve();
}

/**
 * Installs the shim that Google's dynamic-bootstrap doc snippet installs.
 * Split out so the nesting stays shallow and each step reads as prose.
 */
function installImportLibraryShim(config) {
	const ERROR_PREFIX = 'The Google Maps JavaScript API';
	const google = globalThis.google ?? (globalThis.google = {});
	const maps = google.maps ?? (google.maps = {});

	if (maps.importLibrary) {
		// eslint-disable-next-line no-console
		console.warn(`${ERROR_PREFIX} only loads once. Ignoring:`, config);
		return;
	}

	const requestedLibs = new Set();
	let scriptPromise = null;

	maps.importLibrary = (name, ...rest) => {
		requestedLibs.add(name);
		return ensureScriptLoaded(config, requestedLibs, ERROR_PREFIX).then(() =>
			maps.importLibrary(name, ...rest),
		);
	};

	function ensureScriptLoaded(cfg, libs, errorPrefix) {
		if (scriptPromise) return scriptPromise;
		scriptPromise = new Promise((resolve, reject) => {
			const script = document.createElement('script');
			const params = new URLSearchParams();
			params.set('libraries', [...libs].join(','));
			for (const [k, v] of Object.entries(cfg)) {
				const param = k.replaceAll(/[A-Z]/g, (t) => '_' + t.toLowerCase());
				params.set(param, v);
			}
			params.set('callback', 'google.maps.__ib__');
			script.src = `https://maps.googleapis.com/maps/api/js?${params}`;
			maps.__ib__ = resolve;
			script.onerror = () => {
				scriptPromise = null;
				reject(new Error(`${errorPrefix} could not load.`));
			};
			script.nonce = document.querySelector('script[nonce]')?.nonce || '';
			document.head.append(script);
		});
		return scriptPromise;
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
 * `subtitle` (optional): a third mono line under the name, used to surface
 * identifiers/geography ("MSHA 46-09627 · Raleigh Co., WV"). All three tag
 * kinds (MINE / PLANT / METER) share chrome and typography; only the glyph
 * shape changes so the reader can tell them apart at a glance.
 */
const PIN_TRANSFORMS = {
	above: 'translate(-50%, calc(-100% - 14px))',
	below: 'translate(-50%, 14px)',
	left: 'translate(calc(-100% - 14px), -50%)',
	right: 'translate(14px, -50%)',
};

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
		'background:#be573b',
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
	{ type, name, subtitle = '', placement = 'above' },
) {
	const card = document.createElement('div');
	card.style.cssText = [
		'position:absolute',
		`transform:${PIN_TRANSFORMS[placement] || PIN_TRANSFORMS.above}`,
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
		"font-family:'JetBrains Mono',monospace;font-size:9px;color:#be573b;text-transform:uppercase;letter-spacing:0.12em";
	typeEl.textContent = type;
	typeRow.appendChild(typeEl);
	card.appendChild(typeRow);

	if (name) {
		const nameEl = document.createElement('div');
		nameEl.style.cssText =
			"font-family:Newsreader,serif;font-size:12px;color:#e8dfcc;margin-top:1px";
		nameEl.textContent = name;
		card.appendChild(nameEl);
	}
	if (subtitle) {
		const subEl = document.createElement('div');
		subEl.style.cssText =
			"font-family:'JetBrains Mono',monospace;font-size:9px;color:#a89e92;margin-top:2px;letter-spacing:0.04em";
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
