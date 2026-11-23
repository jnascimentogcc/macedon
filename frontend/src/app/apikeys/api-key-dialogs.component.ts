import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmInputImports } from '@spartan-ng/helm/input';
import { HlmLabelImports } from '@spartan-ng/helm/label';
import { ApiKey, ApiKeyCreated, ApiKeyScope, ApiKeysApi, GroupsApi } from '../core/api';
import { I18n, MessageKey, TranslatePipe } from '../core/i18n';
import { GroupPickerComponent } from '../shared/group-picker.component';
import { ModalComponent } from '../shared/modal.component';

export const DEFAULT_DAYS = 90;
export const MAX_DAYS = 365;

/** Creates a key. The secret comes back once, in `created`. */
@Component({
  selector: 'app-api-key-create-dialog',
  imports: [
    FormsModule,
    GroupPickerComponent,
    ModalComponent,
    TranslatePipe,
    HlmButtonImports,
    HlmInputImports,
    HlmLabelImports,
  ],
  template: `
    <app-modal [heading]="'keys.createTitle' | t" (closed)="closed.emit()">
      <form (ngSubmit)="submit()" class="flex flex-col gap-4" novalidate>
        <div class="flex flex-col gap-1.5">
          <label hlmLabel for="key-name">
            {{ 'keys.name' | t }} <span class="text-muted-foreground">{{ 'common.required' | t }}</span>
          </label>
          <input
            id="key-name"
            hlmInput
            name="name"
            maxlength="120"
            autocomplete="off"
            aria-describedby="key-name-help key-error"
            [(ngModel)]="name"
          />
          <p id="key-name-help" class="text-muted-foreground text-xs">{{ 'keys.nameHelp' | t }}</p>
        </div>

        <app-group-picker
          idPrefix="key-groups"
          legend="keys.groupsLabel"
          help="keys.groupsHelp"
          [options]="groupOptions()"
          [(value)]="selectedGroups"
        />

        <fieldset class="flex flex-col gap-1.5" aria-describedby="key-scopes-help">
          <legend class="text-sm leading-none font-medium">
            {{ 'keys.scopes' | t }} <span class="text-muted-foreground">{{ 'common.required' | t }}</span>
          </legend>
          <div class="flex flex-wrap gap-x-4 gap-y-1.5 pt-1.5">
            @for (scope of scopeChoices; track scope) {
              <label class="flex min-h-[44px] items-center gap-2 text-sm sm:min-h-[24px]">
                <input
                  type="checkbox"
                  class="size-4"
                  [checked]="scopes().includes(scope)"
                  (change)="toggleScope(scope)"
                />
                {{ scopeLabels[scope] | t }}
              </label>
            }
          </div>
          <p id="key-scopes-help" class="text-muted-foreground text-xs">{{ 'keys.scopesHelp' | t }}</p>
        </fieldset>

        <div class="flex flex-col gap-1.5">
          <label hlmLabel for="key-days">
            {{ 'keys.expires' | t }} <span class="text-muted-foreground">{{ 'common.required' | t }}</span>
          </label>
          <input
            id="key-days"
            hlmInput
            type="number"
            name="days"
            inputmode="numeric"
            min="1"
            [attr.max]="maxDays"
            aria-describedby="key-days-help"
            [(ngModel)]="days"
          />
          <p id="key-days-help" class="text-muted-foreground text-xs">{{ 'keys.expiresHelp' | t }}</p>
        </div>

        <p id="key-error" class="text-destructive text-sm" role="alert">
          @if (error(); as key) {
            {{ key | t }}
          }
        </p>

        <div class="flex justify-end gap-2">
          <button hlmBtn variant="ghost" type="button" (click)="closed.emit()">
            {{ 'common.cancel' | t }}
          </button>
          <button hlmBtn type="submit" [disabled]="busy()">
            {{ (busy() ? 'keys.submitting' : 'keys.submit') | t }}
          </button>
        </div>
      </form>
    </app-modal>
  `,
})
export class ApiKeyCreateDialogComponent implements OnInit {
  readonly created = output<ApiKeyCreated>();
  readonly closed = output<void>();

  protected readonly scopeChoices: ApiKeyScope[] = ['read', 'write'];
  protected readonly scopeLabels: Record<ApiKeyScope, MessageKey> = {
    read: 'keys.scope.read',
    write: 'keys.scope.write',
  };
  protected readonly maxDays = MAX_DAYS;
  protected name = '';
  protected days: number | null = DEFAULT_DAYS;
  protected readonly scopes = signal<ApiKeyScope[]>(['read']);
  protected readonly groupOptions = signal<string[]>([]);
  protected readonly selectedGroups = signal<string[]>([]);
  protected readonly busy = signal(false);
  protected readonly error = signal<MessageKey | null>(null);
  private readonly api = inject(ApiKeysApi);
  private readonly groupsApi = inject(GroupsApi);

