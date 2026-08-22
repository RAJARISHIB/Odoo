import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';

import { EmployeeRequest, RequestType } from '../../../core/models/claims.model';
import { ClaimsService } from '../../../core/services/claims';
import { Toast } from '../../../core/services/toast';
import { Icon } from '../../../shared/icon/icon';

@Component({
  selector: 'app-admin-requests',
  standalone: true,
  imports: [ReactiveFormsModule, DatePipe, Icon],
  templateUrl: './admin-requests.html',
  styleUrl: './admin-requests.scss',
})
export class AdminRequestsComponent implements OnInit {
  private readonly claimsService = inject(ClaimsService);
  private readonly toast = inject(Toast);
  private readonly fb = inject(FormBuilder);

  protected readonly requests = signal<EmployeeRequest[]>([]);
  protected readonly loading = signal(true);
  protected readonly statusFilter = signal<string>('PENDING');
  protected readonly typeFilter = signal<string>('ALL');

  protected readonly selectedRequest = signal<EmployeeRequest | null>(null);
  protected readonly showApproveModal = signal(false);
  protected readonly showRejectModal = signal(false);

  protected readonly rejectForm = this.fb.nonNullable.group({
    rejection_reason: [''],
  });

  ngOnInit() {
    this.loadRequests();
  }

  protected loadRequests() {
    this.loading.set(true);
    const status = this.statusFilter() === 'ALL' ? undefined : this.statusFilter();
    const requestType = this.typeFilter() === 'ALL' ? undefined : this.typeFilter();

    this.claimsService.getAdminRequests(status, requestType).subscribe({
      next: (page) => {
        this.requests.set(page.items);
        this.loading.set(false);
      },
      error: (err) => {
        this.toast.error(err.message || 'Failed to load employee requests');
        this.loading.set(false);
      },
    });
  }

  protected onStatusFilterChange(status: string) {
    this.statusFilter.set(status);
    this.loadRequests();
  }

  protected onTypeFilterChange(type: string) {
    this.typeFilter.set(type);
    this.loadRequests();
  }

  protected openApproveModal(req: EmployeeRequest) {
    this.selectedRequest.set(req);
    this.showApproveModal.set(true);
  }

  protected openRejectModal(req: EmployeeRequest) {
    this.selectedRequest.set(req);
    this.rejectForm.reset({ rejection_reason: '' });
    this.showRejectModal.set(true);
  }

  protected confirmApprove() {
    const req = this.selectedRequest();
    if (!req) return;

    this.claimsService.approveRequest(req.id).subscribe({
      next: () => {
        this.toast.success('Employee request approved.');
        this.showApproveModal.set(false);
        this.loadRequests();
      },
      error: (err) => this.toast.error(err.message || 'Failed to approve request'),
    });
  }

  protected confirmReject() {
    const req = this.selectedRequest();
    if (!req) return;

    const reason = this.rejectForm.getRawValue().rejection_reason;
    this.claimsService.rejectRequest(req.id, reason).subscribe({
      next: () => {
        this.toast.success('Employee request rejected.');
        this.showRejectModal.set(false);
        this.loadRequests();
      },
      error: (err) => this.toast.error(err.message || 'Failed to reject request'),
    });
  }

  protected downloadAttachment(req: EmployeeRequest) {
    if (!req.has_attachment) return;
    this.claimsService.downloadRequestAttachment(req.id).subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = req.attachment_original_name || `attachment_${req.id}`;
        a.click();
        window.URL.revokeObjectURL(url);
      },
      error: () => this.toast.error('Failed to download attachment.'),
    });
  }

  protected getLabelForType(type: RequestType): string {
    switch (type) {
      case 'id_card': return 'ID Card';
      case 'laptop': return 'Laptop';
      case 'other': return 'Other';
      default: return type;
    }
  }
}
