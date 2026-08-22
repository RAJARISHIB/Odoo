import { CanActivateFn, Router } from '@angular/router';
import { inject } from '@angular/core';

import { ADMIN_ROLES, Role } from '../models/user.model';
import { Auth } from '../services/auth';
import { TokenStorage } from '../services/token-storage';

/** Any signed-in user. Sends anonymous visitors to login, keeping the target. */
export const authGuard: CanActivateFn = (_route, state) => {
  const auth = inject(Auth);
  const router = inject(Router);

  if (auth.isAuthenticated()) return true;

  return router.createUrlTree(['/auth/login'], {
    queryParams: { redirect: state.url },
  });
};

/** Login/register pages: bounce users who are already signed in to their panel. */
export const guestGuard: CanActivateFn = () => {
  const auth = inject(Auth);
  const router = inject(Router);

  if (!auth.isAuthenticated()) return true;
  return router.createUrlTree([auth.homeRoute()]);
};

/** The admin panel: super_admin, admin, hr or manager. */
export const adminGuard: CanActivateFn = (route, state) => {
  const auth = inject(Auth);
  const router = inject(Router);

  const allowed = authGuard(route, state);
  if (allowed !== true) return allowed;

  if (auth.isAdmin()) return true;
  return router.createUrlTree(['/app']);
};

/**
 * Restrict a route to specific roles:
 *   { canActivate: [roleGuard(['super_admin', 'admin'])] }
 */
export function roleGuard(roles: Role[]): CanActivateFn {
  return (route, state) => {
    const auth = inject(Auth);
    const storage = inject(TokenStorage);
    const router = inject(Router);

    const allowed = authGuard(route, state);
    if (allowed !== true) return allowed;

    const role = auth.user()?.role ?? storage.user?.role;
    if (role && roles.includes(role)) return true;

    return router.createUrlTree([ADMIN_ROLES.includes(role as Role) ? '/admin' : '/app']);
  };
}

/**
 * Block the panels while the user is still on a system-generated password.
 *
 * HR creates an employee, the system issues their password, and they must
 * replace it before reaching anything else.
 */
export const passwordChangeGuard: CanActivateFn = (route, state) => {
  const auth = inject(Auth);
  const router = inject(Router);

  const allowed = authGuard(route, state);
  if (allowed !== true) return allowed;

  if (!auth.mustChangePassword()) return true;
  return router.createUrlTree(['/change-password']);
};

/** Root path: send visitors to their panel, or to login if signed out. */
export const rootRedirectGuard: CanActivateFn = () => {
  const auth = inject(Auth);
  const router = inject(Router);

  return router.createUrlTree([auth.isAuthenticated() ? auth.homeRoute() : '/auth/login']);
};
