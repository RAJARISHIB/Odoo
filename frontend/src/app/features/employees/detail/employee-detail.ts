import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DatePipe, DecimalPipe } from '@angular/common';

import { Attendance as AttendanceApi } from '../../../core/services/attendance';
import { AttendanceSummary } from '../../../core/models/attendance.model';
import { Auth } from '../../../core/services/auth';
import { Department, User } from '../../../core/models/user.model';
import { Icon } from '../../../shared/icon/icon';
import { Organizations, Users } from '../../../core/services/users';

/**
 * One employee, read only.
 *
 * The wireframe is explicit: opening a card shows the person in view-only mode.
 * Editing your own details lives at /me; editing somebody else's is an admin
 * action under /settings/people. Nothing on this page is a form.
 *
 * `id` is bound straight from the route parameter by `withComponentInputBinding()`.
 */
@Component({
  selector: 'app-employee-detail',
  imports: [RouterLink, DatePipe, DecimalPipe, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './employee-detail.html',
  styleUrl: './employee-detail.scss',
})
export class EmployeeDetail {
  readonly id = input.required<string>();

  private readonly users = inject(Users);
  private readonly organizations = inject(Organizations);
  private readonly attendance = inject(AttendanceApi);
  protected readonly auth = inject(Auth);

  protected readonly person = signal<User | null>(null);
  protected readonly summary = signal<AttendanceSummary | null>(null);
  protected readonly departments = signal<Department[]>([]);
  protected readonly loading = signal(true);
  protected readonly notFound = signal(false);

  protected readonly canManage = computed(() => this.auth.permissions()?.can_manage_users === true);
  protected readonly canSeeAttendance = computed(
    () => this.auth.permissions()?.can_view_all_attendance === true,
  );
  protected readonly isSelf = computed(() => this.auth.user()?.id === this.person()?.id);

  protected readonly initials = computed(() => {
    const p = this.person();
    if (!p) return '?';
    return `${p.first_name?.[0] ?? ''}${p.last_name?.[0] ?? ''}`.toUpperCase() || 'U';
  });

  protected readonly departmentName = computed(() => {
    const id = this.person()?.department_id;
    if (!id) return null;
    return this.departments().find((d) => d.id === id)?.name ?? null;
  });

  /** Present / late / absent counts, in a fixed order for the summary strip. */
  protected readonly counts = computed(() => {
    const c = this.summary()?.counts;
    if (!c) return [];
    return [
      { key: 'present', label: 'Present', value: c.present ?? 0, tone: 'success' },
      { key: 'late', label: 'Late', value: c.late ?? 0, tone: 'warning' },
      { key: 'absent', label: 'Absent', value: c.absent ?? 0, tone: 'danger' },
      { key: 'on_leave', label: 'On leave', value: c.on_leave ?? 0, tone: 'info' },
    ];
  });

  constructor() {
    this.organizations.departments({ active_only: true, page_size: 100 }).subscribe({
      next: (page) => this.departments.set(page.items),
      error: () => this.departments.set([]),
    });

    effect(() => {
      const id = this.id();
      if (!id) return;
      this.loadPerson(id);
      this.loadSummary(id);
    });
  }

  private loadPerson(id: string): void {
    this.loading.set(true);
    this.notFound.set(false);

    this.users.get(id).subscribe({
      next: (person) => {
        this.person.set(person);
        this.loading.set(false);
      },
      error: () => {
        this.notFound.set(true);
        this.loading.set(false);
      },
    });
  }

  private loadSummary(id: string): void {
    this.summary.set(null);
    if (!this.canSeeAttendance()) return;

    const to = new Date();
    const from = new Date(to.getTime() - 29 * 86400000);

    this.attendance
      .adminUserSummary(id, {
        date_from: from.toISOString().slice(0, 10),
        date_to: to.toISOString().slice(0, 10),
      })
      .subscribe({
        next: (summary) => this.summary.set(summary),
        error: () => this.summary.set(null),
      });
  }
}
