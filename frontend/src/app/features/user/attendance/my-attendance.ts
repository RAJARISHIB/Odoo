import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';

import {
  ATTENDANCE_STATUS_LABELS,
  Attendance as AttendanceRecord,
  AttendanceStatus,
  AttendanceSummary,
} from '../../../core/models/attendance.model';
import { Attendance } from '../../../core/services/attendance';
import { EMPTY_PAGE_META, PageMeta } from '../../../core/models/api.model';

/** The signed-in employee's own attendance history and totals. */
@Component({
  selector: 'app-my-attendance',
  imports: [ReactiveFormsModule, DatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './my-attendance.html',
})
export class MyAttendance {
  private readonly attendance = inject(Attendance);
  private readonly fb = inject(FormBuilder);

  protected readonly statusLabels = ATTENDANCE_STATUS_LABELS;
  protected readonly statuses = Object.keys(ATTENDANCE_STATUS_LABELS) as AttendanceStatus[];

  protected readonly rows = signal<AttendanceRecord[]>([]);
  protected readonly meta = signal<PageMeta>(EMPTY_PAGE_META);
  protected readonly summary = signal<AttendanceSummary | null>(null);
  protected readonly loading = signal(false);

  protected readonly filters = this.fb.nonNullable.group({
    date_from: [''],
    date_to: [''],
    status: [''],
  });

  constructor() {
    this.load();
    this.loadSummary();
  }

  protected load(page = 1): void {
    this.loading.set(true);
    this.attendance
      .myRecords({ page, page_size: this.meta().page_size, ...this.filters.getRawValue() })
      .subscribe({
        next: (result) => {
          this.rows.set(result.items);
          this.meta.set(result.meta);
          this.loading.set(false);
        },
        error: () => this.loading.set(false),
      });
  }

  private loadSummary(): void {
    const { date_from, date_to } = this.filters.getRawValue();
    this.attendance.mySummary({ date_from, date_to }).subscribe((summary) => this.summary.set(summary));
  }

  protected applyFilters(): void {
    this.load(1);
    this.loadSummary();
  }

  protected resetFilters(): void {
    this.filters.reset({ date_from: '', date_to: '', status: '' });
    this.applyFilters();
  }

  protected goToPage(page: number): void {
    if (page < 1 || page > this.meta().total_pages) return;
    this.load(page);
  }
}
