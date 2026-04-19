import { render } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

// fetchEmissions runs inside PlantReveal's onMount. Stub it to resolve to
// null so the component renders synchronously without a real network call —
// these tests only care about the static cost block driven by props.
vi.mock('$lib/api.js', () => ({
	fetchEmissions: vi.fn().mockResolvedValue(null),
}));

import PlantReveal from './PlantReveal.svelte';

// BASE_DATA intentionally has tons:0 and no mine_type so the landDisturbed
// derivation returns null. That lets the people-subsection tests assert
// without the land subsection also rendering and polluting row counts.
const BASE_DATA = {
	mine: 'Bailey Mine',
	mine_id: '36609947',
	mine_operator: 'Consol Pennsylvania Coal',
	mine_county: 'Greene',
	mine_state: 'PA',
	mine_type: '',
	mine_coords: [39.9, -80.2],
	plant: 'Cross',
	plant_operator: 'Santee Cooper',
	plant_coords: [33.5, -80.3],
	tons: 0,
	tons_year: 2024,
	prose: 'Paragraph.\n\nAnother paragraph.',
	subregion_id: 'SRVC',
	degraded: false,
	fatalities: 0,
	injuries_lost_time: 0,
	days_lost: 0,
	incidents: 0,
};

const peopleGroup = (c) => c.querySelector('.ledger[data-kind="people"]');
const landGroup = (c) => c.querySelector('.ledger[data-kind="land"]');

describe('PlantReveal cost block — people subsection', () => {
	it('renders each ledger row when its value is nonzero', () => {
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

		const group = peopleGroup(container);
		expect(group).toBeTruthy();

		const rows = group.querySelectorAll('.row');
		expect(rows).toHaveLength(3);
		expect(group.textContent).toContain('15');
		expect(group.textContent).toContain('2');
		expect(group.textContent).toContain('430');
	});

	it('omits zero-value rows individually', () => {
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

		const group = peopleGroup(container);
		const rows = group.querySelectorAll('.row');
		expect(rows).toHaveLength(1);
		expect(group.textContent).toContain('15');
	});

	it('hides the people subsection when every stat is zero', () => {
		const { container } = render(PlantReveal, {
			props: { data: BASE_DATA },
		});
		expect(peopleGroup(container)).toBeNull();
	});

	it('places fatalities after injuries when both are present', () => {
		const { container } = render(PlantReveal, {
			props: {
				data: { ...BASE_DATA, fatalities: 1, injuries_lost_time: 4, days_lost: 0 },
			},
		});
		const group = peopleGroup(container);
		const rows = Array.from(group.querySelectorAll('.row'));
		expect(rows).toHaveLength(2);
		expect(rows[0].textContent).toContain('4');
		expect(rows[1].textContent).toContain('1');
		expect(rows[1].classList.contains('row--grave')).toBe(true);
	});

	it('marks the fatalities numeral with the grave modifier', () => {
		const { container } = render(PlantReveal, {
			props: { data: { ...BASE_DATA, fatalities: 3 } },
		});
		const grave = peopleGroup(container).querySelector('.numeral--grave');
		expect(grave).toBeTruthy();
		expect(grave.textContent).toContain('3');
	});
});

describe('PlantReveal cost block — land subsection', () => {
	it('renders an inline acres + fields row for surface mines', () => {
		const { container } = render(PlantReveal, {
			props: {
				data: {
					...BASE_DATA,
					mine_type: 'Surface',
					mine_state: 'WV',
					tons: 1_500_000,
				},
			},
		});
		const group = landGroup(container);
		expect(group).toBeTruthy();
		expect(group.querySelector('.ledger-inline')).toBeTruthy();
		expect(group.querySelectorAll('.inline-row')).toHaveLength(2);
	});

	it('renders a prose note for underground mines instead of inline data', () => {
		const { container } = render(PlantReveal, {
			props: {
				data: {
					...BASE_DATA,
					mine_type: 'Underground',
					tons: 1_247_001,
				},
			},
		});
		const group = landGroup(container);
		expect(group).toBeTruthy();
		expect(group.querySelector('.ledger-inline')).toBeNull();
		expect(group.querySelector('.land-note')).toBeTruthy();
	});

	it('hides the land subsection when there is no tonnage', () => {
		const { container } = render(PlantReveal, {
			props: { data: { ...BASE_DATA, tons: 0 } },
		});
		expect(landGroup(container)).toBeNull();
	});
});

describe('PlantReveal cost block — shell', () => {
	it('hides the whole block when neither people nor land has data', () => {
		const { container } = render(PlantReveal, {
			props: { data: BASE_DATA },
		});
		expect(container.querySelector('.cost')).toBeNull();
	});

	it('renders the closing couplet when at least one subsection is present', () => {
		const { container } = render(PlantReveal, {
			props: { data: { ...BASE_DATA, fatalities: 1 } },
		});
		const block = container.querySelector('.cost');
		expect(block).toBeTruthy();
		const kicker = block.querySelector('.cost-kicker');
		expect(kicker).toBeTruthy();
		expect(kicker.querySelector('.kicker-land').textContent).toMatch(/restored/i);
		expect(kicker.querySelector('.kicker-miners').textContent).toMatch(/cannot/i);
	});

	it('separates people and land sections with a typographic break when both are present', () => {
		const { container } = render(PlantReveal, {
			props: {
				data: {
					...BASE_DATA,
					fatalities: 1,
					mine_type: 'Surface',
					mine_state: 'WV',
					tons: 1_000_000,
				},
			},
		});
		expect(peopleGroup(container)).toBeTruthy();
		expect(landGroup(container)).toBeTruthy();
		expect(container.querySelector('.cost .cost-break')).toBeTruthy();
	});

	it('surfaces the eyebrow attribution and serif title', () => {
		const { container } = render(PlantReveal, {
			props: { data: { ...BASE_DATA, fatalities: 1 } },
		});
		expect(container.querySelector('.cost-eyebrow').textContent).toMatch(/federal public data/i);
		expect(container.querySelector('.cost-title').textContent).toMatch(/this mine/i);
	});
});
