import { Injectable, inject } from '@angular/core';
import { Observable, forkJoin, of } from 'rxjs';
import { catchError, map } from 'rxjs/operators';

import { Auth } from './auth';
import { Leaves } from './leaves';
import { Users } from './users';
import { Capability } from '../../shared/shell/nav-config';
import { LEAVE_STATUS_LABELS } from '../models/leaves.model';
import type { IconName } from '../../shared/icon/icons';

export type SearchGroup = 'go' | 'people' | 'leave' | 'holidays';

export const GROUP_LABELS: Record<SearchGroup, string> = {
  go: 'Go to',
  people: 'People',
  leave: 'Leave requests',
  holidays: 'Holidays',
};

/** The order groups appear in the results list. */
export const GROUP_ORDER: SearchGroup[] = ['go', 'people', 'leave', 'holidays'];

export interface SearchHit {
  id: string;
  group: SearchGroup;
  icon: IconName;
  title: string;
  subtitle: string;
  link: string;
  queryParams?: Record<string, string>;
}

interface Destination {
  title: string;
  subtitle: string;
  icon: IconName;
  link: string;
  queryParams?: Record<string, string>;
  requires?: Capability;
  /** Extra words that should match this destination but are not in its title. */
  keywords: string;
}

/**
 * Every screen the search can jump to, with the words people actually use for
 * it. "Apply for leave" is the entry someone reaches for when they type
 * "holiday", "vacation" or "time off", none of which appear in its title —
 * hence the explicit keyword list rather than matching on the label alone.
 */
const DESTINATIONS: Destination[] = [
  {
    title: 'Employees',
    subtitle: 'Browse the directory',
    icon: 'people',
    link: '/employees',
    keywords: 'directory staff team colleagues who people',
  },
  {
    title: 'Apply for leave',
    subtitle: 'Time off · request days',
    icon: 'plane',
    link: '/time-off',
    keywords: 'leave holiday vacation time off absence apply request pto sick',
  },
  {
    title: 'My attendance',
    subtitle: 'Your check-ins and hours',
    icon: 'clock',
    link: '/attendance',
    keywords: 'attendance hours punch check in out timesheet my',
  },
  {
    title: 'My profile',
    subtitle: 'Your details and password',
    icon: 'profile',
    link: '/me',
    keywords: 'profile account password me settings personal',
  },
  {
    title: 'Leave approvals',
    subtitle: 'Approve or reject requests',
    icon: 'check',
    link: '/time-off/requests',
    requires: 'can_approve_attendance',
    keywords: 'approve approvals reject pending leave requests review',
  },
  {
    title: 'Team attendance',
    subtitle: 'Everyone’s records',
    icon: 'clock',
    link: '/attendance/team',
    requires: 'can_view_all_attendance',
    keywords: 'attendance team board records everyone report',
  },
  {
    title: 'Overview',
    subtitle: 'Today at a glance',
    icon: 'dashboard',
    link: '/settings/overview',
    requires: 'can_view_all_attendance',
    keywords: 'dashboard overview today summary stats admin',
  },
  {
    title: 'Leave insights',
    subtitle: 'Utilisation by employee',
    icon: 'plane',
    link: '/settings/leave-insights',
    requires: 'can_view_all_attendance',
    keywords: 'leave insights balance utilisation utilization report allocation',
  },
  {
    title: 'People',
    subtitle: 'Manage roles and access',
    icon: 'briefcase',
    link: '/settings/people',
    requires: 'can_manage_users',
    keywords: 'manage users roles access accounts admin staff employees',
  },
  {
    title: 'Add an employee',
    subtitle: 'Create a new account',
    icon: 'plus',
    link: '/settings/people',
    queryParams: { new: '1' },
    requires: 'can_manage_users',
    keywords: 'add new create employee user invite onboard hire',
  },
  {
    title: 'Leave policy',
    subtitle: 'Leave types and accrual rules',
    icon: 'settings',
    link: '/settings/leave-policy',
    requires: 'can_manage_organization',
    keywords: 'leave policy types allocation accrual carry forward configuration',
  },
  {
    title: 'Holidays',
    subtitle: 'The company holiday calendar',
    icon: 'calendar',
    link: '/settings/holidays',
    requires: 'can_manage_organization',
    keywords: 'holidays calendar public festival government company',
  },
  {
    title: 'Departments',
    subtitle: 'Group people for reporting',
    icon: 'filter',
    link: '/settings/departments',
    requires: 'can_manage_organization',
    keywords: 'departments teams groups division org structure',
  },
  {
    title: 'Work policy',
    subtitle: 'Shift, grace period and day lengths',
    icon: 'clock',
    link: '/settings/work-policy',
    requires: 'can_manage_organization',
    keywords: 'work policy shift hours grace late half day working days',
  },
  {
    title: 'Organization profile',
    subtitle: 'Company name and contact details',
    icon: 'building',
    link: '/settings/organization',
    requires: 'can_manage_organization',
    keywords: 'organization company profile name address timezone',
  },
];

