import { ApplicationConfig, inject, provideAppInitializer, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { catchError, of } from 'rxjs';

import { Auth } from './core/services/auth';
import { TokenStorage } from './core/services/token-storage';
import { authInterceptor } from './core/interceptors/auth.interceptor';
import { errorInterceptor } from './core/interceptors/error.interceptor';
import { routes } from './app.routes';

/**
 * On a reload, restore the session from the stored token before the first route
 * renders, so guards see the real user instead of bouncing to login. A failure
 * is swallowed: the guards then correctly treat the visitor as signed out.
 */
function restoreSession() {
  const storage = inject(TokenStorage);
  const auth = inject(Auth);

  if (!storage.accessToken) return of(null);
  return auth.loadSession().pipe(catchError(() => of(null)));
}

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes, withComponentInputBinding()),
    // Order matters: `errorInterceptor` wraps `authInterceptor`, so a 401 is
    // retried with a refreshed token before it can be turned into a toast.
    provideHttpClient(withInterceptors([errorInterceptor, authInterceptor])),
    provideAppInitializer(restoreSession),
  ],
};
