import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { ApiErrorBody } from '../../../../core/models/api.model';
import {
  EmployeeLeaveBalanceRow,
  EmployeeLeaveSummary,
  LeaveDashboardSummary,
  LeaveType,
} from '../../../../core/models/leaves.model';
import { Leaves } from '../../../../core/services/leaves';
import { Realtime } from '../../../../core/services/realtime';
import { Toast } from '../../../../core/services/toast';

/** Admin leave dashboard: org-wide utilization, drillable into one employee. */
@Component({
  selector: 'app-leave-dashboard',
  imports: [ReactiveFormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './leave-dashboard.html',
})
export class LeaveDashboard {
  private readonly leaves = inject(Leaves);
  private readonly realtime = inject(Realtime);
  private readonly toast = inject(Toast);
  private readonly fb = inject(FormBuilder);

  protected readonly summary = signal<LeaveDashboardSummary | null>(null);
  protected readonly types = signal<LeaveType[]>([]);
  protected readonly loading = signal(false);

  protected readonly expandedUserId = signal<string | null>(null);
  protected readonly employeeSummary = signal<EmployeeLeaveSummary | null>(null);
  protected readonly loadingEmployee = signal(false);

  protected readonly adjustSaving = signal(false);
  protected readonly adjustErrors = signal<Record<string, string>>({});

  protected readonly filters = this.fb.nonNullable.group({
    year: [new Date().getFullYear(), Validators.required],
    leave_type_id: [''],
    search: [''],
  });

  protected readonly adjustForm = this.fb.nonNullable.group({
    leave_type_id: ['', Validators.required],
    amount: [0, Validators.required],
    reason: ['', Validators.required],
  });

  constructor() {
    this.load();
    this.leaves.types({ active_only: 'false' }).subscribe((types) => this.types.set(types));

    this.realtime
      .onAny(['leave.request_updated', 'leave.allocation_updated', 'leave.balance_updated'])
      .pipe(takeUntilDestroyed())
      .subscribe(() => {
        this.load();
        if (this.expandedUserId()) this.loadEmployee(this.expandedUserId()!);
      });
  }

  protected load(): void {
    this.loading.set(true);
    this.leaves.dashboard(this.filters.getRawValue()).subscribe({
      next: (summary) => {
        this.summary.set(summary);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  protected applyFilters(): void {
    this.load();
  }

  protected resetFilters(): void {
    this.filters.reset({ year: new Date().getFullYear(), leave_type_id: '', search: '' });
    this.load();
  }

  protected toggleRow(row: EmployeeLeaveBalanceRow): void {
    if (this.expandedUserId() === row.user_id) {
      this.expandedUserId.set(null);
      this.employeeSummary.set(null);
      return;
    }
    this.expandedUserId.set(row.user_id);
    this.loadEmployee(row.user_id);
  }

  private loadEmployee(userId: string): void {
    this.loadingEmployee.set(true);
    this.leaves.employeeSummary(userId, { year: this.filters.getRawValue().year }).subscribe({
      next: (summary) => {
        this.employeeSummary.set(summary);
        this.loadingEmployee.set(false);
      },
      error: () => this.loadingEmployee.set(false),
    });
  }

  protected saveAdjustment(): void {
    const userId = this.expandedUserId();
    if (!userId || this.adjustForm.invalid || this.adjustSaving()) {
      this.adjustForm.markAllAsTouched();
      return;
    }

    this.adjustSaving.set(true);
    this.adjustErrors.set({});
    this.leaves.createAdjustment({ user_id: userId, ...this.adjustForm.getRawValue() }).subscribe({
      next: () => {
        this.adjustSaving.set(false);
        this.toast.success('Balance adjustment recorded.');
        this.adjustForm.reset({ amount: 0 });
        this.load();
        this.loadEmployee(userId);
      },
      error: (error: ApiErrorBody) => {
        this.adjustSaving.set(false);
        this.adjustErrors.set(error.details ?? { amount: error.message });
      },
    });
  }

  protected meterClass(pct: number): string {
    if (pct >= 100) return 'danger';
    if (pct >= 75) return 'warning';
    return '';
  }
}
