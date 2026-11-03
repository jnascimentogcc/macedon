import { TestBed } from '@angular/core/testing';
import { StatusBadgeComponent } from './status-badge.component';

describe('StatusBadgeComponent', () => {
  it.each([
    ['processing', 'Processing'],
    ['active', 'Active'],
    ['archived', 'Archived'],
    ['failed', 'Failed'],
  ] as const)('shows the %s status as text, not only as color', async (status, label) => {
    const fixture = TestBed.createComponent(StatusBadgeComponent);
    fixture.componentRef.setInput('status', status);
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent.trim()).toBe(label);
  });
});
