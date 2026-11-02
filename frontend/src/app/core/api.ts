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
  acl_users: string[];
  acl_groups: string[];
  created_at: string;
  archived_at: string | null;
  latest_version: DocumentVersion | null;
  active_version: DocumentVersion | null;
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

  list(limit: number, offset: number, includeArchived: boolean): Observable<DocumentPage> {
    const params = new HttpParams()
      .set('limit', limit)
      .set('offset', offset)
      .set('include_archived', includeArchived);
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
    return this.http.post<UploadResult>(this.base, body);
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

  ask(question: string, documentId: string | null): Observable<QueryResult> {
    return this.http.post<QueryResult>(`${APP_CONFIG.apiUrl}/query`, {
      question,
      document_id: documentId,
    });
  }
}
