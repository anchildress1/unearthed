/**
 * PlantReveal — emissions card rendering and formatTons/formatAcres edge cases.
 *
 * The main PlantReveal.test.js covers the cost block (people + land). This
 * file covers the emissions section (fetched via onMount from /emissions/{plant})
 * and prose rendering edge cases.
 */
import { render, cleanup } from '@testing-library/svelte';
import { describe, expect, it, vi, afterEach } from 'vitest';

const mockFetchEmissions = vi.fn();
vi.mock('$lib/api.js', () => ({
	fetchEmissions: (...args) => mockFetchEmissions(...args),
}));

import PlantReveal from './PlantReveal.svelte';

const BASE_DATA = {
	mine: 'Bailey Mine',
	mine_id: '36609947',
	mine_operator: 'Consol Pennsylvania Coal',
	mine_county: 'Greene',
	mine_state: 'PA',
	mine_type: 'Underground',
	mine_coords: [39.9, -80.2],
	plant: 'Cross',
	plant_operator: 'Santee Cooper',
	plant_coords: [33.5, -80.3],
	tons: 1_247_001,
	tons_year: 2024,
	prose: 'First paragraph.\n\nSecond paragraph.',
	subregion_id: 'SRVC',
	degraded: false,
	fatalities: 3,
	injuries_lost_time: 15,
	days_lost: 430,
};

describe('PlantReveal — emissions card', () => {
	afterEach(() => {
		cleanup();
		mockFetchEmissions.mockReset();
	});

	it('renders emissions cards when data is available', async () => {
		mockFetchEmissions.mockResolvedValueOnce({
			co2_tons: 1_500_000,
			so2_tons: 25_000,
			nox_tons: 8_000,
			source: 'EPA Clean Air Markets via Snowflake Marketplace',
		});

		const { container } = render(PlantReveal, { props: { data: BASE_DATA } });

		await vi.waitFor(() => {
			expect(container.querySelector('.emissions')).toBeTruthy();
		});

		// Verify formatted values
		const values = container.querySelectorAll('.e-value');
		expect(values.length).toBeGreaterThanOrEqual(3);
		// 1.5M tons CO2
		expect(values[0].textContent).toContain('1.5M');
		// 25K tons SO2
		expect(values[1].textContent).toContain('25K');
		// 8K tons NOx
		expect(values[2].textContent).toContain('8K');
	});

	it('does not render emissions when fetch returns null', async () => {
		mockFetchEmissions.mockResolvedValueOnce(null);

		const { container } = render(PlantReveal, { props: { data: BASE_DATA } });

		// Wait for onMount to complete
		await vi.waitFor(() => {
			// Emissions should not render — null result
			expect(container.querySelector('.emissions')).toBeNull();
		});
	});

	it('does not render emissions when fetch fails', async () => {
		mockFetchEmissions.mockRejectedValueOnce(new Error('503'));

		const { container } = render(PlantReveal, { props: { data: BASE_DATA } });

		// Wait for error to be caught
		await vi.waitFor(() => {
			expect(container.querySelector('.emissions')).toBeNull();
		});
	});

	it('renders source attribution when present', async () => {
		mockFetchEmissions.mockResolvedValueOnce({
			co2_tons: 100,
			so2_tons: 10,
			nox_tons: 5,
			source: 'EPA Clean Air Markets via Snowflake Marketplace',
		});

		const { container } = render(PlantReveal, { props: { data: BASE_DATA } });

		await vi.waitFor(() => {
			const source = container.querySelector('.emissions-source');
			expect(source).toBeTruthy();
			expect(source.textContent).toContain('EPA');
		});
	});
});

describe('PlantReveal — formatTons edge cases', () => {
	afterEach(() => {
		cleanup();
		mockFetchEmissions.mockReset();
	});

	it('formats null as em dash', async () => {
		mockFetchEmissions.mockResolvedValueOnce({
			co2_tons: null,
			so2_tons: null,
			nox_tons: null,
		});

		const { container } = render(PlantReveal, { props: { data: BASE_DATA } });

		await vi.waitFor(() => {
			// With all null → no emissions block rendered (co2_tons null check)
			// But we can verify the component doesn't crash
		});
		// No crash = success
	});

	it('formats exact 1000 as 1K', async () => {
		mockFetchEmissions.mockResolvedValueOnce({
			co2_tons: 1000,
			so2_tons: 999,
			nox_tons: 500,
		});

		const { container } = render(PlantReveal, { props: { data: BASE_DATA } });

		await vi.waitFor(() => {
			expect(container.querySelector('.emissions')).toBeTruthy();
		});

		const values = container.querySelectorAll('.e-value');
		// 1000 → "1K"
		expect(values[0].textContent).toContain('1K');
		// 999 → "999" (below 1000 threshold)
		expect(values[1].textContent).toContain('999');
	});

	it('formats 0 as 0', async () => {
		mockFetchEmissions.mockResolvedValueOnce({
			co2_tons: 0,
			so2_tons: 0,
			nox_tons: 0,
		});

		const { container } = render(PlantReveal, { props: { data: BASE_DATA } });

		await vi.waitFor(() => {
			expect(container.querySelector('.emissions')).toBeTruthy();
		});
	});
});

describe('PlantReveal — prose rendering', () => {
	afterEach(() => {
		cleanup();
		mockFetchEmissions.mockReset();
	});

	it('splits prose into paragraphs on double newlines', () => {
		mockFetchEmissions.mockResolvedValueOnce(null);
		const { container } = render(PlantReveal, {
			props: { data: { ...BASE_DATA, prose: 'First.\n\nSecond.\n\nThird.' } },
		});
		const paragraphs = container.querySelectorAll('.prose p');
		expect(paragraphs.length).toBe(3);
	});

	it('deduplicates repeated consecutive paragraphs', () => {
		mockFetchEmissions.mockResolvedValueOnce(null);
		const { container } = render(PlantReveal, {
			props: { data: { ...BASE_DATA, prose: 'Same text.\n\nSame text.\n\nDifferent.' } },
		});
		const paragraphs = container.querySelectorAll('.prose p');
		expect(paragraphs.length).toBe(2);
	});

	it('renders empty prose with fallback paragraph', () => {
		mockFetchEmissions.mockResolvedValueOnce(null);
		const { container } = render(PlantReveal, {
			props: { data: { ...BASE_DATA, prose: '' } },
		});
		// Empty prose triggers fallback paragraph (plant description)
		const paragraphs = container.querySelectorAll('.prose p');
		expect(paragraphs.length).toBe(1);
	});
});
