import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { HlmBadgeImports } from '@spartan-ng/helm/badge';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmLabelImports } from '@spartan-ng/helm/label';
import { DocumentItem, DocumentsApi, QueryApi, QueryResult, errorKey } from '../core/api';
import { MessageKey, TranslatePipe } from '../core/i18n';

@Component({
  selector: 'app-ask-page',
  imports: [FormsModule, RouterLink, TranslatePipe, HlmBadgeImports, HlmButtonImports, HlmLabelImports],
  template: `
    <header class="mb-6">
      <h1 class="text-2xl font-bold">{{ 'ask.title' | t }}</h1>
      <p class="text-muted-foreground">{{ 'ask.description' | t }}</p>
    </header>

    <div class="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <form class="bg-card flex flex-col gap-4 self-start rounded-lg border p-4" (ngSubmit)="ask()" novalidate>
        <div class="flex flex-col gap-1.5">
          <label hlmLabel for="question">{{ 'ask.question' | t }}</label>
          <textarea
            id="question"
            name="question"
            rows="5"
            maxlength="2000"
            class="border-input bg-background focus-visible:ring-ring/50 focus-visible:border-ring w-full rounded-md border p-2.5 text-sm outline-none focus-visible:ring-3"
            aria-describedby="question-help question-error"
            [attr.aria-invalid]="formError() ? 'true' : null"
            [(ngModel)]="question"
          ></textarea>
          <p id="question-help" class="text-muted-foreground text-xs">{{ 'ask.questionHelp' | t }}</p>
          <p id="question-error" class="text-destructive text-sm" role="alert">
            @if (formError(); as key) {
              {{ key | t }}
            }
          </p>
        </div>

        <div class="flex flex-col gap-1.5">
          <label hlmLabel for="scope">{{ 'ask.document' | t }}</label>
          <select
            id="scope"
            name="scope"
            class="border-input bg-background focus-visible:ring-ring/50 focus-visible:border-ring h-9 w-full rounded-md border px-2 text-sm outline-none focus-visible:ring-3"
            [(ngModel)]="documentId"
          >
            <option [ngValue]="null">{{ 'ask.allDocuments' | t }}</option>
            @for (doc of documents(); track doc.id) {
              <option [ngValue]="doc.id">{{ doc.name }}</option>
            }
          </select>
        </div>

        <button hlmBtn type="submit" [disabled]="busy()">
          {{ (busy() ? 'ask.submitting' : 'ask.submit') | t }}
        </button>
      </form>

      <section aria-live="polite" aria-label="Result">
        @if (failure(); as key) {
          <div class="border-[var(--danger-border)] bg-[var(--danger-bg)] rounded-lg border p-4" role="alert">
            {{ key | t }}
          </div>
        } @else if (result(); as current) {
          <article class="bg-card rounded-lg border p-4">
            <h2 class="text-lg font-bold">{{ 'ask.answer' | t }}</h2>
            <p class="mt-2 whitespace-pre-wrap">{{ current.answer }}</p>
            @if (current.model) {
              <p class="text-muted-foreground mt-3 text-xs">{{ 'ask.model' | t: { model: current.model } }}</p>
            }
          </article>

          <h2 class="mt-6 mb-2 text-lg font-bold">{{ 'ask.sources' | t }}</h2>
          @if (current.sources.length === 0) {
            <p class="text-muted-foreground">{{ 'ask.noSources' | t }}</p>
          } @else {
            <ol class="flex flex-col gap-3">
              @for (source of current.sources; track source.id) {
                <li class="bg-card rounded-lg border p-4">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="font-mono text-sm">[{{ source.id }}]</span>
                    <a
                      [routerLink]="['/documents', source.document_id]"
                      class="font-medium underline-offset-4 hover:underline"
                      >{{ source.document_name }}</a
                    >
                    <span hlmBadge variant="outline" [class]="source.cited ? citedTone : ''">{{
                      (source.cited ? 'ask.cited' : 'ask.notCited') | t
                    }}</span>
                  </div>
                  <p class="text-muted-foreground mt-1 font-mono text-xs">
                    {{ 'ask.version' | t: { version: source.version } }}
                    @if (source.page !== null) {
                      · {{ 'ask.page' | t: { page: source.page } }}
                    }
                    · {{ source.section }}
                  </p>
                  <details class="mt-2">
                    <summary class="cursor-pointer text-sm">{{ 'ask.showText' | t }}</summary>
                    <p class="mt-2 text-sm whitespace-pre-wrap">{{ source.text }}</p>
                  </details>
                </li>
              }
            </ol>
          }
        } @else {
          <p class="text-muted-foreground">{{ (busy() ? 'ask.submitting' : 'ask.empty') | t }}</p>
        }
      </section>
    </div>
  `,
})
export class AskPageComponent implements OnInit {
  protected question = '';
  protected documentId: string | null = null;
  protected readonly documents = signal<DocumentItem[]>([]);
  protected readonly result = signal<QueryResult | null>(null);
  protected readonly busy = signal(false);
  protected readonly failure = signal<MessageKey | null>(null);
  protected readonly formError = signal<MessageKey | null>(null);
  protected readonly citedTone =
    'bg-[var(--success-bg)] text-[var(--success)] border-[var(--success-border)]';

  private readonly queryApi = inject(QueryApi);
  private readonly documentsApi = inject(DocumentsApi);

  ngOnInit(): void {
    this.documentsApi.list(100, 0, false).subscribe({
      next: (page) => this.documents.set(page.items.filter((doc) => doc.active_version)),
      error: () => undefined, // the scope selector is optional; asking still works
    });
  }

  protected ask(): void {
    const question = this.question.trim();
    if (!question) {
      this.formError.set('ask.questionRequired');
      return;
    }
    this.formError.set(null);
    this.failure.set(null);
    this.busy.set(true);
    this.queryApi.ask(question, this.documentId).subscribe({
      next: (result) => {
        this.result.set(result);
        this.busy.set(false);
      },
      error: (error: unknown) => {
        this.result.set(null);
        this.busy.set(false);
        this.failure.set(this.messageFor(error));
      },
    });
  }

  private messageFor(error: unknown): MessageKey {
    if (error instanceof HttpErrorResponse) {
      if (error.status === 429) {
        return 'ask.tooMany';
      }
      if (error.status === 502 || error.status === 503) {
        return 'ask.unavailable';
      }
    }
    return errorKey(error, 'ask.failed');
  }
}
