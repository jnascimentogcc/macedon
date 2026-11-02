import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmInputImports } from '@spartan-ng/helm/input';
import { HlmLabelImports } from '@spartan-ng/helm/label';
import { DocumentsApi, UploadResult } from '../core/api';
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
            <label hlmLabel for="upload-groups">
              {{ 'upload.groups' | t }} <span class="text-muted-foreground">{{ 'common.optional' | t }}</span>
            </label>
            <input
              id="upload-groups"
              hlmInput
              name="groups"
              autocomplete="off"
              aria-describedby="upload-groups-help"
              [(ngModel)]="groups"
            />
            <p id="upload-groups-help" class="text-muted-foreground text-xs">
              {{ 'upload.groupsHelp' | t }}
            </p>
          </div>
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
export class UploadDialogComponent {
  readonly documentId = input<string | null>(null);
  readonly done = output<UploadResult>();
  readonly closed = output<void>();

  protected name = '';
  protected groups = '';
  protected readonly busy = signal(false);
  protected readonly error = signal<MessageKey | null>(null);
  private file: File | null = null;
  private readonly api = inject(DocumentsApi);

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
          groups: this.groups
            .split(',')
            .map((group) => group.trim())
            .filter(Boolean),
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
        case 422:
          return 'upload.unsupported';
      }
    }
    return 'common.unknownError';
  }
}
