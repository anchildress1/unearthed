/**
 * Geolocation, point-in-polygon subregion lookup, and browser geolocation.
 */

const COAL_SUBREGIONS = new Set([
	'AKGD', 'AZNM', 'CAMX', 'ERCT', 'FRCC',
	'MROE', 'MROW', 'NWPP', 'RFCE', 'RFCM',
	'RFCW', 'RMPA', 'SPNO', 'SPSO', 'SRMV',
	'SRMW', 'SRSO', 'SRTV', 'SRVC',
]);

let geojsonCache = null;

export async function loadSubregionGeoJSON() {
	if (geojsonCache) return geojsonCache;
	const resp = await fetch('/data/egrid_subregions.geojson');
	if (!resp.ok) throw new Error('Failed to load eGRID GeoJSON');
	geojsonCache = await resp.json();
	return geojsonCache;
}

export function findSubregion(lat, lon, geojson) {
	for (const feature of geojson.features) {
		const type = feature.geometry.type;
		const coords = feature.geometry.coordinates;
		if (type === 'MultiPolygon') {
			for (const polygon of coords) {
				if (pointInPolygonRings(lon, lat, polygon)) return feature.properties.Subregion;
			}
		} else if (type === 'Polygon') {
			if (pointInPolygonRings(lon, lat, coords)) return feature.properties.Subregion;
		}
	}
	return null;
}

function pointInPolygonRings(x, y, rings) {
	let inside = pointInRing(x, y, rings[0]);
	for (let h = 1; h < rings.length; h++) {
		if (pointInRing(x, y, rings[h])) inside = !inside;
	}
	return inside;
}

function pointInRing(x, y, ring) {
	let inside = false;
	for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
		const xi = ring[i][0], yi = ring[i][1];
		const xj = ring[j][0], yj = ring[j][1];
		if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
			inside = !inside;
		}
	}
	return inside;
}

export function hasCoalData(subregionId) {
	return COAL_SUBREGIONS.has(subregionId);
}

export function requestLocation(timeout = 10000) {
	return new Promise((resolve) => {
		if (!navigator.geolocation) { resolve(null); return; }
		navigator.geolocation.getCurrentPosition(
			(pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
			() => resolve(null),
			{ enableHighAccuracy: false, timeout, maximumAge: 300000 },
		);
	});
}
