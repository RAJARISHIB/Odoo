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
import { Icon } from '../../../../shared/icon/icon';

/**
 * Admin leave requests: every employee's requests, with approve/reject modal workflows.
 */
@Component({
  selector: 'app-leave-requests',
  imports: [ReactiveFormsModule, DatePipe, Icon],
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

  // Modal states
  protected readonly selectedApproveRequest = signal<LeaveRequest | null>(null);
  protected readonly selectedRejectRequest = signal<LeaveRequest | null>(null);

  protected readonly approveForm = this.fb.nonNullable.group({
    leave_type_id: [''],
  });

  protected readonly rejectForm = this.fb.nonNullable.group({
    comment: [''],
  });

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

  protected openApproveModal(request: LeaveRequest): void {
    this.selectedApproveRequest.set(request);
    this.approveForm.patchValue({
      leave_type_id: request.leave_type_id || '',
    });
  }

  protected openRejectModal(request: LeaveRequest): void {
    this.selectedRejectRequest.set(request);
    this.rejectForm.reset({ comment: '' });
  }

  protected closeModals(): void {
    this.selectedApproveRequest.set(null);
    this.selectedRejectRequest.set(null);
  }

  protected confirmApprove(): void {
    const request = this.selectedApproveRequest();
    if (!request) return;

    const typeId = this.approveForm.controls.leave_type_id.value || undefined;
    this.leaves.approveRequest(request.id, typeId).subscribe({
      next: () => {
        this.toast.success('Leave request approved successfully.');
        this.closeModals();
        this.load(this.meta().page);
      },
      error: () => {
        // toast handled by error interceptor
      },
    });
  }

  protected confirmReject(): void {
    const request = this.selectedRejectRequest();
    if (!request) return;

    const comment = this.rejectForm.controls.comment.value.trim() || undefined;
    this.leaves.rejectRequest(request.id, comment).subscribe({
      next: () => {
        this.toast.success('Leave request rejected.');
        this.closeModals();
        this.load(this.meta().page);
      },
      error: () => {
        // toast handled by error interceptor
      },
    });
  }
}
