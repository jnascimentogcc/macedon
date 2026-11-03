import { Injectable, Pipe, PipeTransform, inject } from '@angular/core';

/** English interface strings. Add another locale as a sibling object with the same keys. */
export const EN = {
  'app.name': 'Macedon',
  'nav.documents': 'Documents',
  'nav.ask': 'Ask',
  'nav.main': 'Main navigation',
  'nav.skip': 'Skip to content',
  'user.signOut': 'Sign out',
  'theme.toLight': 'Switch to light theme',
  'theme.toDark': 'Switch to dark theme',

  'common.loading': 'Loading…',
  'common.retry': 'Try again',
  'common.cancel': 'Cancel',
  'common.close': 'Close',
  'common.previous': 'Previous',
  'common.next': 'Next',
  'common.optional': '(optional)',
  'common.required': '(required)',
  'common.none': 'None',
  'common.unknownError': 'Something went wrong. Try again in a moment.',
  'common.ownerOnly': 'Only the owner of this document can change it.',
  'common.pagination': 'Pagination',
  'common.forbidden': 'You do not have access to this item.',
  'common.notFound': 'This item does not exist or you cannot see it.',
  'common.offline': 'The server could not be reached. Check your connection and try again.',

  'status.processing': 'Processing',
  'status.active': 'Active',
  'status.archived': 'Archived',
  'status.failed': 'Failed',

  'documents.title': 'Documents',
  'documents.description': 'Upload documents, follow their processing and manage versions.',
  'documents.upload': 'Upload document',
  'documents.showArchived': 'Show archived documents',
  'documents.col.name': 'Name',
  'documents.col.collection': 'Collection',
  'documents.col.type': 'Type',
  'documents.col.status': 'Latest version',
  'documents.col.active': 'Active version',
  'documents.col.created': 'Created',
  'documents.noneActive': 'No active version',
  'documents.archivedBadge': 'Archived',
  'documents.empty.title': 'No documents yet',
  'documents.empty.body': 'Upload a PDF, DOCX or TXT file to make it searchable.',
  'documents.error.load': 'The documents could not be loaded.',
  'documents.range': 'Showing {from}–{to} of {total}',
  'documents.table': 'Documents',

  'upload.title': 'Upload document',
  'upload.newVersionTitle': 'Upload new version',
  'upload.file': 'File',
  'upload.fileHelp': 'PDF, DOCX or TXT. The text is sent to the configured AI provider.',
  'upload.name': 'Name',
  'upload.nameHelp': 'Defaults to the file name.',
  'upload.groups': 'Groups with access',
  'upload.groupsHelp':
    'You and administrators always have access; select none to keep it private.',
  'upload.groupsNone': 'No groups are available to share with.',
  'upload.submit': 'Upload',
  'upload.submitting': 'Uploading…',
  'upload.fileRequired': 'Choose a file to upload.',
  'upload.tooLarge': 'The file is larger than the server accepts.',
  'upload.unsupported': 'This file type is not supported. Use PDF, DOCX or TXT.',
  'upload.duplicate': 'This exact file is already the latest version, so nothing was added.',
  'upload.accepted': 'Upload accepted. Processing has started.',

  'detail.back': 'Back to documents',
  'detail.id': 'Identifier',
  'detail.owner': 'Owner',
  'detail.groups': 'Groups with access',
  'detail.tags': 'Tags',
  'detail.created': 'Created',
  'detail.versions': 'Versions',
  'detail.versionsDescription': 'Only the active version answers questions.',
  'detail.col.number': 'Version',
  'detail.col.status': 'Status',
  'detail.col.hash': 'SHA-256',
  'detail.col.author': 'Author',
  'detail.col.created': 'Created',
  'detail.col.actions': 'Actions',
  'detail.newVersion': 'Upload new version',
  'detail.activate': 'Make active',
  'detail.activateLabel': 'Make version {number} active',
  'detail.activated': 'Version {number} is now active.',
  'detail.activateFailed': 'The version could not be activated.',
  'detail.delete': 'Archive document',
  'detail.deleteTitle': 'Archive this document?',
  'detail.deleteBody':
    'All versions of {name} are archived and stop answering questions. The history is kept for audit.',
  'detail.deleteConfirm': 'Archive',
  'detail.archivedNotice': 'This document is archived and no longer answers questions.',
  'detail.processingNotice': 'Processing in the background. This page updates by itself.',
  'detail.errorLoad': 'The document could not be loaded.',
  'detail.versionFailed': 'Processing failed: {error}',

  'ask.title': 'Ask',
  'ask.description': 'Ask a question. Answers cite the documents you can read.',
  'ask.question': 'Question',
  'ask.questionHelp': 'Ask in plain language, up to 2000 characters.',
  'ask.document': 'Search in',
  'ask.allDocuments': 'All documents',
  'ask.submit': 'Ask',
  'ask.submitting': 'Searching…',
  'ask.answer': 'Answer',
  'ask.asked': 'Your question',
  'ask.disclaimer': 'Check the sources before relying on this answer.',
  'ask.sources': 'Sources',
  'ask.noSources': 'No source was found for this question.',
  'ask.cited': 'Cited',
  'ask.notCited': 'Not cited',
  'ask.page': 'page {page}',
  'ask.version': 'version {version}',
  'ask.showText': 'Show passage',
  'ask.empty': 'Your answer and its sources will appear here.',
  'ask.tooMany': 'Too many questions in a short time. Wait a moment and try again.',
  'ask.unavailable': 'The answering service is unavailable right now. Try again later.',
  'ask.failed': 'The question could not be answered.',
  'ask.questionRequired': 'Write a question first.',

  'collections.title': 'Collections',
  'collections.all': 'All documents',
  'collections.one': 'Collection',
  'collections.none': 'No collection',
  'collections.manage': 'Manage collections',
  'collections.newRoot': 'New collection',
  'collections.newChild': 'New subcollection',
  'collections.rename': 'Rename',
  'collections.delete': 'Delete',
  'collections.createTitle': 'New collection',
  'collections.renameTitle': 'Rename collection',
  'collections.name': 'Name',
  'collections.save': 'Save',
  'collections.nameRequired': 'Enter a name.',
  'collections.duplicate': 'A collection with this name already exists here.',
  'collections.tooDeep': 'Collections can be nested four levels deep.',
  'collections.adminOnly': 'Only administrators can change collections.',
  'collections.deleteTitle': 'Delete this collection?',
  'collections.deleteBody': '{name} will be removed. Only empty collections can be deleted.',
  'collections.notEmpty': 'It still has subcollections or documents. Move or remove them first.',
  'tags.label': 'Tags',
  'tags.help': 'Comma-separated, for example: policy, 2026. They are saved in lowercase.',
  'tags.invalid': 'Tags can have at most 40 characters each, and there can be at most 20.',
  'tags.filter': 'Filter by tags',
  'tags.filterHelp': 'Documents must have all the tags you list.',
  'tags.apply': 'Apply',
  'tags.clear': 'Clear',
  'edit.title': 'Edit document',
  'edit.action': 'Edit details',
  'documents.filteredEmpty': 'No documents match these filters.',
  'ask.scope': 'Search in',
  'ask.scopeCollections': 'Collections',
  'ask.scopeDocuments': 'Documents',
  'ask.tags': 'Only documents with tags',

  'auth.signingIn': 'Signing you in…',
  'auth.failed': 'Sign-in failed. Start again.',
  'auth.retry': 'Sign in again',
} as const;

export type MessageKey = keyof typeof EN;
type Params = Record<string, string | number>;

@Injectable({ providedIn: 'root' })
export class I18n {
  readonly locale = 'en';

  t(key: MessageKey, params?: Params): string {
    const template: string = EN[key];
    return params
      ? template.replace(/\{(\w+)\}/g, (_, name: string) => String(params[name] ?? `{${name}}`))
      : template;
  }
}

@Pipe({ name: 't' })
export class TranslatePipe implements PipeTransform {
  private readonly i18n = inject(I18n);

  transform(key: MessageKey, params?: Params): string {
    return this.i18n.t(key, params);
  }
}
