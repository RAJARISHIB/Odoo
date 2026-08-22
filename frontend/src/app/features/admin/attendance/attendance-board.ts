import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import {
  ATTENDANCE_STATUS_LABELS,
  Attendance as AttendanceRecord,
  AttendanceStatus,
  DailyOverview,
} from '../../../core/models/attendance.model';
import { ApiErrorBody, EMPTY_PAGE_META, PageMeta } from '../../../core/models/api.model';
import { Attendance } from '../../../core/services/attendance';
import { Realtime } from '../../../core/services/realtime';
import { Toast } from '../../../core/services/toast';
import { User } from '../../../core/models/user.model';
import { Users } from '../../../core/services/users';

/**
 * Attendance board.
 *
 * Lists records with filters, and updates itself whenever the hub reports a
 * punch instead of polling the API.
 */
@Component({
  selector: 'app-attendance-board',
  imports: [ReactiveFormsModule, DatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './attendance-board.html',
})
export class AttendanceBoard {
  private readonly attendance = inject(Attendance);
  private readonly users = inject(Users);
  private readonly realtime = inject(Realtime);
  private readonly toast = inject(Toast);
  private readonly fb = inject(FormBuilder);

  protected readonly statusLabels = ATTENDANCE_STATUS_LABELS;
  protected readonly statuses = Object.keys(ATTENDANCE_STATUS_LABELS) as AttendanceStatus[];

  protected readonly rows = signal<AttendanceRecord[]>([]);
  protected readonly meta = signal<PageMeta>(EMPTY_PAGE_META);
  protected readonly overview = signal<DailyOverview | null>(null);
  protected readonly employees = signal<User[]>([]);
  protected readonly loading = signal(false);
  protected readonly showEntryForm = signal(false);
  protected readonly saving = signal(false);
  protected readonly formErrors = signal<Record<string, string>>({});

  protected readonly filters = this.fb.nonNullable.group({
    user_id: [''],
    date_from: [''],
    date_to: [''],
    status: [''],
  });

  /** Admin correction for one employee's day. */
  protected readonly entryForm = this.fb.nonNullable.group({
    user_id: ['', Validators.required],
    date: [new Date().toISOString().slice(0, 10), Validators.required],
    check_in: [''],
    check_out: [''],
    status: ['present', Validators.required],
    note: [''],
  });

  constructor() {
    this.load();
    this.loadOverview();
    this.users.list({ page_size: 100 }).subscribe((page) => this.employees.set(page.items));

    this.realtime
      .onAny(['attendance.checked_in', 'attendance.checked_out', 'attendance.updated'])
      .pipe(takeUntilDestroyed())
      .subscribe(() => {
        this.load(this.meta().page);
        this.loadOverview();
      });
  }

  protected load(page = 1): void {
    this.loading.set(true);
    this.attendance
      .adminList({ page, page_size: this.meta().page_size, ...this.filters.getRawValue() })
      .subscribe({
        next: (result) => {
          this.rows.set(result.items);
          this.meta.set(result.meta);
          this.loading.set(false);
        },
        error: () => this.loading.set(false),
      });
  }

  private loadOverview(): void {
    this.attendance.adminOverview().subscribe((overview) => this.overview.set(overview));
  }

  protected applyFilters(): void {
    this.load(1);
  }

  protected resetFilters(): void {
    this.filters.reset({ user_id: '', date_from: '', date_to: '', status: '' });
    this.load(1);
  }

  protected goToPage(page: number): void {
    if (page < 1 || page > this.meta().total_pages) return;
    this.load(page);
  }

  // -- manual entry ------------------------------------------------------
  protected toggleEntryForm(): void {
    this.showEntryForm.update((open) => !open);
    this.formErrors.set({});
  }

  protected saveEntry(): void {
    if (this.entryForm.invalid || this.saving()) {
      this.entryForm.markAllAsTouched();
      return;
    }

    this.saving.set(true);
    const payload = this.entryForm.getRawValue();

    this.attendance
      .adminManualEntry({
        ...payload,
        // `datetime-local` has no zone; treat it as the browser's local time.
        check_in: payload.check_in ? new Date(payload.check_in).toISOString() : undefined,
        check_out: payload.check_out ? new Date(payload.check_out).toISOString() : undefined,
      })
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.toast.success('Attendance recorded.');
          this.showEntryForm.set(false);
          this.load(this.meta().page);
        },
        error: (error: ApiErrorBody) => {
          this.saving.set(false);
          this.formErrors.set(error.details ?? { date: error.message });
        },
      });
  }

  protected remove(record: AttendanceRecord): void {
    if (!confirm('Remove this attendance record?')) return;
    this.attendance.adminRemove(record.id).subscribe(() => {
      this.toast.success('Record removed.');
      this.load(this.meta().page);
    });
  }
}
