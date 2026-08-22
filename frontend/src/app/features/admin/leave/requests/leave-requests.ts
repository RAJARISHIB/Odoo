import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { EMPTY_PAGE_META, PageMeta } from '../../../../core/models/api.model';
import {
  LEAVE_STATUS_LABELS,
  LeaveRequest,
  LeaveStatus,
  LeaveType,
} from '../../../../core/models/leaves.model';
import { Leaves } from '../../../../core/services/leaves';
import { Realtime } from '../../../../core/services/realtime';
import { Toast } from '../../../../core/services/toast';

/**
 * Admin leave requests: every employee's requests, with approve/reject.
 *
 * Approve lets the admin optionally tag which configured leave type this
 * request should be attributed to (the employee's own submission flow does
 * not collect one), so the dashboard can build a per-type utilization picture
 * without ever having touched the employee calendar.
 */
@Component({
  selector: 'app-leave-requests',
  imports: [ReactiveFormsModule, DatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './leave-requests.html',
  styleUrl: './leave-requests.scss',
})
export class LeaveRequests {
  private readonly leaves = inject(Leaves);
  private readonly realtime = inject(Realtime);
  private readonly toast = inject(Toast);
  private readonly fb = inject(FormBuilder);

  protected readonly statusLabels = LEAVE_STATUS_LABELS;
  protected readonly statuses = Object.keys(LEAVE_STATUS_LABELS) as LeaveStatus[];

  protected readonly rows = signal<LeaveRequest[]>([]);
  protected readonly meta = signal<PageMeta>(EMPTY_PAGE_META);
  protected readonly types = signal<LeaveType[]>([]);
  protected readonly loading = signal(false);
  /** Leave type picked per pending row before approving - keyed by request id. */
  protected readonly approveTypeChoice = signal<Record<string, string>>({});

  protected readonly filters = this.fb.nonNullable.group({
    status: [''],
    leave_type_id: [''],
    search: [''],
  });

  constructor() {
    this.load();
    this.leaves.types({ active_only: 'false' }).subscribe((types) => this.types.set(types));

    this.realtime
      .onAny(['leave.request_created', 'leave.request_updated'])
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.load(this.meta().page));
  }

  protected load(page = 1): void {
    this.loading.set(true);
    this.leaves
      .adminRequests({ page, page_size: this.meta().page_size, ...this.filters.getRawValue() })
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
    this.filters.reset({ status: '', leave_type_id: '', search: '' });
    this.load(1);
  }

  protected goToPage(page: number): void {
    if (page < 1 || page > this.meta().total_pages) return;
    this.load(page);
  }

  protected setApproveType(requestId: string, typeId: string): void {
    this.approveTypeChoice.update((map) => ({ ...map, [requestId]: typeId }));
  }

  protected approve(request: LeaveRequest): void {
    if (!confirm(`Approve ${request.total_days} day(s) of leave?`)) return;
    const typeId = this.approveTypeChoice()[request.id] || undefined;
    this.leaves.approveRequest(request.id, typeId).subscribe(() => {
      this.toast.success('Leave request approved.');
      this.load(this.meta().page);
    });
  }

  protected reject(request: LeaveRequest): void {
    const comment = prompt('Reason for rejecting this request (optional):');
    if (comment === null) return;
    this.leaves.rejectRequest(request.id, comment).subscribe(() => {
      this.toast.success('Leave request rejected.');
      this.load(this.meta().page);
    });
  }
}
