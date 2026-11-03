import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmInputImports } from '@spartan-ng/helm/input';
import { HlmLabelImports } from '@spartan-ng/helm/label';
import { DocumentsApi, GroupsApi, UploadResult } from '../core/api';
import { CollectionsStore, parseTags } from '../core/collections.store';
import { MessageKey, TranslatePipe } from '../core/i18n';
import { ModalComponent } from '../shared/modal.component';

/** Uploads a new document, or a new version when `documentId` is set. */
@Component({
  selector: 'app-upload-dialog',
  imports: [
    FormsModule,
    ModalComponent,
    TranslatePipe,
    HlmButtonImports,
    HlmInputImports,
    HlmLabelImports,
  ],
  template: `
    <app-modal
      [heading]="(documentId() ? 'upload.newVersionTitle' : 'upload.title') | t"
      (closed)="closed.emit()"
    >
      <form (ngSubmit)="submit()" class="flex flex-col gap-4" novalidate>
        <div class="flex flex-col gap-1.5">
          <label hlmLabel for="upload-file">
            {{ 'upload.file' | t }} <span class="text-muted-foreground">{{ 'common.required' | t }}</span>
          </label>
          <input
            id="upload-file"
            hlmInput
            type="file"
            accept=".pdf,.docx,.txt"
            aria-describedby="upload-file-help upload-error"
            [attr.aria-invalid]="error() ? 'true' : null"
            (change)="pick($event)"
          />
          <p id="upload-file-help" class="text-muted-foreground text-xs">
            {{ 'upload.fileHelp' | t }}
          </p>
        </div>

        @if (!documentId()) {
          <div class="flex flex-col gap-1.5">
            <label hlmLabel for="upload-name">
              {{ 'upload.name' | t }} <span class="text-muted-foreground">{{ 'common.optional' | t }}</span>
            </label>
            <input
              id="upload-name"
              hlmInput
              name="name"
              autocomplete="off"
              aria-describedby="upload-name-help"
              [(ngModel)]="name"
            />
            <p id="upload-name-help" class="text-muted-foreground text-xs">
              {{ 'upload.nameHelp' | t }}
            </p>
          </div>
          <div class="flex flex-col gap-1.5">
            <label hlmLabel for="upload-collection">
              {{ 'collections.one' | t }} <span class="text-muted-foreground">{{ 'common.optional' | t }}</span>
            </label>
            <select
              id="upload-collection"
              name="collection"
              class="border-input bg-background focus-visible:ring-ring/50 focus-visible:border-ring h-9 w-full rounded-md border px-2 text-sm outline-none focus-visible:ring-3"
              [(ngModel)]="collectionId"
            >
              <option [ngValue]="null">{{ 'collections.none' | t }}</option>
              @for (node of store.ordered(); track node.collection.id) {
                <option [ngValue]="node.collection.id">
                  {{ '  '.repeat(node.collection.depth - 1) + node.collection.name }}
                </option>
              }
            </select>
          </div>
          <div class="flex flex-col gap-1.5">
            <label hlmLabel for="upload-tags">
              {{ 'tags.label' | t }} <span class="text-muted-foreground">{{ 'common.optional' | t }}</span>
            </label>
            <input
              id="upload-tags"
              hlmInput
              name="tags"
              autocomplete="off"
              aria-describedby="upload-tags-help"
              [(ngModel)]="tags"
            />
            <p id="upload-tags-help" class="text-muted-foreground text-xs">{{ 'tags.help' | t }}</p>
          </div>
          <fieldset class="flex flex-col gap-1.5" aria-describedby="upload-groups-help">
            <legend class="text-sm leading-none font-medium">
              {{ 'upload.groups' | t }} <span class="text-muted-foreground">{{ 'common.optional' | t }}</span>
            </legend>
            @if (groupOptions().length) {
              <div class="flex flex-wrap gap-x-4 gap-y-1.5 pt-1.5">
                @for (group of groupOptions(); track group) {
                  <label class="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      class="size-4"
                      [checked]="selectedGroups().has(group)"
                      (change)="toggleGroup(group)"
                    />
                    {{ group }}
                  </label>
                }
              </div>
            } @else {
              <p class="text-muted-foreground pt-1.5 text-sm">{{ 'upload.groupsNone' | t }}</p>
            }
            <p id="upload-groups-help" class="text-muted-foreground text-xs">
              {{ 'upload.groupsHelp' | t }}
            </p>
          </fieldset>
        }

        <p id="upload-error" class="text-destructive text-sm" role="alert">
          @if (error(); as key) {
            {{ key | t }}
          }
        </p>

        <div class="flex justify-end gap-2">
          <button hlmBtn variant="ghost" type="button" (click)="closed.emit()">
            {{ 'common.cancel' | t }}
          </button>
          <button hlmBtn type="submit" [disabled]="busy()">
            {{ (busy() ? 'upload.submitting' : 'upload.submit') | t }}
          </button>
        </div>
      </form>
    </app-modal>
  `,
})
export class UploadDialogComponent implements OnInit {
  readonly documentId = input<string | null>(null);
  readonly defaultCollectionId = input<string | null>(null);
  readonly done = output<UploadResult>();
  readonly closed = output<void>();

  protected name = '';
  protected tags = '';
  protected collectionId: string | null = null;
  protected readonly store = inject(CollectionsStore);
  protected readonly groupOptions = signal<string[]>([]);
  protected readonly selectedGroups = signal<ReadonlySet<string>>(new Set());
  protected readonly busy = signal(false);
  protected readonly error = signal<MessageKey | null>(null);
  private file: File | null = null;
  private readonly api = inject(DocumentsApi);
  private readonly groupsApi = inject(GroupsApi);

  ngOnInit(): void {
    this.collectionId = this.defaultCollectionId();
    if (!this.documentId()) {
      this.groupsApi.list().subscribe({
        next: (groups) => this.groupOptions.set(groups),
        error: () => undefined, // sharing is optional; the upload still works privately
      });
    }
  }

  protected toggleGroup(group: string): void {
    this.selectedGroups.update((current) => {
      const next = new Set(current);
      if (!next.delete(group)) {
        next.add(group);
      }
      return next;
    });
  }

  protected pick(event: Event): void {
    this.file = (event.target as HTMLInputElement).files?.item(0) ?? null;
    this.error.set(null);
  }

  protected submit(): void {
    if (!this.file) {
      this.error.set('upload.fileRequired');
      return;
    }
    const id = this.documentId();
    const request = id
      ? this.api.uploadVersion(id, this.file)
      : this.api.upload({
          file: this.file,
          name: this.name.trim() || undefined,
          tags: parseTags(this.tags),
          collectionId: this.collectionId,
          groups: [...this.selectedGroups()],
        });
    this.busy.set(true);
    this.error.set(null);
    request.subscribe({
      next: (result) => this.done.emit(result),
      error: (failure: unknown) => {
        this.busy.set(false);
        this.error.set(this.messageFor(failure));
      },
    });
  }

  private messageFor(failure: unknown): MessageKey {
    if (failure instanceof HttpErrorResponse) {
      switch (failure.status) {
        case 0:
          return 'common.offline';
        case 403:
          return 'common.ownerOnly';
        case 413:
          return 'upload.tooLarge';
        case 415:
          return 'upload.unsupported';
        case 422:
          return this.documentId() ? 'upload.unsupported' : 'tags.invalid';
      }
    }
    return 'common.unknownError';
  }
}