  ngOnInit(): void {
    this.groupsApi.list().subscribe({
      next: (groups) => this.groupOptions.set(groups),
      error: () => undefined, // a key without groups is still valid
    });
  }

  protected toggleScope(scope: ApiKeyScope): void {
    this.scopes.update((current) =>
      current.includes(scope) ? current.filter((s) => s !== scope) : [...current, scope],
    );
  }

  protected submit(): void {
    const name = this.name.trim();
    const days = Number(this.days);
    if (!name) {
      this.error.set('keys.nameRequired');
      return;
    }
    if (this.scopes().length === 0) {
      this.error.set('keys.scopeRequired');
      return;
    }
    if (!Number.isInteger(days) || days < 1 || days > MAX_DAYS) {
      this.error.set('keys.expiresInvalid');
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    this.api
      .create({
        name,
        groups: this.selectedGroups(),
        scopes: this.scopes(),
        expires_in_days: days,
      })
      .subscribe({
        next: (key) => this.created.emit(key),
        error: (failure: unknown) => {
          this.busy.set(false);
          this.error.set(this.messageFor(failure));
        },
      });
  }

  private messageFor(failure: unknown): MessageKey {
    if (failure instanceof HttpErrorResponse) {
      if (failure.status === 0) return 'common.offline';
      if (failure.status === 403) return 'keys.adminOnly';
      if (failure.status === 422) return 'keys.invalid';
    }
    return 'common.unknownError';
  }
}

/** Shows the secret of a new key, once, with a way to copy it. */
@Component({
  selector: 'app-api-key-secret-dialog',
  imports: [ModalComponent, TranslatePipe, HlmButtonImports, HlmLabelImports],
  template: `
    <app-modal [heading]="'keys.createdTitle' | t" (closed)="closed.emit()">
      <p class="mb-4">{{ 'keys.createdWarning' | t }}</p>
      <label hlmLabel for="key-secret">{{ 'keys.token' | t }}</label>
      <div class="mt-1.5 flex flex-wrap items-center gap-2">
        <input
          id="key-secret"
          readonly
          class="border-input bg-muted min-w-0 flex-1 rounded-md border px-3 py-2 font-mono text-sm"
          [value]="key().token"
          (focus)="select($event)"
        />
        <button hlmBtn variant="secondary" type="button" (click)="copy()">
          {{ 'keys.copy' | t }}
        </button>
      </div>
      <p class="text-muted-foreground mt-1.5 text-xs">{{ 'keys.usage' | t }}</p>
      <p class="mt-2 text-sm" role="status" aria-live="polite">{{ feedback() }}</p>
      <div class="mt-4 flex justify-end">
        <button hlmBtn type="button" (click)="closed.emit()">{{ 'keys.done' | t }}</button>
      </div>
    </app-modal>
  `,
})
export class ApiKeySecretDialogComponent {
  readonly key = input.required<ApiKeyCreated>();
  readonly closed = output<void>();
  protected readonly feedback = signal('');
  private readonly i18n = inject(I18n);

  protected select(event: Event): void {
    (event.target as HTMLInputElement).select();
  }

  protected async copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(this.key().token);
      this.feedback.set(this.i18n.t('keys.copied'));
    } catch {
      this.feedback.set(this.i18n.t('keys.copyFailed'));
    }
  }
}

/** Confirms and performs the revocation of a key. */
@Component({
  selector: 'app-api-key-revoke-dialog',
  imports: [ModalComponent, TranslatePipe, HlmButtonImports],
  template: `
    <app-modal [heading]="'keys.revokeTitle' | t" (closed)="closed.emit()">
      <p class="mb-2">{{ 'keys.revokeBody' | t: { name: key().name } }}</p>
      <p class="text-destructive mb-4 text-sm" role="alert">
        @if (error(); as message) {
          {{ message | t }}
        }
      </p>
      <div class="flex justify-end gap-2">
        <button hlmBtn variant="ghost" type="button" (click)="closed.emit()">
          {{ 'common.cancel' | t }}
        </button>
        <button hlmBtn variant="destructive" type="button" [disabled]="busy()" (click)="confirm()">
          {{ 'keys.revoke' | t }}
        </button>
      </div>
    </app-modal>
  `,
})
export class ApiKeyRevokeDialogComponent {
  readonly key = input.required<ApiKey>();
  readonly done = output<void>();
  readonly closed = output<void>();

  protected readonly busy = signal(false);
  protected readonly error = signal<MessageKey | null>(null);
  private readonly api = inject(ApiKeysApi);

  protected confirm(): void {
    this.busy.set(true);
    this.api.revoke(this.key().id).subscribe({
      next: () => this.done.emit(),
      error: (failure: unknown) => {
        this.busy.set(false);
        this.error.set(
          failure instanceof HttpErrorResponse && failure.status === 0
            ? 'common.offline'
            : 'common.unknownError',
        );
      },
    });
  }
}
