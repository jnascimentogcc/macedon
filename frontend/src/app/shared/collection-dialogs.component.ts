import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmInputImports } from '@spartan-ng/helm/input';
import { HlmLabelImports } from '@spartan-ng/helm/label';
import { Collection, CollectionsApi } from '../core/api';
import { MessageKey, TranslatePipe } from '../core/i18n';
import { ModalComponent } from './modal.component';

/** Creates a collection (under `parent`, or at the top) or renames `collection`. */
@Component({
  selector: 'app-collection-name-dialog',
  imports: [FormsModule, ModalComponent, TranslatePipe, HlmButtonImports, HlmInputImports, HlmLabelImports],
  template: `
    <app-modal
      [heading]="(collection() ? 'collections.renameTitle' : 'collections.createTitle') | t"
      (closed)="closed.emit()"
    >
      <form (ngSubmit)="save()" class="flex flex-col gap-4" novalidate>
        <div class="flex flex-col gap-1.5">
          <label hlmLabel for="collection-name">
            {{ 'collections.name' | t }} <span class="text-muted-foreground">{{ 'common.required' | t }}</span>
          </label>
          <input
            id="collection-name"
            hlmInput
            name="name"
            maxlength="120"
            autocomplete="off"
            aria-describedby="collection-error"
            [attr.aria-invalid]="error() ? 'true' : null"
            [(ngModel)]="name"
          />
          <p id="collection-error" class="text-destructive text-sm" role="alert">
            @if (error(); as key) {
              {{ key | t }}
            }
          </p>
        </div>
        <div class="flex justify-end gap-2">
          <button hlmBtn variant="ghost" type="button" (click)="closed.emit()">
            {{ 'common.cancel' | t }}
          </button>
          <button hlmBtn type="submit" [disabled]="busy()">{{ 'collections.save' | t }}</button>
        </div>
      </form>
    </app-modal>
  `,
})
export class CollectionNameDialogComponent implements OnInit {
  readonly parent = input<Collection | null>(null);
  readonly collection = input<Collection | null>(null);
  readonly done = output<void>();
  readonly closed = output<void>();

  protected name = '';
  protected readonly busy = signal(false);
  protected readonly error = signal<MessageKey | null>(null);
  private readonly api = inject(CollectionsApi);

  ngOnInit(): void {
    this.name = this.collection()?.name ?? '';
  }

  protected save(): void {
    const name = this.name.trim();
    if (!name) {
      this.error.set('collections.nameRequired');
      return;
    }
    const existing = this.collection();
    const request = existing
      ? this.api.rename(existing.id, name)
      : this.api.create(name, this.parent()?.id ?? null);
    this.busy.set(true);
    this.error.set(null);
    request.subscribe({
      next: () => this.done.emit(),
      error: (failure: unknown) => {
        this.busy.set(false);
        this.error.set(this.messageFor(failure));
      },
    });
  }

  private messageFor(failure: unknown): MessageKey {
    if (failure instanceof HttpErrorResponse) {
      if (failure.status === 409) return 'collections.duplicate';
      if (failure.status === 422) return 'collections.tooDeep';
      if (failure.status === 403) return 'collections.adminOnly';
      if (failure.status === 0) return 'common.offline';
    }
    return 'common.unknownError';
  }
}

/** Confirms and performs the deletion of an empty collection. */
@Component({
  selector: 'app-collection-delete-dialog',
  imports: [ModalComponent, TranslatePipe, HlmButtonImports],
  template: `
    <app-modal [heading]="'collections.deleteTitle' | t" (closed)="closed.emit()">
      <p class="mb-2">{{ 'collections.deleteBody' | t: { name: collection().name } }}</p>
      <p class="text-destructive mb-4 text-sm" role="alert">
        @if (error(); as key) {
          {{ key | t }}
        }
      </p>
      <div class="flex justify-end gap-2">
        <button hlmBtn variant="ghost" type="button" (click)="closed.emit()">
          {{ 'common.cancel' | t }}
        </button>
        <button hlmBtn variant="destructive" type="button" [disabled]="busy()" (click)="confirm()">
          {{ 'collections.delete' | t }}
        </button>
      </div>
    </app-modal>
  `,
})
export class CollectionDeleteDialogComponent {
  readonly collection = input.required<Collection>();
  readonly done = output<void>();
  readonly closed = output<void>();

  protected readonly busy = signal(false);
  protected readonly error = signal<MessageKey | null>(null);
  private readonly api = inject(CollectionsApi);

  protected confirm(): void {
    this.busy.set(true);
    this.api.remove(this.collection().id).subscribe({
      next: () => this.done.emit(),
      error: (failure: unknown) => {
        this.busy.set(false);
        this.error.set(
          failure instanceof HttpErrorResponse && failure.status === 409
            ? 'collections.notEmpty'
            : 'common.unknownError',
        );
      },
    });
  }
}
