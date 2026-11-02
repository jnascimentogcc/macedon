import { Routes } from '@angular/router';
import { AskPageComponent } from './ask/ask-page.component';
import { authGuard } from './core/auth.http';
import { DocumentDetailComponent } from './documents/document-detail.component';
import { DocumentsPageComponent } from './documents/documents-page.component';
import { CallbackComponent } from './shell/callback.component';
import { ShellComponent } from './shell/shell.component';

export const routes: Routes = [
  { path: 'auth/callback', component: CallbackComponent },
  {
    path: '',
    component: ShellComponent,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'documents' },
      { path: 'documents', component: DocumentsPageComponent, title: 'Documents · Macedon' },
      { path: 'documents/:id', component: DocumentDetailComponent, title: 'Document · Macedon' },
      { path: 'ask', component: AskPageComponent, title: 'Ask · Macedon' },
    ],
  },
  { path: '**', redirectTo: '' },
];
