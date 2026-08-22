import { CanActivateFn, Router } from '@angular/router';
import { inject } from '@angular/core';

import { Role } from '../models/user.model';
import type { Capability } from '../../shared/shell/nav-config';
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

/** Legacy admin-panel gate. Prefer `capabilityGuard` - see below. */
export const adminGuard: CanActivateFn = (route, state) => {
  const auth = inject(Auth);
  const router = inject(Router);

  const allowed = authGuard(route, state);
  if (allowed !== true) return allowed;

  if (auth.isAdmin()) return true;
  return router.createUrlTree(['/employees']);
};

/**
 * Gate a route on a capability flag the backend returns on /auth/me:
 *   { canActivate: [capabilityGuard('can_manage_organization')] }
 *
 * Flags, not roles: the backend owns the policy and the frontend must not
 * re-derive it. Note the flags are null for the first frames after a fresh
 * sign-in, because `startSession()` does not await `loadSession()`. That does
 * not strand anyone - the nav items these guards protect are themselves hidden
 * until the flags land, so there is nothing to click yet.
 */
export function capabilityGuard(capability: Capability): CanActivateFn {
  return (route, state) => {
    const auth = inject(Auth);
    const router = inject(Router);

    const allowed = passwordChangeGuard(route, state);
    if (allowed !== true) return allowed;

    if (auth.permissions()?.[capability]) return true;
    return router.createUrlTree(['/employees']);
  };
}

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

    return router.createUrlTree(['/employees']);
  };
}

/**
 * Block the app while the user is still on a system-generated password.
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

/** Root path: everybody lands on Employees, or on login if signed out. */
export const rootRedirectGuard: CanActivateFn = () => {
  const auth = inject(Auth);
  const router = inject(Router);

  return router.createUrlTree([auth.isAuthenticated() ? auth.homeRoute() : '/auth/login']);
};
