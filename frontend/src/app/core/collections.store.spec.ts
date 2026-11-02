import { TestBed } from '@angular/core/testing';
import { Collection } from './api';
import { CollectionsStore, parseTags } from './collections.store';

const node = (id: string, parent: string | null, name: string, depth: number, count = 0): Collection => ({
  id,
  parent_id: parent,
  name,
  depth,
  document_count: count,
});

describe('CollectionsStore', () => {
  const store = () => TestBed.inject(CollectionsStore);

  it('orders parents before their children and siblings by name', () => {
    const tree = store();
    tree.items.set([
      node('c', 'a', 'Contracts', 2),
      node('b', null, 'Finance', 1),
      node('a', null, 'Legal', 1),
      node('d', 'a', 'Cases', 2),
    ]);

    expect(tree.ordered().map((n) => n.collection.name)).toEqual([
      'Finance',
      'Legal',
      'Cases',
      'Contracts',
    ]);
  });

  it('totals documents over the whole subtree', () => {
    const tree = store();
    tree.items.set([
      node('a', null, 'Legal', 1, 1),
      node('c', 'a', 'Contracts', 2, 2),
      node('s', 'c', 'Suppliers', 3, 4),
    ]);

    expect(Object.fromEntries(tree.ordered().map((n) => [n.collection.name, n.total]))).toEqual({
      Legal: 7,
      Contracts: 6,
      Suppliers: 4,
    });
  });

  it('writes the path of a collection, and nothing for none', () => {
    const tree = store();
    tree.items.set([node('a', null, 'Legal', 1), node('c', 'a', 'Contracts', 2)]);

    expect(tree.pathName('c')).toBe('Legal / Contracts');
    expect(tree.pathName(null)).toBe('');
  });
});

describe('parseTags', () => {
  it('splits on commas, trims and drops blanks', () => {
    expect(parseTags(' policy ,2026,, ')).toEqual(['policy', '2026']);
    expect(parseTags('')).toEqual([]);
  });
});
