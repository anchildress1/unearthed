import { render } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import SectionRailHarness from './SectionRailHarness.test.svelte';

describe('SectionRail', () => {
	it('renders the number and label chrome', () => {
		const { container } = render(SectionRailHarness, {
			props: { number: '02', label: 'Your coal', body: 'payload' },
		});
		expect(container.querySelector('.rail-num')?.textContent).toBe('N° 02');
		expect(container.querySelector('.rail-label')?.textContent).toBe('Your coal');
	});

	it('marks the decorative chrome aria-hidden', () => {
		const { container } = render(SectionRailHarness, {
			props: { number: '01', label: 'Hero', body: 'payload' },
		});
		const chrome = container.querySelector('.rail-chrome');
		expect(chrome).toBeTruthy();
		expect(chrome.getAttribute('aria-hidden')).toBe('true');
	});

	it('applies class override to the section wrapper', () => {
		const { container } = render(SectionRailHarness, {
			props: { number: '03', label: 'Map', className: 'map-spotlight', body: 'payload' },
		});
		const section = container.querySelector('section.section-rail');
		expect(section.classList.contains('map-spotlight')).toBe(true);
	});

	it('renders child content through the snippet slot', () => {
		const { getByText } = render(SectionRailHarness, {
			props: { number: '04', label: 'Ticker', body: 'the body content' },
		});
		expect(getByText('the body content')).toBeInTheDocument();
	});
});
