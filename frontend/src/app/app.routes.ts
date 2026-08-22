import { Routes } from '@angular/router';

import {
  authGuard,
  capabilityGuard,
  guestGuard,
  passwordChangeGuard,
  rootRedirectGuard,
} from './core/guards/auth.guard';

/**
 * One shell behind one login.
 *
 * There is no separate admin panel: everybody gets the same chrome and the same
 * routes, and admin power shows up as capability-gated nav items under
 * /settings plus inline actions on the shared pages.
 *
 * The leave module keeps its files under features/admin/leave, but its routes
 * are placed by audience rather than by folder: approving requests is a
 * day-to-day job so it sits beside Time off, while policy, holidays and the
 * roll-up are configuration and live under /settings.
 *
 * `title` sets document.title through Angular's built-in TitleStrategy.
 * `data.breadcrumb` feeds the topbar - see AppShell.crumbs().
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
      {
        path: 'login',
        title: 'Sign in',
        loadComponent: () => import('./features/auth/login').then((m) => m.Login),
      },
      {
        path: 'register',
        title: 'Create organization',
        loadComponent: () => import('./features/auth/register').then((m) => m.Register),
      },
    ],
  },

  {
    // Forced first-login password change. Outside the shell: a user still on a
    // system-generated password is not allowed anywhere else.
    path: 'change-password',
    title: 'Set your password',
    canActivate: [authGuard],
    loadComponent: () => import('./features/auth/change-password').then((m) => m.ChangePassword),
  },

  {
    path: '',
    canActivate: [authGuard, passwordChangeGuard],
    loadComponent: () => import('./shared/shell/app-shell').then((m) => m.AppShell),
    children: [
      {
        path: 'employees',
        data: { breadcrumb: 'Employees' },
        children: [
          {
            path: '',
            title: 'Employees',
            loadComponent: () =>
              import('./features/employees/directory/directory').then((m) => m.Directory),
          },
          {
            path: ':id',
            title: 'Employee',
            data: { breadcrumb: 'Details' },
            loadComponent: () =>
              import('./features/employees/detail/employee-detail').then((m) => m.EmployeeDetail),
          },
        ],
      },

      {
        path: 'teams',
        title: 'My team',
        data: { breadcrumb: 'My Team' },
        loadComponent: () => import('./features/teams/my-team/my-team').then((m) => m.MyTeam),
      },

      {
        path: 'attendance',
        data: { breadcrumb: 'Attendance' },
        children: [
          {
            path: '',
            title: 'My attendance',
            loadComponent: () =>
              import('./features/user/attendance/my-attendance').then((m) => m.MyAttendance),
          },
          {
            path: 'team',
            title: 'Team attendance',
            data: { breadcrumb: 'Team' },
            canActivate: [capabilityGuard('can_view_all_attendance')],
            loadComponent: () =>
              import('./features/admin/attendance/attendance-board').then((m) => m.AttendanceBoard),
          },
        ],
      },

      {
        path: 'time-off',
        data: { breadcrumb: 'Time off' },
        children: [
          {
            path: '',
            title: 'Time off',
            loadComponent: () =>
              import('./features/user/calendar/calendar').then((m) => m.UserCalendar),
          },
          {
            path: 'requests',
            title: 'Leave approvals',
            data: { breadcrumb: 'Approvals' },
            canActivate: [capabilityGuard('can_approve_attendance')],
            loadComponent: () =>
              import('./features/admin/leave/requests/leave-requests').then((m) => m.LeaveRequests),
          },
        ],
      },

      {
        path: 'claims',
        title: 'Expense Claims',
        data: { breadcrumb: 'Claims' },
        loadComponent: () => import('./features/user/claims/claims').then((m) => m.ClaimsComponent),
      },

      {
        path: 'payroll',
        title: 'My Payroll',
        data: { breadcrumb: 'My Payroll' },
        loadComponent: () => import('./features/user/payroll/my-payroll').then((m) => m.MyPayrollComponent),
      },

      {
        path: 'fines',
        title: 'My Fines',
        data: { breadcrumb: 'Fines' },
        loadComponent: () => import('./features/user/fines/fines').then((m) => m.FinesComponent),
      },

      {
        path: 'requests',
        title: 'Employee Requests',
        data: { breadcrumb: 'Requests' },
        loadComponent: () => import('./features/user/requests/requests').then((m) => m.EmployeeRequestsComponent),
      },

      {
        path: 'me',
        title: 'My profile',
        data: { breadcrumb: 'My profile' },
        loadComponent: () => import('./features/user/profile/profile').then((m) => m.Profile),
      },

      {
        path: 'settings',
        data: { breadcrumb: 'Settings' },
        children: [
          { path: '', pathMatch: 'full', redirectTo: 'overview' },
          {
            path: 'overview',
            title: 'Overview',
            data: { breadcrumb: 'Overview' },
            canActivate: [capabilityGuard('can_view_all_attendance')],
            loadComponent: () =>
              import('./features/admin/dashboard/dashboard').then((m) => m.AdminDashboard),
          },
          {
            path: 'payroll-templates',
            title: 'Role salary templates',
            data: { breadcrumb: 'Salary Templates' },
            canActivate: [capabilityGuard('can_manage_organization')],
            loadComponent: () =>
              import('./features/admin/payroll/templates/admin-payroll-templates').then((m) => m.AdminPayrollTemplatesComponent),
          },
          {
            path: 'payroll-assignments',
            title: 'Employee payroll',
            data: { breadcrumb: 'Employee Payroll' },
            canActivate: [capabilityGuard('can_manage_organization')],
            loadComponent: () =>
              import('./features/admin/payroll/assignments/admin-payroll-assignments').then((m) => m.AdminPayrollAssignmentComponent),
          },
          {
            path: 'payroll-documents',
            title: 'Payroll documents',
            data: { breadcrumb: 'Payroll Documents' },
            canActivate: [capabilityGuard('can_manage_organization')],
            loadComponent: () =>
              import('./features/admin/payroll/documents/admin-payroll-documents').then((m) => m.AdminPayrollDocumentsComponent),
          },
          {
            path: 'teams',
            title: 'Teams setup',
            data: { breadcrumb: 'Teams setup' },
            canActivate: [capabilityGuard('can_manage_organization')],
            loadComponent: () =>
              import('./features/admin/teams/manage-teams').then((m) => m.ManageTeams),
          },
          {
            path: 'claims-approvals',
            title: 'Claim approvals',
            data: { breadcrumb: 'Claim approvals' },
            canActivate: [capabilityGuard('can_manage_organization')],
            loadComponent: () =>
              import('./features/admin/claims/admin-claims').then((m) => m.AdminClaimsComponent),
          },
          {
            path: 'fines-management',
            title: 'Fines setup',
            data: { breadcrumb: 'Fines setup' },
            canActivate: [capabilityGuard('can_manage_users')],
            loadComponent: () =>
              import('./features/admin/fines/admin-fines').then((m) => m.AdminFinesComponent),
          },
          {
            path: 'incoming-requests',
            title: 'Incoming requests',
            data: { breadcrumb: 'Incoming requests' },
            canActivate: [capabilityGuard('can_manage_organization')],
            loadComponent: () =>
              import('./features/admin/requests/admin-requests').then((m) => m.AdminRequestsComponent),
          },
          {
            path: 'people',
            data: { breadcrumb: 'People' },
            canActivate: [capabilityGuard('can_manage_users')],
            children: [
              {
                path: '',
                title: 'People',
                loadComponent: () =>
                  import('./features/admin/employees/employees').then((m) => m.Employees),
              },
              {
                path: ':id',
                title: 'Edit employee',
                data: { breadcrumb: 'Edit' },
                loadComponent: () =>
                  import('./features/admin/employees/employee-edit').then((m) => m.EmployeeEdit),
              },
            ],
          },
          {
            path: 'organization',
            title: 'Organization profile',
            data: { breadcrumb: 'Organization' },
            canActivate: [capabilityGuard('can_manage_organization')],
            loadComponent: () =>
              import('./features/admin/organization/organization-settings').then(
                (m) => m.OrganizationSettings,
              ),
          },
          {
            path: 'work-policy',
            title: 'Work policy',
            data: { breadcrumb: 'Work policy' },
            canActivate: [capabilityGuard('can_manage_organization')],
            loadComponent: () =>
              import('./features/admin/organization/work-policy').then((m) => m.WorkPolicy),
          },
          {
            path: 'departments',
            title: 'Departments',
            data: { breadcrumb: 'Departments' },
            canActivate: [capabilityGuard('can_manage_organization')],
            loadComponent: () =>
              import('./features/admin/organization/departments').then((m) => m.Departments),
          },
          {
            path: 'leave-insights',
            title: 'Leave insights',
            data: { breadcrumb: 'Leave insights' },
            canActivate: [capabilityGuard('can_view_all_attendance')],
            loadComponent: () =>
              import('./features/admin/leave/dashboard/leave-dashboard').then((m) => m.LeaveDashboard),
          },
          {
            path: 'leave-policy',
            title: 'Leave policy',
            data: { breadcrumb: 'Leave policy' },
            canActivate: [capabilityGuard('can_manage_organization')],
            loadComponent: () =>
              import('./features/admin/leave/configuration/leave-configuration').then(
                (m) => m.LeaveConfiguration,
              ),
          },
          {
            path: 'holidays',
            title: 'Holidays',
            data: { breadcrumb: 'Holidays' },
            canActivate: [capabilityGuard('can_manage_organization')],
            loadComponent: () =>
              import('./features/admin/leave/holidays/holiday-calendar').then((m) => m.HolidayCalendar),
          },
        ],
      },
    ],
  },

  {
    path: '**',
    title: 'Not found',
    loadComponent: () => import('./shared/not-found/not-found').then((m) => m.NotFound),
  },
];
