import { Injectable, computed, inject, signal } from '@angular/core';
import { Collection, CollectionsApi, MeApi } from './api';

export interface CollectionNode {
  collection: Collection;
  /** Documents in this collection and everything below it. */
  total: number;
}

/** Splits "a, B ,c" into tags; the server normalizes and validates them. */
export function parseTags(text: string): string[] {
  return text
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean);
}

/** The collection tree, shared by every screen, plus whether the caller administers it. */
@Injectable({ providedIn: 'root' })
export class CollectionsStore {
  readonly items = signal<Collection[]>([]);
  readonly isAdmin = signal(false);
  readonly loaded = signal(false);

  /** Depth-first, siblings by name, so a parent is always followed by its children. */
  readonly ordered = computed<CollectionNode[]>(() => {
    const children = new Map<string | null, Collection[]>();
    for (const item of this.items()) {
      const siblings = children.get(item.parent_id) ?? [];
      siblings.push(item);
      children.set(item.parent_id, siblings);
    }
    const nodes: CollectionNode[] = [];
    const visit = (parent: string | null): number => {
      let sum = 0;
      const siblings = (children.get(parent) ?? []).sort((a, b) =>
        a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }),
      );
      for (const collection of siblings) {
        const node: CollectionNode = { collection, total: collection.document_count };
        nodes.push(node);
        node.total += visit(collection.id);
        sum += node.total;
      }
      return sum;
    };
    visit(null);
    return nodes;
  });

  private readonly collectionsApi = inject(CollectionsApi);
  private readonly meApi = inject(MeApi);

  load(): void {
    this.collectionsApi.list().subscribe({
      next: (items) => {
        this.items.set(items);
        this.loaded.set(true);
      },
      error: () => this.loaded.set(true),
    });
    this.meApi.get().subscribe({
      next: (me) => this.isAdmin.set(me.is_admin),
      error: () => this.isAdmin.set(false),
    });
  }

  /** "Legal / Contracts" for a collection id, or an empty string. */
  pathName(id: string | null): string {
    const byId = new Map(this.items().map((item) => [item.id, item]));
    const names: string[] = [];
    for (let node = id ? byId.get(id) : undefined; node; node = node.parent_id ? byId.get(node.parent_id) : undefined) {
      names.unshift(node.name);
    }
    return names.join(' / ');
  }
}
