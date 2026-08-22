import { HttpErrorResponse, HttpInterceptorFn, HttpRequest } from '@angular/common/http';
import { inject } from '@angular/core';
import { BehaviorSubject, Observable, catchError, filter, switchMap, take, throwError } from 'rxjs';

import { Auth } from '../services/auth';
import { TokenStorage } from '../services/token-storage';

/** Endpoints that must never carry a token or trigger a refresh. */
const PUBLIC_PATHS = ['/auth/login', '/auth/register', '/auth/refresh', '/health'];

// Shared across calls so a burst of parallel 401s triggers exactly one refresh;
// the rest wait here for the new token.
let refreshing = false;
const refreshedToken$ = new BehaviorSubject<string | null>(null);

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const storage = inject(TokenStorage);
  const auth = inject(Auth);

  const isPublic = PUBLIC_PATHS.some((path) => request.url.includes(path));
  const token = storage.accessToken;

  const outbound = isPublic || !token ? request : withToken(request, token);

  return next(outbound).pipe(
    catchError((error: HttpErrorResponse) => {
      const isAuthFailure = error.status === 401 && !isPublic && !!storage.refreshToken;
      if (!isAuthFailure) return throwError(() => error);
      return retryWithRefreshedToken(request, next, auth);
    }),
  );
};

function withToken(request: HttpRequest<unknown>, token: string): HttpRequest<unknown> {
  return request.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
}

/**
 * Refresh once, then replay the failed request with the new token. Requests
 * that arrive mid-refresh queue on `refreshedToken$` instead of refreshing too.
 */
function retryWithRefreshedToken(
  request: HttpRequest<unknown>,
  next: (req: HttpRequest<unknown>) => Observable<never | any>,
  auth: Auth,
): Observable<any> {
  if (refreshing) {
    return refreshedToken$.pipe(
      filter((token): token is string => token !== null),
      take(1),
      switchMap((token) => next(withToken(request, token))),
    );
  }

  refreshing = true;
  refreshedToken$.next(null);

  return auth.refreshTokens().pipe(
    switchMap((tokens) => {
      refreshing = false;
      refreshedToken$.next(tokens.access_token);
      return next(withToken(request, tokens.access_token));
    }),
    catchError((refreshError) => {
      refreshing = false;
      // The refresh token is dead too - end the session and send them to login.
      auth.logout();
      return throwError(() => refreshError);
    }),
  );
}
