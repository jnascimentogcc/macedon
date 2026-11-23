import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { HlmBadgeImports } from '@spartan-ng/helm/badge';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmTableImports } from '@spartan-ng/helm/table';
import { ApiKey, ApiKeyCreated, ApiKeysApi, errorKey } from '../core/api';
import { CollectionsStore } from '../core/collections.store';
import { I18n, MessageKey, TranslatePipe } from '../core/i18n';
import {
  ApiKeyCreateDialogComponent,
  ApiKeyRevokeDialogComponent,
  ApiKeySecretDialogComponent,
} from './api-key-dialogs.component';
import { KeyStatus, keyStatus } from './key-status';

const TONES: Record<KeyStatus, string> = {
  active: 'bg-[var(--success-bg)] text-[var(--success)] border-[var(--success-border)]',
  expired: 'bg-muted text-muted-foreground border-border',
  revoked: 'bg-[var(--danger-bg)] text-[var(--danger)] border-[var(--danger-border)]',
};

@Component({
  selector: 'app-api-keys-page',
  imports: [
    DatePipe,
    TranslatePipe,
    HlmBadgeImports,
    HlmButtonImports,
    HlmTableImports,
    ApiKeyCreateDialogComponent,
    ApiKeyRevokeDialogComponent,
    ApiKeySecretDialogComponent,
  ],
  template: `
    <header class="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold">{{ 'keys.title' | t }}</h1>
        <p class="text-muted-foreground max-w-prose">{{ 'keys.description' | t }}</p>
      </div>
      @if (store.isAdmin()) {
        <button hlmBtn type="button" (click)="creating.set(true)">{{ 'keys.create' | t }}</button>
      }
    </header>

    <p class="sr-only" role="status" aria-live="polite">
      {{ loading() ? ('common.loading' | t) : '' }}
    </p>

    @if (!store.loaded()) {
      <p class="text-muted-foreground">{{ 'common.loading' | t }}</p>
    } @else if (!store.isAdmin()) {
      <div class="bg-card rounded-lg border p-8 text-center" role="alert">
        <p>{{ 'keys.adminOnly' | t }}</p>
      </div>
    } @else if (error(); as key) {
      <div class="border-[var(--danger-border)] bg-[var(--danger-bg)] rounded-lg border p-4" role="alert">
        <p>{{ key | t }}</p>
        <button hlmBtn variant="outline" size="sm" class="mt-3" type="button" (click)="load()">
          {{ 'common.retry' | t }}
        </button>
      </div>
    } @else if (keys(); as list) {
      @if (list.length === 0) {
        <div class="bg-card rounded-lg border p-8 text-center">
          <h2 class="text-lg font-bold">{{ 'keys.empty.title' | t }}</h2>
          <p class="text-muted-foreground mt-1">{{ 'keys.empty.body' | t }}</p>
          <button hlmBtn class="mt-4" type="button" (click)="creating.set(true)">
            {{ 'keys.create' | t }}
          </button>
        </div>
      } @else {
        <div class="bg-card overflow-x-auto rounded-lg border">
          <table hlmTable>
            <caption class="sr-only">{{ 'keys.table' | t }}</caption>
            <thead hlmTHead>
              <tr hlmTr>
                <th hlmTh scope="col">{{ 'keys.col.name' | t }}</th>
                <th hlmTh scope="col">{{ 'keys.col.key' | t }}</th>
                <th hlmTh scope="col">{{ 'keys.col.groups' | t }}</th>
                <th hlmTh scope="col">{{ 'keys.col.scopes' | t }}</th>
                <th hlmTh scope="col">{{ 'keys.col.expires' | t }}</th>
                <th hlmTh scope="col">{{ 'keys.col.lastUsed' | t }}</th>
                <th hlmTh scope="col">{{ 'keys.col.status' | t }}</th>
                <th hlmTh scope="col"><span class="sr-only">{{ 'keys.col.actions' | t }}</span></th>
              </tr>
            </thead>
            <tbody hlmTBody>
              @for (key of list; track key.id) {
                <tr hlmTr>
                  <td hlmTd class="font-medium">{{ key.name }}</td>
                  <td hlmTd class="font-mono text-sm">{{ key.prefix }}…</td>
                  <td hlmTd class="text-sm">
                    {{ key.groups.length ? key.groups.join(', ') : ('keys.noGroups' | t) }}
                  </td>
                  <td hlmTd class="text-sm">{{ scopeText(key) }}</td>
                  <td hlmTd class="font-mono">{{ key.expires_at | date: 'mediumDate' }}</td>
                  <td hlmTd class="font-mono">
                    @if (key.last_used_at) {
                      {{ key.last_used_at | date: 'medium' }}
                    } @else {
                      <span class="text-muted-foreground font-sans">{{ 'keys.neverUsed' | t }}</span>
                    }
                  </td>
                  <td hlmTd>
                    <span hlmBadge variant="outline" [class]="tone(key)">{{ statusKey(key) | t }}</span>
                  </td>
                  <td hlmTd>
                    @if (status(key) === 'active') {
                      <button
                        hlmBtn
                        variant="outline"
                        size="sm"
                        type="button"
                        [attr.aria-label]="'keys.revokeLabel' | t: { name: key.name }"
                        (click)="revoking.set(key)"
                      >
                        {{ 'keys.revoke' | t }}
                      </button>
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    }

    @if (creating()) {
      <app-api-key-create-dialog (closed)="creating.set(false)" (created)="created($event)" />
    }
    @if (secret(); as key) {
      <app-api-key-secret-dialog [key]="key" (closed)="secret.set(null)" />
    }
    @if (revoking(); as key) {
      <app-api-key-revoke-dialog [key]="key" (closed)="revoking.set(null)" (done)="revoked()" />
    }
  `,
})
export class ApiKeysPageComponent implements OnInit {
  protected readonly keys = signal<ApiKey[] | null>(null);
  protected readonly loading = signal(false);
  protected readonly error = signal<MessageKey | null>(null);
  protected readonly creating = signal(false);
  protected readonly secret = signal<ApiKeyCreated | null>(null);
  protected readonly revoking = signal<ApiKey | null>(null);
  protected readonly store = inject(CollectionsStore);
  private readonly api = inject(ApiKeysApi);
  private readonly i18n = inject(I18n);

  ngOnInit(): void {
    this.store.load(); // tells whether the caller is an administrator
    this.load();
  }

  protected load(): void {
    this.loading.set(true);
    this.api.list().subscribe({
      next: (keys) => {
        this.keys.set(keys);
        this.error.set(null);
        this.loading.set(false);
      },
      error: (failure: unknown) => {
        this.loading.set(false);
        // A 403 means the caller is not an administrator; the page already says so.
        this.error.set(errorKey(failure, 'keys.error.load'));
      },
    });
  }

  protected created(key: ApiKeyCreated): void {
    this.creating.set(false);
    this.secret.set(key);
    this.load();
  }

  protected revoked(): void {
    this.revoking.set(null);
    this.load();
  }

  protected status(key: ApiKey): KeyStatus {
    return keyStatus(key);
  }

  protected statusKey(key: ApiKey): MessageKey {
    return `keys.status.${keyStatus(key)}`;
  }

  protected tone(key: ApiKey): string {
    return TONES[keyStatus(key)];
  }

  protected scopeText(key: ApiKey): string {
    return key.scopes.map((s) => this.i18n.t(`keys.scope.${s}`)).join(', ');
  }
}
