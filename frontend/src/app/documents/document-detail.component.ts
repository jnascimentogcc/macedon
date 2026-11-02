import { HttpErrorResponse } from '@angular/common/http';
import { DatePipe } from '@angular/common';
import { Component, DestroyRef, OnInit, computed, inject, input, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmTableImports } from '@spartan-ng/helm/table';
import { DocumentItem, DocumentVersion, DocumentsApi, UploadResult, errorKey } from '../core/api';
import { CollectionsStore } from '../core/collections.store';
import { I18n, MessageKey, TranslatePipe } from '../core/i18n';
import { EditDocumentDialogComponent } from './edit-document-dialog.component';
import { ModalComponent } from '../shared/modal.component';
import { StatusBadgeComponent } from '../shared/status-badge.component';
import { UploadDialogComponent } from './upload-dialog.component';

const POLL_MS = 3000;

@Component({
  selector: 'app-document-detail',
  imports: [
    DatePipe,
    RouterLink,
    TranslatePipe,
    HlmButtonImports,
    HlmTableImports,
    EditDocumentDialogComponent,
    ModalComponent,
    StatusBadgeComponent,
    UploadDialogComponent,
  ],
  template: `
    <a routerLink="/documents" class="text-muted-foreground text-sm underline-offset-4 hover:underline">
      ← {{ 'detail.back' | t }}
    </a>

    @if (error(); as key) {
      <div class="border-[var(--danger-border)] bg-[var(--danger-bg)] mt-4 rounded-lg border p-4" role="alert">
        <p>{{ key | t }}</p>
        <button hlmBtn variant="outline" size="sm" class="mt-3" type="button" (click)="load()">
          {{ 'common.retry' | t }}
        </button>
      </div>
    } @else if (document(); as doc) {
      <header class="mt-2 mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold break-words">{{ doc.name }}</h1>
          <p class="text-muted-foreground font-mono text-xs uppercase">{{ doc.doc_type }}</p>
        </div>
        @if (!doc.archived_at) {
          <div class="flex flex-wrap gap-2">
            <button hlmBtn variant="outline" type="button" (click)="editing.set(true)">
              {{ 'edit.action' | t }}
            </button>
            <button hlmBtn variant="secondary" type="button" (click)="uploading.set(true)">
              {{ 'detail.newVersion' | t }}
            </button>
            <button hlmBtn variant="destructive" type="button" (click)="confirming.set(true)">
              {{ 'detail.delete' | t }}
            </button>
          </div>
        }
      </header>

      <p class="sr-only" role="status" aria-live="polite">{{ notice() }}</p>
      @if (notice()) {
        <p class="bg-[var(--success-bg)] border-[var(--success-border)] mb-4 rounded-lg border p-3">
          {{ notice() }}
        </p>
      }
      @if (doc.archived_at) {
        <p class="bg-[var(--warning-bg)] border-[var(--warning-border)] mb-4 rounded-lg border p-3">
          {{ 'detail.archivedNotice' | t }}
        </p>
      }
      @if (processing()) {
        <p class="bg-[var(--info-bg)] border-[var(--info-border)] mb-4 rounded-lg border p-3">
          {{ 'detail.processingNotice' | t }}
        </p>
      }
      @if (actionError(); as key) {
        <p class="border-[var(--danger-border)] bg-[var(--danger-bg)] mb-4 rounded-lg border p-3" role="alert">
          {{ key | t }}
        </p>
      }

      <section class="bg-card mb-6 rounded-lg border p-4" aria-label="Metadata">
        <dl class="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          <div>
            <dt class="text-muted-foreground text-xs">{{ 'detail.id' | t }}</dt>
            <dd class="font-mono text-sm break-all">{{ doc.id }}</dd>
          </div>
          <div>
            <dt class="text-muted-foreground text-xs">{{ 'detail.owner' | t }}</dt>
            <dd class="font-mono text-sm break-all">{{ doc.owner_id }}</dd>
          </div>
          <div>
            <dt class="text-muted-foreground text-xs">{{ 'detail.groups' | t }}</dt>
            <dd class="text-sm">{{ doc.acl_groups.length ? doc.acl_groups.join(', ') : ('common.none' | t) }}</dd>
          </div>
          <div>
            <dt class="text-muted-foreground text-xs">{{ 'collections.one' | t }}</dt>
            <dd class="text-sm">{{ store.pathName(doc.collection_id) || ('collections.none' | t) }}</dd>
          </div>
          <div>
            <dt class="text-muted-foreground text-xs">{{ 'detail.tags' | t }}</dt>
            <dd class="text-sm">{{ doc.tags.length ? doc.tags.join(', ') : ('common.none' | t) }}</dd>
          </div>
          <div>
            <dt class="text-muted-foreground text-xs">{{ 'detail.created' | t }}</dt>
            <dd class="font-mono text-sm">{{ doc.created_at | date: 'medium' }}</dd>
          </div>
        </dl>
      </section>

      <section aria-labelledby="versions-title">
        <h2 id="versions-title" class="text-lg font-bold">{{ 'detail.versions' | t }}</h2>
        <p class="text-muted-foreground mb-3 text-sm">{{ 'detail.versionsDescription' | t }}</p>
        <div class="bg-card overflow-x-auto rounded-lg border">
          <table hlmTable>
            <caption class="sr-only">{{ 'detail.versions' | t }}</caption>
            <thead hlmTHead>
              <tr hlmTr>
                <th hlmTh scope="col">{{ 'detail.col.number' | t }}</th>
                <th hlmTh scope="col">{{ 'detail.col.status' | t }}</th>
                <th hlmTh scope="col">{{ 'detail.col.hash' | t }}</th>
                <th hlmTh scope="col">{{ 'detail.col.author' | t }}</th>
                <th hlmTh scope="col">{{ 'detail.col.created' | t }}</th>
                <th hlmTh scope="col">{{ 'detail.col.actions' | t }}</th>
              </tr>
            </thead>
            <tbody hlmTBody>
              @for (version of versions(); track version.id) {
                <tr hlmTr>
                  <td hlmTd class="font-mono">v{{ version.number }}</td>
                  <td hlmTd>
                    <app-status-badge [status]="version.status" />
                    @if (version.error) {
                      <p class="text-destructive mt-1 text-xs">
                        {{ 'detail.versionFailed' | t: { error: version.error } }}
                      </p>
                    }
                  </td>
                  <td hlmTd class="font-mono" [title]="version.file_hash">{{ version.file_hash.slice(0, 12) }}…</td>
                  <td hlmTd class="font-mono break-all">{{ version.author_id.slice(0, 8) }}</td>
                  <td hlmTd class="font-mono">{{ version.created_at | date: 'medium' }}</td>
                  <td hlmTd>
                    @if (version.status === 'archived' && !doc.archived_at) {
                      <button
                        hlmBtn
                        variant="outline"
                        size="sm"
                        type="button"
                        [attr.aria-label]="'detail.activateLabel' | t: { number: version.number }"
                        [disabled]="activating() !== null"
                        (click)="activate(version)"
                      >
                        {{ 'detail.activate' | t }}
                      </button>
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </section>

      @if (uploading()) {
        <app-upload-dialog [documentId]="doc.id" (closed)="uploading.set(false)" (done)="uploaded($event)" />
      }
      @if (editing()) {
        <app-edit-document-dialog
          [document]="doc"
          (closed)="editing.set(false)"
          (done)="edited($event)"
        />
      }
      @if (confirming()) {
        <app-modal [heading]="'detail.deleteTitle' | t" (closed)="confirming.set(false)">
          <p class="mb-6">{{ 'detail.deleteBody' | t: { name: doc.name } }}</p>
          <div class="flex justify-end gap-2">
            <button hlmBtn variant="ghost" type="button" (click)="confirming.set(false)">
              {{ 'common.cancel' | t }}
            </button>
            <button hlmBtn variant="destructive" type="button" (click)="archive()">
              {{ 'detail.deleteConfirm' | t }}
            </button>
          </div>
        </app-modal>
      }
    }
  `,
})
export class DocumentDetailComponent implements OnInit {
  readonly id = input.required<string>();

