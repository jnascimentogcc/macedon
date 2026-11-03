import { Injectable, signal } from '@angular/core';
import { User, UserManager, WebStorageStateStore } from 'oidc-client-ts';
import { APP_CONFIG } from '../config';

/** OIDC Authorization Code + PKCE against Keycloak (or any OIDC provider). */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly manager = new UserManager({
    authority: APP_CONFIG.oidcAuthority,
    client_id: APP_CONFIG.oidcClientId,
    redirect_uri: `${window.location.origin}/auth/callback`,
    post_logout_redirect_uri: window.location.origin,
    response_type: 'code',
    scope: 'openid profile',
    automaticSilentRenew: true,
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
  });

  readonly user = signal<User | null>(null);

  constructor() {
    this.manager.events.addUserLoaded((user) => this.user.set(user));
    this.manager.events.addUserUnloaded(() => this.user.set(null));
    this.manager.events.addAccessTokenExpired(() => this.user.set(null));
  }

  /** Restore a session kept for this browser tab, if it is still valid. */
  async restore(): Promise<void> {
    const user = await this.manager.getUser();
    this.user.set(user && !user.expired ? user : null);
  }

  get accessToken(): string | null {
    const user = this.user();
    return user && !user.expired ? user.access_token : null;
  }

  get displayName(): string {
    const profile = this.user()?.profile;
    return profile?.name ?? profile?.preferred_username ?? '';
  }

  login(returnUrl = '/'): Promise<void> {
    return this.manager.signinRedirect({ state: returnUrl });
  }

  /** Finish the redirect and return the URL the user was trying to reach. */
  async completeLogin(): Promise<string> {
    const user = await this.manager.signinRedirectCallback();
    this.user.set(user);
    const state = user.state;
    return typeof state === 'string' && state.startsWith('/') ? state : '/';
  }

  logout(): Promise<void> {
    return this.manager.signoutRedirect();
  }
}
