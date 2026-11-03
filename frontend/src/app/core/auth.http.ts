import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { CanActivateFn } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { APP_CONFIG } from '../config';
import { AuthService } from './auth.service';

/** Sends the access token to the API only, and restarts sign-in when the API rejects it. */
export const authInterceptor: HttpInterceptorFn = (request, next) => {
  if (!request.url.startsWith(APP_CONFIG.apiUrl)) {
    return next(request);
  }
  const auth = inject(AuthService);
  const token = auth.accessToken;
  const authorized = token
    ? request.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
    : request;
  return next(authorized).pipe(
    catchError((error: unknown) => {
      if (error instanceof HttpErrorResponse && error.status === 401) {
        void auth.login(window.location.pathname + window.location.search);
      }
      return throwError(() => error);
    }),
  );
};

export const authGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  if (auth.user()) {
    return true;
  }
  void auth.login(state.url);
  return false;
};
