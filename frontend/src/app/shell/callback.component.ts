import { Component, OnInit, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { AuthService } from '../core/auth.service';
import { TranslatePipe } from '../core/i18n';

/** Landing route of the OIDC redirect: exchanges the code, then goes where the user was headed. */
@Component({
  selector: 'app-callback',
  imports: [TranslatePipe, HlmButtonImports],
  template: `
    <main class="mx-auto max-w-md p-8 text-center">
      @if (failed()) {
        <p role="alert">{{ 'auth.failed' | t }}</p>
        <button hlmBtn class="mt-4" type="button" (click)="retry()">{{ 'auth.retry' | t }}</button>
      } @else {
        <p role="status">{{ 'auth.signingIn' | t }}</p>
      }
    </main>
  `,
})
export class CallbackComponent implements OnInit {
  protected readonly failed = signal(false);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  async ngOnInit(): Promise<void> {
    try {
      const target = await this.auth.completeLogin();
      await this.router.navigateByUrl(target, { replaceUrl: true });
    } catch {
      this.failed.set(true);
    }
  }

  protected retry(): void {
    void this.auth.login('/');
  }
}