  protected readonly document = signal<DocumentItem | null>(null);
  protected readonly versions = signal<DocumentVersion[]>([]);
  protected readonly error = signal<MessageKey | null>(null);
  protected readonly actionError = signal<MessageKey | null>(null);
  protected readonly notice = signal('');
  protected readonly uploading = signal(false);
  protected readonly confirming = signal(false);
  protected readonly editing = signal(false);
  protected readonly store = inject(CollectionsStore);
  protected readonly activating = signal<number | null>(null);
  protected readonly processing = computed(() =>
    this.versions().some((version) => version.status === 'processing'),
  );

  private readonly api = inject(DocumentsApi);
  private readonly router = inject(Router);
  private readonly i18n = inject(I18n);
  private readonly destroyRef = inject(DestroyRef);

  ngOnInit(): void {
    this.store.load();
    this.load();
    const timer = setInterval(() => {
      if (this.processing()) {
        this.refresh(true);
      }
    }, POLL_MS);
    this.destroyRef.onDestroy(() => clearInterval(timer));
  }

  protected load(): void {
    this.refresh(false);
  }

  private refresh(quiet: boolean): void {
    this.api.get(this.id()).subscribe({
      next: (doc) => {
        this.document.set(doc);
        this.error.set(null);
      },
      error: (failure: unknown) => {
        if (!quiet) {
          this.error.set(errorKey(failure, 'detail.errorLoad'));
        }
      },
    });
    this.api.versions(this.id()).subscribe({
      next: (versions) => this.versions.set(versions),
      error: () => undefined,
    });
  }

  protected uploaded(result: UploadResult): void {
    this.uploading.set(false);
    this.notice.set(
      this.i18n.t(result.duplicate ? 'upload.duplicate' : 'upload.accepted'),
    );
    this.refresh(true);
  }

  protected edited(updated: DocumentItem): void {
    this.editing.set(false);
    this.document.set(updated);
    this.store.load();
  }

  protected activate(version: DocumentVersion): void {
    this.activating.set(version.number);
    this.actionError.set(null);
    this.api.activate(this.id(), version.number).subscribe({
      next: () => {
        this.activating.set(null);
        this.notice.set(this.i18n.t('detail.activated', { number: version.number }));
        this.refresh(true);
      },
      error: (failure: unknown) => {
        this.activating.set(null);
        this.actionError.set(this.writeError(failure, 'detail.activateFailed'));
      },
    });
  }

  protected archive(): void {
    this.confirming.set(false);
    this.api.archive(this.id()).subscribe({
      next: () => void this.router.navigate(['/documents']),
      error: (failure: unknown) => this.actionError.set(this.writeError(failure)),
    });
  }

  private writeError(failure: unknown, fallback: MessageKey = 'common.unknownError'): MessageKey {
    return failure instanceof HttpErrorResponse && failure.status === 403
      ? 'common.ownerOnly'
      : errorKey(failure, fallback);
  }
}
