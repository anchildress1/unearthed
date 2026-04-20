import { render, fireEvent, cleanup } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

// Mock fetchAsk globally before importing the component.
const mockFetchAsk = vi.fn();
vi.mock('$lib/api.js', () => ({
	fetchAsk: (...args) => mockFetchAsk(...args),
}));

import CortexChat from './CortexChat.svelte';

const PROPS = {
	mineName: 'Bailey Mine',
	plantName: 'Cross',
	subregionId: 'SRVC',
};

describe('CortexChat — initial render', () => {
	it('renders the section heading and pipeline', () => {
		const { container } = render(CortexChat, { props: PROPS });
		expect(container.textContent).toContain('Interrogate');
		expect(container.textContent).toContain('natural language');
		expect(container.textContent).toContain('generated SQL');
	});

	it('renders suggestion chips with mine and plant names', () => {
		const { container } = render(CortexChat, { props: PROPS });
		const chips = container.querySelectorAll('.chip');
		expect(chips.length).toBeGreaterThanOrEqual(5);
		expect(chips[0].textContent).toContain('Bailey Mine');
		expect(chips[1].textContent).toContain('Cross');
	});

	it('does not render an entry card before any question is asked', () => {
		const { container } = render(CortexChat, { props: PROPS });
		expect(container.querySelector('.entry')).toBeNull();
	});

	it('renders the input form with correct attributes', () => {
		const { container } = render(CortexChat, { props: PROPS });
		const input = container.querySelector('input[name="question"]');
		expect(input).toBeTruthy();
		expect(input.getAttribute('maxlength')).toBe('500');
		expect(input.getAttribute('aria-label')).toBe('Ask a question');
	});
});

describe('CortexChat — asking a question', () => {
	beforeEach(() => {
		mockFetchAsk.mockReset();
	});

	it('displays the question in the entry card', async () => {
		mockFetchAsk.mockResolvedValueOnce({
			answer: 'The total is 42.',
			interpretation: 'Restated: how much?',
			sql: 'SELECT 42',
			error: null,
			results: [{ TOTAL: 42 }],
			suggestions: [],
		});

		const { container } = render(CortexChat, { props: PROPS });
		const input = container.querySelector('input[name="question"]');
		const form = container.querySelector('form');

		await fireEvent.input(input, { target: { value: 'How much coal?' } });
		await fireEvent.submit(form);
		// Wait for the async response
		await vi.waitFor(() => {
			expect(container.querySelector('.answer')).toBeTruthy();
		});

		expect(container.querySelector('.q').textContent).toContain('How much coal?');
	});

	it('renders the answer text', async () => {
		mockFetchAsk.mockResolvedValueOnce({
			answer: 'Five million tons.',
			interpretation: null,
			sql: null,
			error: null,
			results: null,
			suggestions: [],
		});

		const { container } = render(CortexChat, { props: PROPS });
		const input = container.querySelector('input[name="question"]');
		const form = container.querySelector('form');
		await fireEvent.input(input, { target: { value: 'How much coal?' } });
		await fireEvent.submit(form);

		await vi.waitFor(() => {
			expect(container.querySelector('.answer').textContent).toContain('Five million tons.');
		});
	});

	it('renders the error message when API fails', async () => {
		mockFetchAsk.mockRejectedValueOnce(new Error('Network error'));

		const { container } = render(CortexChat, { props: PROPS });
		const input = container.querySelector('input[name="question"]');
		const form = container.querySelector('form');
		await fireEvent.input(input, { target: { value: 'test' } });
		await fireEvent.submit(form);

		await vi.waitFor(() => {
			expect(container.querySelector('.error').textContent).toContain('Could not reach');
		});
	});

	it('renders server error from result.error', async () => {
		mockFetchAsk.mockResolvedValueOnce({
			answer: '',
			interpretation: null,
			sql: null,
			error: 'Cortex is down.',
			results: null,
			suggestions: ['Try this?'],
		});

		const { container } = render(CortexChat, { props: PROPS });
		const input = container.querySelector('input[name="question"]');
		const form = container.querySelector('form');
		await fireEvent.input(input, { target: { value: 'test' } });
		await fireEvent.submit(form);

		await vi.waitFor(() => {
			expect(container.querySelector('.error').textContent).toContain('Cortex is down');
		});
	});

	it('renders no-results message for empty SQL result set', async () => {
		mockFetchAsk.mockResolvedValueOnce({
			answer: '',
			interpretation: 'Restated.',
			sql: 'SELECT 1 WHERE FALSE',
			error: null,
			results: [],
			suggestions: [],
		});

		const { container } = render(CortexChat, { props: PROPS });
		const input = container.querySelector('input[name="question"]');
		const form = container.querySelector('form');
		await fireEvent.input(input, { target: { value: 'test' } });
		await fireEvent.submit(form);

		await vi.waitFor(() => {
			expect(container.querySelector('.no-results').textContent).toContain('no rows');
		});
	});

	it('renders the results table with column headers', async () => {
		mockFetchAsk.mockResolvedValueOnce({
			answer: 'Summary.',
			interpretation: 'Restated.',
			sql: 'SELECT MINE_NAME, TONS FROM ...',
			error: null,
			results: [
				{ MINE_NAME: 'Bailey', TONS: 5000000 },
				{ MINE_NAME: 'Hobet', TONS: 2000000 },
			],
			suggestions: [],
		});

		const { container } = render(CortexChat, { props: PROPS });
		const input = container.querySelector('input[name="question"]');
		const form = container.querySelector('form');
		await fireEvent.input(input, { target: { value: 'test' } });
		await fireEvent.submit(form);

		await vi.waitFor(() => {
			const ths = container.querySelectorAll('th');
			expect(ths).toHaveLength(2);
			expect(ths[0].textContent).toContain('MINE NAME');
			const tds = container.querySelectorAll('td');
			expect(tds).toHaveLength(4);
		});
	});

	it('does not submit an empty question', async () => {
		const { container } = render(CortexChat, { props: PROPS });
		const form = container.querySelector('form');
		await fireEvent.submit(form);
		expect(mockFetchAsk).not.toHaveBeenCalled();
	});
});

