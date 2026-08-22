import { ApplicationConfig, inject, provideAppInitializer, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  PreloadAllModules,
  TitleStrategy,
  provideRouter,
  withComponentInputBinding,
  withPreloading,
  withViewTransitions,
} from '@angular/router';
import { catchError, of } from 'rxjs';

import { Auth } from './core/services/auth';
import { TokenStorage } from './core/services/token-storage';
import { authInterceptor } from './core/interceptors/auth.interceptor';
import { errorInterceptor } from './core/interceptors/error.interceptor';
import { BrandTitleStrategy } from './core/title-strategy';
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
    provideRouter(
      routes,
      withComponentInputBinding(),
      // Every route is `loadComponent`. `startViewTransition` freezes paint
      // while the update callback runs, so a cold chunk would show as a frozen
      // page with no feedback. The app is small enough to just preload it all
      // once the first screen is up.
      withPreloading(PreloadAllModules),
      withViewTransitions({
        // The app initialiser awaits /auth/me, so without this the very first
        // paint cross-fades in from a blank document.
        skipInitialTransition: true,
        onViewTransitionCreated: ({ transition }) => {
          // The reliable half of the reduced-motion story: the CSS block in
          // _motion.scss needs `::view-transition-group(*)`, which older
          // engines do not support. This works everywhere.
          if (matchMedia('(prefers-reduced-motion: reduce)').matches) transition.skipTransition();
        },
      }),
    ),
    // Order matters: `errorInterceptor` wraps `authInterceptor`, so a 401 is
    // retried with a refreshed token before it can be turned into a toast.
    provideHttpClient(withInterceptors([errorInterceptor, authInterceptor])),
    provideAppInitializer(restoreSession),
    { provide: TitleStrategy, useClass: BrandTitleStrategy },
  ],
};
