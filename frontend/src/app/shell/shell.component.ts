import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { AuthService } from '../core/auth.service';
import { TranslatePipe } from '../core/i18n';
import { ThemeService } from '../core/theme.service';

@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, TranslatePipe, HlmButtonImports],
  template: `
    <a
      href="#main"
      class="bg-card focus:ring-ring sr-only rounded-md p-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:ring-2"
      >{{ 'nav.skip' | t }}</a
    >
    <header class="bg-card border-b">
      <div
        class="mx-auto flex max-w-[var(--content-max)] flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-2 sm:px-6"
      >
        <div class="flex items-center gap-6">
          <a routerLink="/" class="inline-flex min-h-[44px] items-center text-lg font-bold sm:min-h-[24px]">{{ 'app.name' | t }}</a>
          <nav [attr.aria-label]="'nav.main' | t" class="flex gap-1">
            <a
              hlmBtn
              variant="ghost"
              routerLink="/documents"
              routerLinkActive="bg-accent"
              ariaCurrentWhenActive="page"
              >{{ 'nav.documents' | t }}</a
            >
            <a
              hlmBtn
              variant="ghost"
              routerLink="/ask"
              routerLinkActive="bg-accent"
              ariaCurrentWhenActive="page"
              >{{ 'nav.ask' | t }}</a
            >
          </nav>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-muted-foreground hidden text-sm sm:inline">{{ auth.displayName }}</span>
          <button hlmBtn variant="ghost" type="button" (click)="theme.toggle()">
            {{ (theme.theme() === 'dark' ? 'theme.toLight' : 'theme.toDark') | t }}
          </button>
          <button hlmBtn variant="outline" type="button" (click)="auth.logout()">
            {{ 'user.signOut' | t }}
          </button>
        </div>
      </div>
    </header>
    <main id="main" tabindex="-1" class="mx-auto max-w-[var(--content-max)] px-4 py-6 sm:px-6">
      <router-outlet />
    </main>
  `,
})
export class ShellComponent {
  protected readonly auth = inject(AuthService);
  protected readonly theme = inject(ThemeService);
}
