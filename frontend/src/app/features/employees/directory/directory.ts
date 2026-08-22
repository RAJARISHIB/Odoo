import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { EMPTY_PAGE_META, PageMeta } from '../../../core/models/api.model';
import { Attendance as AttendanceApi } from '../../../core/services/attendance';
import { Auth } from '../../../core/services/auth';
import { Department, Role, User } from '../../../core/models/user.model';
import { Icon } from '../../../shared/icon/icon';
import type { IconName } from '../../../shared/icon/icons';
import { Realtime } from '../../../core/services/realtime';
import { Organizations, Users } from '../../../core/services/users';

/** How a card's corner marker reads. */
export type PresenceKind = 'in' | 'out' | 'leave' | 'absent' | 'unknown';

export interface Presence {
  kind: PresenceKind;
  label: string;
  icon: IconName | null;
}

const PRESENCE: Record<PresenceKind, Presence> = {
  in: { kind: 'in', label: 'In office', icon: null },
  out: { kind: 'out', label: 'Checked out', icon: null },
  leave: { kind: 'leave', label: 'On leave', icon: 'plane' },
  absent: { kind: 'absent', label: 'Absent', icon: null },
  unknown: { kind: 'unknown', label: 'Not marked', icon: null },
};

/**
 * Employee directory - the landing page for everybody.
 *
 * Cards carry the wireframe's corner status marker: green in office, an
 * aeroplane on leave, amber absent.
 *
 * Presence needs today's attendance for the whole organization, which the API
 * only serves to `can_view_all_attendance` roles. Without that flag the cards
 * render without a marker rather than showing something invented.
 */
@Component({
  selector: 'app-directory',
  imports: [ReactiveFormsModule, RouterLink, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './directory.html',
  styleUrl: './directory.scss',
})
export class Directory {
  private readonly users = inject(Users);
  private readonly organizations = inject(Organizations);
  private readonly attendance = inject(AttendanceApi);
  private readonly realtime = inject(Realtime);
  private readonly fb = inject(FormBuilder);
  protected readonly auth = inject(Auth);

  protected readonly rows = signal<User[]>([]);
  protected readonly meta = signal<PageMeta>({ ...EMPTY_PAGE_META, page_size: 24 });
  protected readonly loading = signal(true);
  protected readonly departments = signal<Department[]>([]);
  private readonly presenceByUser = signal<Map<string, Presence>>(new Map());

  protected readonly canManage = computed(() => this.auth.permissions()?.can_manage_users === true);
  protected readonly canSeePresence = computed(
    () => this.auth.permissions()?.can_view_all_attendance === true,
  );

  protected readonly inOfficeCount = computed(
    () => [...this.presenceByUser().values()].filter((p) => p.kind === 'in').length,
  );

  protected readonly roles: { value: Role | ''; label: string }[] = [
    { value: '', label: 'All roles' },
    { value: 'employee', label: 'Employee' },
    { value: 'manager', label: 'Manager' },
    { value: 'hr', label: 'HR' },
    { value: 'admin', label: 'Admin' },
    { value: 'super_admin', label: 'Super admin' },
  ];

  protected readonly filters = this.fb.nonNullable.group({
    search: [''],
    department_id: [''],
    role: [''],
  });

  protected readonly skeletons = Array.from({ length: 8 }, (_, i) => i);

  constructor() {
    this.load();
    this.loadDepartments();
    this.loadPresence();

    this.realtime
      .onAny(['user.created', 'user.updated', 'user.status_changed'])
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.load(this.meta().page));

    this.realtime
      .onAny(['attendance.checked_in', 'attendance.checked_out', 'attendance.updated'])
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.loadPresence());
  }

  protected load(page = 1): void {
    this.loading.set(true);
    const { search, department_id, role } = this.filters.getRawValue();

    this.users
      .list({ page, page_size: this.meta().page_size, search, department_id, role, status: 'active' })
      .subscribe({
        next: (result) => {
          this.rows.set(result.items);
          this.meta.set(result.meta);
          this.loading.set(false);
        },
        error: () => this.loading.set(false),
      });
  }

  protected applyFilters(): void {
    this.load(1);
  }

  protected resetFilters(): void {
    this.filters.reset({ search: '', department_id: '', role: '' });
    this.load(1);
  }

  protected goToPage(page: number): void {
    if (page < 1 || page > this.meta().total_pages) return;
    this.load(page);
  }

  protected presenceFor(user: User): Presence | null {
    if (!this.canSeePresence()) return null;
    return this.presenceByUser().get(user.id) ?? PRESENCE.unknown;
  }

  protected initials(user: User): string {
    return `${user.first_name?.[0] ?? ''}${user.last_name?.[0] ?? ''}`.toUpperCase() || 'U';
  }

  /** Stable per user, so a face keeps its colour between renders and pages. */
  protected tint(user: User): string {
    let hash = 0;
    for (const ch of user.id) hash = (hash + ch.charCodeAt(0)) % 4;
    return `tint-${hash + 1}`;
  }

  protected departmentName(user: User): string {
    if (!user.department_id) return 'No department';
    return this.departments().find((d) => d.id === user.department_id)?.name ?? 'Department';
  }

  private loadDepartments(): void {
    this.organizations.departments({ active_only: true, page_size: 100 }).subscribe({
      next: (page) => this.departments.set(page.items),
      error: () => this.departments.set([]),
    });
  }

  private loadPresence(): void {
    if (!this.canSeePresence()) return;

    const today = new Date().toISOString().slice(0, 10);
    this.attendance.adminList({ date_from: today, date_to: today, page_size: 200 }).subscribe({
      next: (page) => {
        const map = new Map<string, Presence>();
        for (const record of page.items) {
          map.set(record.user_id, resolvePresence(record.status, record.is_checked_in));
        }
        this.presenceByUser.set(map);
      },
      error: () => this.presenceByUser.set(new Map()),
    });
  }
}

function resolvePresence(status: string, checkedIn: boolean): Presence {
  if (status === 'on_leave' || status === 'holiday') return PRESENCE.leave;
  if (status === 'absent') return PRESENCE.absent;
  if (checkedIn) return PRESENCE.in;
  if (status === 'present' || status === 'late' || status === 'half_day') return PRESENCE.out;
  return PRESENCE.unknown;
}
