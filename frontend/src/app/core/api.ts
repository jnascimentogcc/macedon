import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { APP_CONFIG } from '../config';
import { MessageKey } from './i18n';

export type VersionStatus = 'processing' | 'active' | 'archived' | 'failed';

export interface DocumentVersion {
  id: string;
  number: number;
  status: VersionStatus;
  file_hash: string;
  author_id: string;
  error: string | null;
  created_at: string;
}

export interface DocumentItem {
  id: string;
  name: string;
  doc_type: string;
  owner_id: string;
  tags: string[];
  collection_id: string | null;
  acl_users: string[];
  acl_groups: string[];
  created_at: string;
  archived_at: string | null;
  latest_version: DocumentVersion | null;
  active_version: DocumentVersion | null;
}

export interface Collection {
  id: string;
  parent_id: string | null;
  name: string;
  depth: number;
  document_count: number;
}

export interface DocumentFilters {
  collectionId: string | null;
  tags: string[];
}

export interface DocumentChanges {
  name?: string;
  tags?: string[];
  collection_id?: string | null;
}

export interface DocumentPage {
  items: DocumentItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface UploadResult {
  document: DocumentItem;
  version: DocumentVersion;
  duplicate: boolean;
}

export interface Source {
  id: number;
  document_id: string;
  document_name: string;
  version: number;
  page: number | null;
  section: string;
  text: string;
  cited: boolean;
}

export interface QueryResult {
  answer: string;
  sources: Source[];
  model: string | null;
}

export interface UploadFields {
  file: File;
  name?: string;
  groups?: string[];
  tags?: string[];
  collectionId?: string | null;
}

/** Maps a failed request to an interface message the user can act on. */
export function errorKey(error: unknown, fallback: MessageKey = 'common.unknownError'): MessageKey {
  if (!(error instanceof HttpErrorResponse)) {
    return fallback;
  }
  switch (error.status) {
    case 0:
      return 'common.offline';
    case 403:
      return 'common.forbidden';
    case 404:
      return 'common.notFound';
    default:
      return fallback;
  }
}

@Injectable({ providedIn: 'root' })
export class DocumentsApi {
  private readonly http = inject(HttpClient);
  private readonly base = `${APP_CONFIG.apiUrl}/documents`;

  list(
    limit: number,
    offset: number,
    includeArchived: boolean,
    filters: DocumentFilters = { collectionId: null, tags: [] },
  ): Observable<DocumentPage> {
    let params = new HttpParams()
      .set('limit', limit)
      .set('offset', offset)
      .set('include_archived', includeArchived);
    if (filters.collectionId) {
      params = params.set('collection_id', filters.collectionId);
    }
    for (const tag of filters.tags) {
      params = params.append('tag', tag);
    }
    return this.http.get<DocumentPage>(this.base, { params });
  }

  get(id: string): Observable<DocumentItem> {
    return this.http.get<DocumentItem>(`${this.base}/${id}`);
  }

  versions(id: string): Observable<DocumentVersion[]> {
    return this.http.get<DocumentVersion[]>(`${this.base}/${id}/versions`);
  }

  upload(fields: UploadFields): Observable<UploadResult> {
    const body = new FormData();
    body.append('file', fields.file);
    if (fields.name) {
      body.append('name', fields.name);
    }
    for (const group of fields.groups ?? []) {
      body.append('acl_groups', group);
    }
    for (const tag of fields.tags ?? []) {
      body.append('tags', tag);
    }
    if (fields.collectionId) {
      body.append('collection_id', fields.collectionId);
    }
    return this.http.post<UploadResult>(this.base, body);
  }

  update(id: string, changes: DocumentChanges): Observable<DocumentItem> {
    return this.http.patch<DocumentItem>(`${this.base}/${id}`, changes);
  }

  uploadVersion(id: string, file: File): Observable<UploadResult> {
    const body = new FormData();
    body.append('file', file);
    return this.http.post<UploadResult>(`${this.base}/${id}/versions`, body);
  }

  activate(id: string, number: number): Observable<DocumentVersion> {
    return this.http.post<DocumentVersion>(`${this.base}/${id}/versions/${number}/activate`, {});
  }

  archive(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`);
  }
}

@Injectable({ providedIn: 'root' })
export class QueryApi {
  private readonly http = inject(HttpClient);

  ask(question: string, scope: QueryScope): Observable<QueryResult> {
    return this.http.post<QueryResult>(`${APP_CONFIG.apiUrl}/query`, {
      question,
      document_id: scope.documentId,
      collection_id: scope.collectionId,
      tags: scope.tags,
    });
  }
}

export interface QueryScope {
  documentId: string | null;
  collectionId: string | null;
  tags: string[];
}

@Injectable({ providedIn: 'root' })
export class CollectionsApi {
  private readonly http = inject(HttpClient);
  private readonly base = `${APP_CONFIG.apiUrl}/collections`;

  list(): Observable<Collection[]> {
    return this.http.get<Collection[]>(this.base);
  }

  create(name: string, parentId: string | null): Observable<Collection> {
    return this.http.post<Collection>(this.base, { name, parent_id: parentId });
  }

  rename(id: string, name: string): Observable<Collection> {
    return this.http.patch<Collection>(`${this.base}/${id}`, { name });
  }

  remove(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`);
  }
}

@Injectable({ providedIn: 'root' })
export class GroupsApi {
  private readonly http = inject(HttpClient);

  /** Groups a document can be shared with. */
  list(): Observable<string[]> {
    return this.http.get<string[]>(`${APP_CONFIG.apiUrl}/groups`);
  }
}

@Injectable({ providedIn: 'root' })
export class MeApi {
  private readonly http = inject(HttpClient);

  get(): Observable<{ user_id: string; groups: string[]; is_admin: boolean }> {
    return this.http.get<{ user_id: string; groups: string[]; is_admin: boolean }>(
      `${APP_CONFIG.apiUrl}/me`,
    );
  }
}
