import { render } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

// fetchEmissions runs inside PlantReveal's onMount. Stub it to resolve to
// null so the component renders synchronously without a real network call —
// these tests only care about the static miner-toll block driven by props.
vi.mock('$lib/api.js', () => ({
	fetchEmissions: vi.fn().mockResolvedValue(null),
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
	prose: 'Paragraph.\n\nAnother paragraph.',
	subregion_id: 'SRVC',
	degraded: false,
	fatalities: 0,
	injuries_lost_time: 0,
	days_lost: 0,
	incidents: 0,
};

describe('PlantReveal miner toll block', () => {
	it('renders each stat line when its value is nonzero', () => {
		const { container } = render(PlantReveal, {
			props: {
				data: {
					...BASE_DATA,
					fatalities: 2,
					injuries_lost_time: 15,
					days_lost: 430,
					incidents: 60,
				},
			},
		});

		const toll = container.querySelector('.toll');
		expect(toll).toBeTruthy();

		const cards = toll.querySelectorAll('.t-card');
		expect(cards).toHaveLength(3);
		expect(toll.textContent).toContain('15');
		expect(toll.textContent).toContain('2');
		expect(toll.textContent).toContain('430');
	});

	it('omits zero-value cards individually', () => {
		const { container } = render(PlantReveal, {
			props: {
				data: {
					...BASE_DATA,
					fatalities: 0,
					injuries_lost_time: 15,
					days_lost: 0,
				},
			},
		});

		const cards = container.querySelectorAll('.toll .t-card');
		expect(cards).toHaveLength(1);
		expect(container.querySelector('.toll').textContent).toContain('15');
	});

	it('hides the whole block when every stat is zero', () => {
		const { container } = render(PlantReveal, {
			props: { data: BASE_DATA },
		});
		expect(container.querySelector('.toll')).toBeNull();
	});

	it('places fatalities after injuries when both are present', () => {
		const { container } = render(PlantReveal, {
			props: {
				data: { ...BASE_DATA, fatalities: 1, injuries_lost_time: 4, days_lost: 0 },
			},
		});
		const cards = Array.from(container.querySelectorAll('.toll .t-card'));
		expect(cards).toHaveLength(2);
		expect(cards[0].textContent).toContain('4');
		expect(cards[1].textContent).toContain('1');
	});
});
