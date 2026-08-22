import type { Permissions } from '../../core/models/user.model';
import type { IconName } from '../icon/icons';

/**
 * Capability flags the backend already returns on /auth/me. Nav visibility keys
 * off these rather than re-deriving policy from the role in the frontend.
 */
export type Capability = keyof Pick<
  Permissions,
  'can_manage_users' | 'can_manage_organization' | 'can_view_all_attendance' | 'can_approve_attendance'
>;

export interface NavItem {
  label: string;
  path: string;
  icon: IconName;
  /** Hidden unless every listed capability is true. */
  requires?: readonly Capability[];
}

export interface NavSection {
  label: string;
  items: readonly NavItem[];
}

/**
 * One nav for everybody. Admin powers are not a separate panel - they appear as
 * extra items here and as inline actions on the shared pages.
 */
export const NAV: readonly NavSection[] = [
  {
    label: 'Workspace',
    items: [
      { label: 'Employees', path: '/employees', icon: 'people' },
      { label: 'My Team', path: '/teams', icon: 'people' },
      { label: 'Attendance', path: '/attendance', icon: 'clock' },
      { label: 'Time off', path: '/time-off', icon: 'calendar' },
      { label: 'Claims', path: '/claims', icon: 'file' },
      { label: 'Fines', path: '/fines', icon: 'warning' },
      { label: 'Requests', path: '/requests', icon: 'mail' },
      {
        label: 'Approvals',
        path: '/time-off/requests',
        icon: 'check',
        requires: ['can_approve_attendance'],
      },
    ],
  },
  {
    label: 'Administration',
    items: [
      { label: 'Overview', path: '/settings/overview', icon: 'dashboard', requires: ['can_view_all_attendance'] },
      { label: 'Teams setup', path: '/settings/teams', icon: 'people', requires: ['can_manage_organization'] },
      { label: 'Claim approvals', path: '/settings/claims-approvals', icon: 'file', requires: ['can_manage_organization'] },
      { label: 'Fines setup', path: '/settings/fines-management', icon: 'warning', requires: ['can_manage_users'] },
      { label: 'Incoming requests', path: '/settings/incoming-requests', icon: 'mail', requires: ['can_manage_organization'] },
      { label: 'Leave insights', path: '/settings/leave-insights', icon: 'plane', requires: ['can_view_all_attendance'] },
      { label: 'People', path: '/settings/people', icon: 'briefcase', requires: ['can_manage_users'] },
      { label: 'Leave policy', path: '/settings/leave-policy', icon: 'settings', requires: ['can_manage_organization'] },
      { label: 'Holidays', path: '/settings/holidays', icon: 'calendar', requires: ['can_manage_organization'] },
      { label: 'Departments', path: '/settings/departments', icon: 'filter', requires: ['can_manage_organization'] },
      { label: 'Work policy', path: '/settings/work-policy', icon: 'clock', requires: ['can_manage_organization'] },
      { label: 'Organization', path: '/settings/organization', icon: 'building', requires: ['can_manage_organization'] },
    ],
  },
];

/**
 * Pure predicate, deliberately NOT a method on `Auth` - it keeps this overhaul
 * out of a service that other work touches.
 *
 * Returns false while `permissions` is still null. That window is real: after a
 * fresh sign-in `startSession()` fires `loadSession()` without awaiting it, so
 * the first frames have no flags. The sidebar renders skeleton rows instead of
 * guessing.
 */
export function isNavItemVisible(item: NavItem, permissions: Permissions | null): boolean {
  if (!item.requires?.length) return true;
  if (!permissions) return false;
  return item.requires.every((capability) => permissions[capability] === true);
}

/** Sections with their items filtered; empty sections are dropped. */
export function visibleNav(permissions: Permissions | null): NavSection[] {
  return NAV.map((section) => ({
    ...section,
    items: section.items.filter((item) => isNavItemVisible(item, permissions)),
  })).filter((section) => section.items.length > 0);
}
