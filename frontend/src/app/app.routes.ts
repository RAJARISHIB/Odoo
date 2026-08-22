import { Routes } from '@angular/router';

import {
  adminGuard,
  authGuard,
  guestGuard,
  passwordChangeGuard,
  rootRedirectGuard,
} from './core/guards/auth.guard';

/**
 * Two panels behind one login:
 *   /auth/*   public - login and organization signup
 *   /admin/*  admin panel  (super_admin, admin, hr, manager)
 *   /app/*    user panel   (every signed-in employee)
 *
 * Both shells are lazy-loaded, so a user only downloads the panel they use.
 */
export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    canActivate: [rootRedirectGuard],
    // Never reached: the guard always redirects.
    children: [],
  },

  {
    path: 'auth',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/auth-layout').then((m) => m.AuthLayout),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'login' },
      { path: 'login', loadComponent: () => import('./features/auth/login').then((m) => m.Login) },
      { path: 'register', loadComponent: () => import('./features/auth/register').then((m) => m.Register) },
    ],
  },

  {
    // Forced first-login password change. Outside both panels: a user who has
    // not set their own password yet is not allowed into either.
    path: 'change-password',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/auth/change-password').then((m) => m.ChangePassword),
  },

  {
    path: 'admin',
    canActivate: [adminGuard, passwordChangeGuard],
    loadComponent: () => import('./features/admin/admin-shell').then((m) => m.AdminShell),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      {
        path: 'dashboard',
        loadComponent: () => import('./features/admin/dashboard/dashboard').then((m) => m.AdminDashboard),
      },
      {
        path: 'employees',
        loadComponent: () => import('./features/admin/employees/employees').then((m) => m.Employees),
      },
      {
        path: 'attendance',
        loadComponent: () => import('./features/admin/attendance/attendance-board').then((m) => m.AttendanceBoard),
      },
      {
        path: 'organization',
        loadComponent: () => import('./features/admin/organization/organization-settings').then((m) => m.OrganizationSettings),
      },
    ],
  },

  {
    path: 'app',
    canActivate: [authGuard, passwordChangeGuard],
    loadComponent: () => import('./features/user/user-shell').then((m) => m.UserShell),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      {
        path: 'dashboard',
        loadComponent: () => import('./features/user/dashboard/dashboard').then((m) => m.UserDashboard),
      },
      {
        path: 'attendance',
        loadComponent: () => import('./features/user/attendance/my-attendance').then((m) => m.MyAttendance),
      },
      {
        path: 'profile',
        loadComponent: () => import('./features/user/profile/profile').then((m) => m.Profile),
      },
    ],
  },

  {
    path: '**',
    loadComponent: () => import('./shared/not-found/not-found').then((m) => m.NotFound),
  },
];