/**
 * Backs the topbar's global search.
 *
 * Three of the four groups are live queries and one is a static list of
 * destinations. They are combined with `forkJoin`, and every remote source
 * carries its own `catchError` returning an empty array — one endpoint being
 * unreachable should cost you that group's results, not the whole dropdown.
 *
 * Teams are deliberately absent. The `teams/*` endpoints exist and return real
 * data, but nothing in the app renders a team, so a team hit would have
 * nowhere to navigate to. Add them here once a Teams screen exists.
 */
@Injectable({ providedIn: 'root' })
export class Search {
  private readonly users = inject(Users);
  private readonly leaves = inject(Leaves);
  private readonly auth = inject(Auth);

  /** Holidays have no search endpoint, so the year is fetched once and sifted
      in memory. A year of holidays is a few dozen rows at most. */
  private holidayCache: { year: number; rows: { id: string; name: string; date: string; type: string }[] } | null = null;

  query(term: string): Observable<SearchHit[]> {
    const needle = term.trim().toLowerCase();
    if (needle.length < 2) return of([]);

    return forkJoin({
      go: of(this.destinations(needle)),
      people: this.people(needle),
      leave: this.leaveRequests(needle),
      holidays: this.holidays(needle),
    }).pipe(map((groups) => [...groups.go, ...groups.people, ...groups.leave, ...groups.holidays]));
  }

  // -- destinations --------------------------------------------------------
  private destinations(needle: string): SearchHit[] {
    const permissions = this.auth.permissions();

    return DESTINATIONS.filter((destination) => {
      if (destination.requires && !permissions?.[destination.requires]) return false;
      return `${destination.title} ${destination.keywords}`.toLowerCase().includes(needle);
    })
      .slice(0, 5)
      .map((destination) => ({
        id: `go:${destination.link}:${destination.title}`,
        group: 'go' as const,
        icon: destination.icon,
        title: destination.title,
        subtitle: destination.subtitle,
        link: destination.link,
        queryParams: destination.queryParams,
      }));
  }

  // -- people --------------------------------------------------------------
  private people(needle: string): Observable<SearchHit[]> {
    return this.users.list({ search: needle, page_size: 5, status: 'active' }).pipe(
      map((page) =>
        page.items.map((user) => ({
          id: `people:${user.id}`,
          group: 'people' as const,
          icon: 'profile' as IconName,
          title: user.full_name,
          subtitle: [user.designation, user.email].filter(Boolean).join(' · '),
          link: `/employees/${user.id}`,
        })),
      ),
      catchError(() => of([])),
    );
  }

  // -- leave requests ------------------------------------------------------
  private leaveRequests(needle: string): Observable<SearchHit[]> {
    const canApprove = this.auth.permissions()?.can_approve_attendance === true;

    // An approver searches everyone's requests by employee; everybody else
    // searches their own, which the API cannot filter, so it is sifted here.
    const source = canApprove
      ? this.leaves.adminRequests({ search: needle, page_size: 4 })
      : this.leaves.getMyRequests({ page_size: 25 });

    return source.pipe(
      map((page) => {
        const rows = canApprove
          ? page.items
          : page.items.filter((request) =>
              `${request.reason ?? ''} ${request.leave_type_name ?? ''} ${request.status}`
                .toLowerCase()
                .includes(needle),
            );

        return rows.slice(0, 4).map((request) => ({
          id: `leave:${request.id}`,
          group: 'leave' as const,
          icon: 'calendar' as IconName,
          title: canApprove
            ? `${request.employee_info?.name ?? 'Someone'} · ${request.start_date} → ${request.end_date}`
            : `${request.start_date} → ${request.end_date}`,
          subtitle: [
            LEAVE_STATUS_LABELS[request.status],
            request.leave_type_name,
            request.reason,
          ]
            .filter(Boolean)
            .join(' · '),
          link: canApprove ? '/time-off/requests' : '/time-off',
        }));
      }),
      catchError(() => of([])),
    );
  }

  // -- holidays ------------------------------------------------------------
  private holidays(needle: string): Observable<SearchHit[]> {
    const year = new Date().getFullYear();
    const toHits = (rows: { id: string; name: string; date: string; type: string }[]): SearchHit[] =>
      rows
        .filter((holiday) => holiday.name.toLowerCase().includes(needle))
        .slice(0, 4)
        .map((holiday) => ({
          id: `holiday:${holiday.id}`,
          group: 'holidays' as const,
          icon: 'calendar' as IconName,
          title: holiday.name,
          subtitle: `${holiday.date} · ${holiday.type}`,
          // Employees have no holiday admin screen; the calendar shows the
          // same days, so that is where they land.
          link: this.auth.permissions()?.can_manage_organization ? '/settings/holidays' : '/time-off',
        }));

    if (this.holidayCache?.year === year) return of(toHits(this.holidayCache.rows));

    return this.leaves.getHolidays({ start_date: `${year}-01-01`, end_date: `${year}-12-31` }).pipe(
      map((rows) => {
        this.holidayCache = { year, rows };
        return toHits(rows);
      }),
      catchError(() => of([])),
    );
  }
}
