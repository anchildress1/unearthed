import { render, cleanup } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import Ticker from './Ticker.svelte';

const DATA = {
	mine: 'Bailey Mine',
	mine_county: 'Greene',
	mine_state: 'PA',
	plant: 'Cross',
	tons: 1_247_001,
	tons_year: 2024,
};

describe('Ticker — initial render', () => {
	afterEach(cleanup);

	it('renders the section heading', () => {
		const { container } = render(Ticker, { props: { data: DATA } });
		expect(container.textContent).toContain('seam');
	});

	it('renders the counter starting at 0.00', () => {
		const { container } = render(Ticker, { props: { data: DATA } });
		const number = container.querySelector('.number');
		expect(number).toBeTruthy();
		expect(number.textContent).toBe('0.00');
	});

	it('renders the unit labels', () => {
		const { container } = render(Ticker, { props: { data: DATA } });
		expect(container.querySelector('.unit-primary').textContent).toContain('tons of coal');
		expect(container.querySelector('.unit-secondary').textContent).toContain('2024');
	});

	it('renders the closing paragraph with mine county and plant', () => {
		const { container } = render(Ticker, { props: { data: DATA } });
		const closing = container.querySelector('.closing');
		expect(closing.textContent).toContain('Greene');
		expect(closing.textContent).toContain('Cross');
	});

	it('renders the dedication block', () => {
		const { container } = render(Ticker, { props: { data: DATA } });
		const ded = container.querySelector('.dedication');
		expect(ded).toBeTruthy();
		expect(ded.textContent).toContain('Bailey Mine');
	});
});

describe('Ticker — counter animation', () => {
	let rafCallbacks = [];
	let originalRAF, originalCAF;

	beforeEach(() => {
		originalRAF = globalThis.requestAnimationFrame;
		originalCAF = globalThis.cancelAnimationFrame;
		rafCallbacks = [];
		vi.stubGlobal('requestAnimationFrame', (cb) => {
			rafCallbacks.push(cb);
			return rafCallbacks.length;
		});
		vi.stubGlobal('cancelAnimationFrame', vi.fn());
	});

	afterEach(() => {
		cleanup();
		globalThis.requestAnimationFrame = originalRAF;
		globalThis.cancelAnimationFrame = originalCAF;
	});

	it('starts the animation frame loop on mount', () => {
		render(Ticker, { props: { data: DATA } });
		expect(rafCallbacks.length).toBeGreaterThanOrEqual(1);
	});

	it('schedules successive frames after the first tick', () => {
		render(Ticker, { props: { data: DATA } });

		const initialCount = rafCallbacks.length;
		// First tick sets t0
		rafCallbacks[0](0);
		// Each tick schedules the next frame
		expect(rafCallbacks.length).toBeGreaterThan(initialCount);
	});
});

describe('Ticker — edge cases', () => {
	afterEach(cleanup);

	it('handles zero tonnage without crashing', () => {
		const data = { ...DATA, tons: 0 };
		const { container } = render(Ticker, { props: { data } });
		const number = container.querySelector('.number');
		expect(number.textContent).toBe('0.00');
	});
});
