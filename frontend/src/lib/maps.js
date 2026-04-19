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

let _scriptPromise = null;

// Hard cap so a missing/blocked Google Maps response can't hang the UI
// indefinitely. 15s is comfortably above typical cold-load times and well
// below anything a user would wait without assuming the page is broken.
const MAPS_LOAD_TIMEOUT_MS = 15000;

export function loadGoogleMaps() {
	if (_scriptPromise) return _scriptPromise;

	_scriptPromise = new Promise((resolve, reject) => {
		if (typeof globalThis.window === 'undefined') {
			reject(new Error('loadGoogleMaps can only run in the browser'));
			return;
		}
		if (globalThis.google?.maps) {
			resolve();
			return;
		}
		const key = import.meta.env.VITE_GOOGLE_MAPS_KEY || '';
		if (!key) {
			reject(new Error('VITE_GOOGLE_MAPS_KEY not set — map cannot load'));
			return;
		}

		// A single shared script tag: if another component added it before us
		// and it's already loaded, `load` will not fire again and an
		// addEventListener('load', …) listener would hang forever. Poll
		// briefly for `window.google.maps` to cover the "already loaded
		// between the readiness check above and the querySelector below"
		// race. The timeout below bounds every path so a genuinely stuck
		// load still surfaces to the caller.
		const watchdog = setTimeout(
			() => reject(new Error('Google Maps script timed out')),
			MAPS_LOAD_TIMEOUT_MS,
		);
		const succeed = () => {
			clearTimeout(watchdog);
			resolve();
		};
		const fail = (err) => {
			clearTimeout(watchdog);
			reject(err);
		};

		const existing = document.querySelector('script[data-unearthed-maps]');
		if (existing) {
			const poll = setInterval(() => {
				if (globalThis.google?.maps) {
					clearInterval(poll);
					succeed();
				}
			}, 50);
			existing.addEventListener('load', () => {
				clearInterval(poll);
				succeed();
			});
			existing.addEventListener('error', () => {
				clearInterval(poll);
				fail(new Error('Google Maps failed to load'));
			});
			// Give the watchdog responsibility for stopping the poll if
			// neither event fires and google never appears.
			setTimeout(() => clearInterval(poll), MAPS_LOAD_TIMEOUT_MS);
			return;
		}
		const s = document.createElement('script');
		s.src = `https://maps.googleapis.com/maps/api/js?key=${key}&v=weekly&libraries=geometry`;
		s.async = true;
		s.dataset.unearthedMaps = '1';
		s.onload = () => succeed();
		s.onerror = () => fail(new Error('Google Maps failed to load'));
		document.head.appendChild(s);
	}).catch((err) => {
		// Reset so the next caller can retry after a transient failure
		// (network blip, ad-blocker toggled off, etc.) instead of being
		// locked onto a permanently-rejected promise for the page lifetime.
		_scriptPromise = null;
		throw err;
	});

	return _scriptPromise;
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
 */
const PIN_TRANSFORMS = {
	above: 'translate(-50%, calc(-100% - 14px))',
	below: 'translate(-50%, 14px)',
	left: 'translate(calc(-100% - 14px), -50%)',
	right: 'translate(14px, -50%)',
};

export function createLabeledMarker(map, marker, { type, name, placement = 'above' }) {
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
	const typeEl = document.createElement('div');
	typeEl.style.cssText =
		"font-family:'JetBrains Mono',monospace;font-size:9px;color:#be573b;text-transform:uppercase;letter-spacing:0.12em";
	typeEl.textContent = type;
	card.appendChild(typeEl);
	if (name) {
		const nameEl = document.createElement('div');
		nameEl.style.cssText =
			"font-family:Newsreader,serif;font-size:12px;color:#e8dfcc;margin-top:1px";
		nameEl.textContent = name;
		card.appendChild(nameEl);
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
	pulse.setAttribute('fill', color);
	pulse.setAttribute('stroke', '#ffffff');
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
