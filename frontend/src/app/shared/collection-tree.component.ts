import { Component, computed, inject, input, output } from '@angular/core';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { Collection } from '../core/api';
import { CollectionsStore } from '../core/collections.store';
import { TranslatePipe } from '../core/i18n';

/** The collection tree as a keyboard-friendly list of buttons; admins get management actions. */
@Component({
  selector: 'app-collection-tree',
  imports: [TranslatePipe, HlmButtonImports],
  template: `
    <nav [attr.aria-label]="'collections.title' | t">
      <h2 class="mb-2 text-sm font-bold">{{ 'collections.title' | t }}</h2>
      <ul class="flex flex-col gap-0.5">
        <li>
          <button
            type="button"
            class="hover:bg-accent flex w-full items-center justify-between rounded-md px-2 py-2 text-left text-sm"
            [class.bg-accent]="selectedId() === null"
            [attr.aria-current]="selectedId() === null ? 'true' : null"
            (click)="selected.emit(null)"
          >
            <span>{{ 'collections.all' | t }}</span>
          </button>
        </li>
        @for (node of store.ordered(); track node.collection.id) {
          <li>
            <button
              type="button"
              class="hover:bg-accent flex w-full items-center justify-between gap-2 rounded-md py-2 pr-2 text-left text-sm"
              [style.padding-left.px]="8 + (node.collection.depth - 1) * 16"
              [class.bg-accent]="selectedId() === node.collection.id"
              [attr.aria-current]="selectedId() === node.collection.id ? 'true' : null"
              (click)="selected.emit(node.collection.id)"
            >
              <span class="min-w-0 break-words">{{ node.collection.name }}</span>
              <span class="text-muted-foreground font-mono text-xs">{{ node.total }}</span>
            </button>
          </li>
        }
      </ul>
    </nav>

    @if (store.isAdmin()) {
      <div class="mt-4 flex flex-col gap-2" role="group" [attr.aria-label]="'collections.manage' | t">
        <button hlmBtn variant="outline" size="sm" type="button" (click)="create.emit(null)">
          {{ 'collections.newRoot' | t }}
        </button>
        @if (current(); as chosen) {
          <button
            hlmBtn
            variant="outline"
            size="sm"
            type="button"
            [disabled]="chosen.depth >= maxDepth"
            (click)="create.emit(chosen)"
          >
            {{ 'collections.newChild' | t }}
          </button>
          <button hlmBtn variant="outline" size="sm" type="button" (click)="rename.emit(chosen)">
            {{ 'collections.rename' | t }}
          </button>
          <button hlmBtn variant="destructive" size="sm" type="button" (click)="remove.emit(chosen)">
            {{ 'collections.delete' | t }}
          </button>
        }
      </div>
    }
  `,
})
export class CollectionTreeComponent {
  readonly selectedId = input<string | null>(null);
  readonly selected = output<string | null>();
  readonly create = output<Collection | null>();
  readonly rename = output<Collection>();
  readonly remove = output<Collection>();

  protected readonly store = inject(CollectionsStore);
  protected readonly maxDepth = 4;
  protected readonly current = computed(
    () => this.store.items().find((item) => item.id === this.selectedId()) ?? null,
  );
}