describe('CortexChat — formatCell', () => {
	it('renders null values as empty strings in table cells', async () => {
		mockFetchAsk.mockResolvedValueOnce({
			answer: 'ok.',
			interpretation: 'ok.',
			sql: 'SELECT 1',
			error: null,
			results: [{ A: null, B: 42, C: 'text' }],
			suggestions: [],
		});

		const { container } = render(CortexChat, { props: PROPS });
		const input = container.querySelector('input[name="question"]');
		const form = container.querySelector('form');
		await fireEvent.input(input, { target: { value: 'test' } });
		await fireEvent.submit(form);

		await vi.waitFor(() => {
			const tds = container.querySelectorAll('td');
			// null → '' (empty), number → locale-formatted, string → as-is
			expect(tds[0].textContent).toBe('');
			expect(tds[2].textContent).toBe('text');
		});
	});
});

describe('CortexChat — proof toggle', () => {
	it('shows proof drawer on toggle click', async () => {
		mockFetchAsk.mockResolvedValueOnce({
			answer: 'Summary.',
			interpretation: 'Query restatement.',
			sql: 'SELECT 42',
			error: null,
			results: [{ X: 42 }],
			suggestions: [],
		});

		const { container } = render(CortexChat, { props: PROPS });
		const input = container.querySelector('input[name="question"]');
		const form = container.querySelector('form');
		await fireEvent.input(input, { target: { value: 'test' } });
		await fireEvent.submit(form);

		await vi.waitFor(() => {
			expect(container.querySelector('.proof-toggle')).toBeTruthy();
		});

		// Proof hidden by default
		expect(container.querySelector('.proof')).toBeNull();

		// Click toggle
		await fireEvent.click(container.querySelector('.proof-toggle'));
		expect(container.querySelector('.proof')).toBeTruthy();
		expect(container.querySelector('.sql-pre').textContent).toContain('SELECT 42');
		expect(container.querySelector('.interp').textContent).toContain('Query restatement');

		// Click again to hide
		await fireEvent.click(container.querySelector('.proof-toggle'));
		expect(container.querySelector('.proof')).toBeNull();
	});
});

describe('CortexChat — suggestion follow-ups', () => {
	it('renders follow-up suggestions when answer has no SQL', async () => {
		mockFetchAsk.mockResolvedValueOnce({
			answer: 'I cannot answer that.',
			interpretation: null,
			sql: null,
			error: null,
			results: null,
			suggestions: ['Try asking about mines', 'Try asking about plants'],
		});

		const { container } = render(CortexChat, { props: PROPS });
		const input = container.querySelector('input[name="question"]');
		const form = container.querySelector('form');
		await fireEvent.input(input, { target: { value: 'weather?' } });
		await fireEvent.submit(form);

		await vi.waitFor(() => {
			const followUps = container.querySelectorAll('.follow-ups .chip');
			expect(followUps).toHaveLength(2);
			expect(followUps[0].textContent).toContain('Try asking about mines');
		});
	});

	it('hides suggestion follow-ups when SQL is present', async () => {
		mockFetchAsk.mockResolvedValueOnce({
			answer: 'Summary.',
			interpretation: 'ok.',
			sql: 'SELECT 1',
			error: null,
			results: [{ X: 1 }],
			suggestions: ['Follow up?'],
		});

		const { container } = render(CortexChat, { props: PROPS });
		const input = container.querySelector('input[name="question"]');
		const form = container.querySelector('form');
		await fireEvent.input(input, { target: { value: 'test' } });
		await fireEvent.submit(form);

		await vi.waitFor(() => {
			// With SQL present, suggestions are cleared
			expect(container.querySelector('.follow-ups')).toBeNull();
		});
	});
});

describe('CortexChat — no-SQL hint', () => {
	it('shows interpretation hint when no SQL is generated', async () => {
		mockFetchAsk.mockResolvedValueOnce({
			answer: 'I cannot find that in the data.',
			interpretation: null,
			sql: null,
			error: null,
			results: null,
			suggestions: [],
		});

		const { container } = render(CortexChat, { props: PROPS });
		const input = container.querySelector('input[name="question"]');
		const form = container.querySelector('form');
		await fireEvent.input(input, { target: { value: 'weather?' } });
		await fireEvent.submit(form);

		await vi.waitFor(() => {
			expect(container.querySelector('.hint')).toBeTruthy();
			expect(container.querySelector('.hint').textContent).toContain('interpretation layer');
		});
	});
});

describe('CortexChat — chip click', () => {
	beforeEach(() => {
		mockFetchAsk.mockReset();
	});
	afterEach(cleanup);

	it('triggers a question from clicking a chip', async () => {
		mockFetchAsk.mockResolvedValue({
			answer: '42 tons.',
			interpretation: null,
			sql: null,
			error: null,
			results: null,
			suggestions: [],
		});

		const { container } = render(CortexChat, { props: PROPS });
		const callsBefore = mockFetchAsk.mock.calls.length;
		const chip = container.querySelector('.chip');
		await fireEvent.click(chip);

		// At least one new call after the click
		expect(mockFetchAsk.mock.calls.length).toBeGreaterThan(callsBefore);
		// The most recent call should reference the chip content
		const lastCall = mockFetchAsk.mock.calls[mockFetchAsk.mock.calls.length - 1];
		expect(lastCall[0]).toContain('Bailey Mine');
	});
});
