import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmInputImports } from '@spartan-ng/helm/input';
import { HlmLabelImports } from '@spartan-ng/helm/label';
import { DocumentItem, DocumentsApi, GroupsApi } from '../core/api';
import { CollectionsStore, parseTags } from '../core/collections.store';
import { MessageKey, TranslatePipe } from '../core/i18n';
import { GroupPickerComponent } from '../shared/group-picker.component';
import { ModalComponent } from '../shared/modal.component';

/** Renames, retags, moves or re-shares a document. */
@Component({
  selector: 'app-edit-document-dialog',
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
    <app-modal [heading]="'edit.title' | t" (closed)="closed.emit()">
      <form (ngSubmit)="save()" class="flex flex-col gap-4" novalidate>
        <div class="flex flex-col gap-1.5">
          <label hlmLabel for="edit-name">{{ 'upload.name' | t }}</label>
          <input id="edit-name" hlmInput name="name" maxlength="255" autocomplete="off" [(ngModel)]="name" />
        </div>
        <div class="flex flex-col gap-1.5">
          <label hlmLabel for="edit-collection">{{ 'collections.one' | t }}</label>
          <select
            id="edit-collection"
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
          <label hlmLabel for="edit-tags">{{ 'tags.label' | t }}</label>
          <input
            id="edit-tags"
            hlmInput
            name="tags"
            autocomplete="off"
            aria-describedby="edit-tags-help"
            [(ngModel)]="tags"
          />
          <p id="edit-tags-help" class="text-muted-foreground text-xs">{{ 'tags.help' | t }}</p>
        </div>
        <app-group-picker
          idPrefix="edit-groups"
          [optional]="false"
          [options]="groupOptions()"
          [(value)]="groups"
        />
        <p class="text-destructive text-sm" role="alert">
          @if (error(); as key) {
            {{ key | t }}
          }
        </p>
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
export class EditDocumentDialogComponent implements OnInit {
  readonly document = input.required<DocumentItem>();
  readonly done = output<DocumentItem>();
  readonly closed = output<void>();

  protected name = '';
  protected tags = '';
  protected collectionId: string | null = null;
  protected readonly groups = signal<string[]>([]);
  protected readonly groupOptions = signal<string[]>([]);
  protected readonly busy = signal(false);
  protected readonly error = signal<MessageKey | null>(null);
  protected readonly store = inject(CollectionsStore);
  private readonly api = inject(DocumentsApi);
  private readonly groupsApi = inject(GroupsApi);

  ngOnInit(): void {
    const doc = this.document();
    this.name = doc.name;
    this.tags = doc.tags.join(', ');
    this.collectionId = doc.collection_id;
    this.groups.set([...doc.acl_groups]);
    this.groupsApi.list().subscribe({
      next: (options) => this.groupOptions.set(options),
      error: () => undefined, // the groups the document already has are still listed
    });
  }

  protected save(): void {
    this.busy.set(true);
    this.error.set(null);
    this.api
      .update(this.document().id, {
        name: this.name.trim() || this.document().name,
        tags: parseTags(this.tags),
        collection_id: this.collectionId,
        acl_groups: this.groups(),
      })
      .subscribe({
        next: (updated) => this.done.emit(updated),
        error: (failure: unknown) => {
          this.busy.set(false);
          this.error.set(this.messageFor(failure));
        },
      });
  }

  private messageFor(failure: unknown): MessageKey {
    if (failure instanceof HttpErrorResponse) {
      if (failure.status === 403) return 'common.ownerOnly';
      if (failure.status === 422) return 'edit.invalid';
      if (failure.status === 0) return 'common.offline';
    }
    return 'common.unknownError';
  }
}
