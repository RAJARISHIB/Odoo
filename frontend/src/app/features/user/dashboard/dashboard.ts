import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { ATTENDANCE_STATUS_LABELS, AttendanceState, AttendanceSummary } from '../../../core/models/attendance.model';
import { ApiErrorBody } from '../../../core/models/api.model';
import { Attendance } from '../../../core/services/attendance';
import { Auth } from '../../../core/services/auth';
import { Realtime } from '../../../core/services/realtime';
import { ServerMessage } from '../../../core/models/realtime.model';
import { Toast } from '../../../core/services/toast';

/** Employee home: the check-in widget, today's sessions and a 30-day summary. */
@Component({
  selector: 'app-user-dashboard',
  imports: [DatePipe, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss',
})
export class UserDashboard {
  private readonly attendance = inject(Attendance);
  private readonly toast = inject(Toast);
  private readonly realtime = inject(Realtime);
  protected readonly auth = inject(Auth);

  protected readonly statusLabels = ATTENDANCE_STATUS_LABELS;
  protected readonly today = signal<AttendanceState | null>(null);
  protected readonly summary = signal<AttendanceSummary | null>(null);
  protected readonly busy = signal(false);
  protected readonly notifications = signal<ServerMessage[]>([]);

  protected readonly checkedIn = computed(() => this.today()?.is_checked_in ?? false);

  protected readonly openSince = computed(() => {
    const open = this.today()?.sessions.find((session) => session.is_open);
    return open?.check_in ?? null;
  });

  constructor() {
    this.load();

    // Another device of ours punched, or an admin corrected today's record.
    this.realtime
      .onAny(['attendance.checked_in', 'attendance.checked_out', 'attendance.updated'])
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.loadStatus());

    this.realtime
      .onAny(['notification', 'system.announcement'])
      .pipe(takeUntilDestroyed())
      .subscribe((message) => {
        this.notifications.update((items) => [message, ...items].slice(0, 5));
      });
  }

  private load(): void {
    this.loadStatus();
    this.attendance.mySummary().subscribe((summary) => this.summary.set(summary));
  }

  private loadStatus(): void {
    this.attendance.status().subscribe((state) => this.today.set(state));
  }

  protected checkIn(): void {
    if (this.busy()) return;
    this.busy.set(true);
    this.attendance.checkIn().subscribe({
      next: () => {
        this.busy.set(false);
        this.toast.success('Checked in. Have a good one.');
        this.loadStatus();
      },
      error: (error: ApiErrorBody) => {
        this.busy.set(false);
        this.toast.error(error.message);
        this.loadStatus();
      },
    });
  }

  protected checkOut(): void {
    if (this.busy()) return;
    this.busy.set(true);
    this.attendance.checkOut().subscribe({
      next: (record) => {
        this.busy.set(false);
        this.toast.success(`Checked out after ${record.total_hours} h.`);
        this.loadStatus();
        this.attendance.mySummary().subscribe((summary) => this.summary.set(summary));
      },
      error: (error: ApiErrorBody) => {
        this.busy.set(false);
        this.toast.error(error.message);
        this.loadStatus();
      },
    });
  }

  protected notificationText(message: ServerMessage): string {
    const payload = message.payload as { title?: string; body?: string };
    return payload.title ? `${payload.title} — ${payload.body ?? ''}` : (payload.body ?? 'Update');
  }
}
