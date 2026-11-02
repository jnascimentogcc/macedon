import { Component, computed, input } from '@angular/core';
import { HlmBadgeImports } from '@spartan-ng/helm/badge';
import { VersionStatus } from '../core/api';
import { MessageKey, TranslatePipe } from '../core/i18n';

const TONES: Record<VersionStatus, string> = {
  processing: 'bg-[var(--info-bg)] text-[var(--info)] border-[var(--info-border)]',
  active: 'bg-[var(--success-bg)] text-[var(--success)] border-[var(--success-border)]',
  archived: 'bg-muted text-muted-foreground border-border',
  failed: 'bg-[var(--danger-bg)] text-[var(--danger)] border-[var(--danger-border)]',
};

/** Version status as text plus color, never color alone. */
@Component({
  selector: 'app-status-badge',
  imports: [HlmBadgeImports, TranslatePipe],
  template: `<span hlmBadge variant="outline" [class]="tone()">{{
    label() | t
  }}</span>`,
})
export class StatusBadgeComponent {
  readonly status = input.required<VersionStatus>();
  protected readonly label = computed((): MessageKey => `status.${this.status()}`);
  protected readonly tone = computed(() => TONES[this.status()]);
}
