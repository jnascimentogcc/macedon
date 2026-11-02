import { DatePipe } from '@angular/common';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmTableImports } from '@spartan-ng/helm/table';
import { DocumentPage, DocumentsApi, UploadResult, errorKey } from '../core/api';
import { I18n, MessageKey, TranslatePipe } from '../core/i18n';
import { StatusBadgeComponent } from '../shared/status-badge.component';
import { UploadDialogComponent } from './upload-dialog.component';

const PAGE_SIZE = 20;
const POLL_MS = 3000;

@Component({
  selector: 'app-documents-page',
  imports: [
    DatePipe,
    RouterLink,
    TranslatePipe,
    HlmButtonImports,
    HlmTableImports,
    StatusBadgeComponent,
    UploadDialogComponent,
  ],
  template: `
    <header class="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold">{{ 'documents.title' | t }}</h1>
        <p class="text-muted-foreground">{{ 'documents.description' | t }}</p>
      </div>
      <button hlmBtn type="button" (click)="uploading.set(true)">
        {{ 'documents.upload' | t }}
      </button>
    </header>

    <div class="mb-4 flex items-center gap-2">
      <input
        id="show-archived"
        type="checkbox"
        class="size-4"
        [checked]="includeArchived()"
        (change)="toggleArchived($event)"
      />
      <label for="show-archived">{{ 'documents.showArchived' | t }}</label>
    </div>

    <p class="sr-only" role="status" aria-live="polite">
      {{ loading() ? ('common.loading' | t) : '' }}
    </p>

    @if (error(); as key) {
      <div class="border-[var(--danger-border)] bg-[var(--danger-bg)] rounded-lg border p-4" role="alert">
        <p>{{ key | t }}</p>
        <button hlmBtn variant="outline" size="sm" class="mt-3" type="button" (click)="load()">
          {{ 'common.retry' | t }}
        </button>
      </div>
    } @else if (page(); as current) {
      @if (current.items.length === 0) {
        <div class="bg-card rounded-lg border p-8 text-center">
          <h2 class="text-lg font-bold">{{ 'documents.empty.title' | t }}</h2>
          <p class="text-muted-foreground mt-1">{{ 'documents.empty.body' | t }}</p>
          <button hlmBtn class="mt-4" type="button" (click)="uploading.set(true)">
            {{ 'documents.upload' | t }}
          </button>
        </div>
      } @else {
        <div class="bg-card overflow-x-auto rounded-lg border">
          <table hlmTable>
            <caption class="sr-only">{{ 'documents.table' | t }}</caption>
            <thead hlmTHead>
              <tr hlmTr>
                <th hlmTh scope="col">{{ 'documents.col.name' | t }}</th>
                <th hlmTh scope="col">{{ 'documents.col.type' | t }}</th>
                <th hlmTh scope="col">{{ 'documents.col.status' | t }}</th>
                <th hlmTh scope="col">{{ 'documents.col.active' | t }}</th>
                <th hlmTh scope="col">{{ 'documents.col.created' | t }}</th>
              </tr>
            </thead>
            <tbody hlmTBody>
              @for (doc of current.items; track doc.id) {
                <tr hlmTr>
                  <td hlmTd class="font-medium">
                    <a [routerLink]="['/documents', doc.id]" class="underline-offset-4 hover:underline">{{
                      doc.name
                    }}</a>
                    @if (doc.archived_at) {
                      <span class="text-muted-foreground ml-2 text-xs">{{ 'documents.archivedBadge' | t }}</span>
                    }
                  </td>
                  <td hlmTd class="font-mono uppercase">{{ doc.doc_type }}</td>
                  <td hlmTd>
                    @if (doc.latest_version; as version) {
                      <app-status-badge [status]="version.status" />
                    }
                  </td>
                  <td hlmTd class="font-mono">
                    @if (doc.active_version; as version) {
                      v{{ version.number }}
                    } @else {
                      <span class="text-muted-foreground font-sans">{{ 'documents.noneActive' | t }}</span>
                    }
                  </td>
                  <td hlmTd class="font-mono">{{ doc.created_at | date: 'medium' }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>

        <nav class="mt-4 flex flex-wrap items-center justify-between gap-2" [attr.aria-label]="'common.pagination' | t">
          <p class="text-muted-foreground font-mono text-xs">{{ range() }}</p>
          <div class="flex gap-2">
            <button hlmBtn variant="outline" size="sm" type="button" [disabled]="offset() === 0" (click)="go(-1)">
              {{ 'common.previous' | t }}
            </button>
            <button hlmBtn variant="outline" size="sm" type="button" [disabled]="!hasNext()" (click)="go(1)">
              {{ 'common.next' | t }}
            </button>
          </div>
        </nav>
      }
    }

    @if (uploading()) {
      <app-upload-dialog (closed)="uploading.set(false)" (done)="uploaded($event)" />
    }
  `,
})
export class DocumentsPageComponent implements OnInit {
  protected readonly page = signal<DocumentPage | null>(null);
  protected readonly loading = signal(false);
  protected readonly error = signal<MessageKey | null>(null);
  protected readonly offset = signal(0);
  protected readonly includeArchived = signal(false);
  protected readonly uploading = signal(false);
  protected readonly hasNext = computed(() => {
    const current = this.page();
    return current !== null && current.offset + current.items.length < current.total;
  });
  protected readonly range = computed(() => {
    const current = this.page();
    return current
      ? this.i18n.t('documents.range', {
          from: current.offset + 1,
          to: current.offset + current.items.length,
          total: current.total,
        })
      : '';
  });

  private readonly api = inject(DocumentsApi);
  private readonly i18n = inject(I18n);
  private readonly destroyRef = inject(DestroyRef);

  ngOnInit(): void {
    this.load();
    const timer = setInterval(() => {
      const processing = this.page()?.items.some((d) => d.latest_version?.status === 'processing');
      if (processing) {
        this.load(true);
      }
    }, POLL_MS);
    this.destroyRef.onDestroy(() => clearInterval(timer));
  }

  protected load(quiet = false): void {
    if (!quiet) {
      this.loading.set(true);
    }
    this.api.list(PAGE_SIZE, this.offset(), this.includeArchived()).subscribe({
      next: (result) => {
        this.page.set(result);
        this.error.set(null);
        this.loading.set(false);
      },
      error: (failure: unknown) => {
        this.loading.set(false);
        if (!quiet) {
          this.error.set(errorKey(failure, 'documents.error.load'));
        }
      },
    });
  }

  protected go(direction: 1 | -1): void {
    this.offset.update((value) => Math.max(0, value + direction * PAGE_SIZE));
    this.load();
  }

  protected toggleArchived(event: Event): void {
    this.includeArchived.set((event.target as HTMLInputElement).checked);
    this.offset.set(0);
    this.load();
  }

  protected uploaded(_result: UploadResult): void {
    this.uploading.set(false);
    this.offset.set(0);
    this.load();
  }

}
