import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';

import { ExpenseClaim } from '../../../core/models/claims.model';
import { ClaimsService } from '../../../core/services/claims';
import { Toast } from '../../../core/services/toast';
import { Icon } from '../../../shared/icon/icon';

@Component({
  selector: 'app-admin-claims',
  standalone: true,
  imports: [ReactiveFormsModule, CurrencyPipe, DatePipe, Icon],
  templateUrl: './admin-claims.html',
  styleUrl: './admin-claims.scss',
})
export class AdminClaimsComponent implements OnInit {
  private readonly claimsService = inject(ClaimsService);
  private readonly toast = inject(Toast);
  private readonly fb = inject(FormBuilder);

  protected readonly claims = signal<ExpenseClaim[]>([]);
  protected readonly loading = signal(true);
  protected readonly statusFilter = signal<string>('PENDING');

  protected readonly selectedClaim = signal<ExpenseClaim | null>(null);
  protected readonly showApproveModal = signal(false);
  protected readonly showRejectModal = signal(false);

  protected readonly actionForm = this.fb.nonNullable.group({
    comment: [''],
  });

  ngOnInit() {
    this.loadClaims();
  }

  protected loadClaims() {
    this.loading.set(true);
    const filter = this.statusFilter();
    this.claimsService.getAdminClaims(filter === 'ALL' ? undefined : filter).subscribe({
      next: (page) => {
        this.claims.set(page.items);
        this.loading.set(false);
      },
      error: (err) => {
        this.toast.error(err.message || 'Failed to load claims');
        this.loading.set(false);
      },
    });
  }

  protected onFilterChange(status: string) {
    this.statusFilter.set(status);
    this.loadClaims();
  }

  protected openApproveModal(claim: ExpenseClaim) {
    this.selectedClaim.set(claim);
    this.actionForm.reset({ comment: '' });
    this.showApproveModal.set(true);
  }

  protected openRejectModal(claim: ExpenseClaim) {
    this.selectedClaim.set(claim);
    this.actionForm.reset({ comment: '' });
    this.showRejectModal.set(true);
  }

  protected confirmApprove() {
    const claim = this.selectedClaim();
    if (!claim) return;

    const comment = this.actionForm.getRawValue().comment;
    this.claimsService.approveClaim(claim.id, comment).subscribe({
      next: () => {
        this.toast.success('Expense claim approved.');
        this.showApproveModal.set(false);
        this.loadClaims();
      },
      error: (err) => this.toast.error(err.message || 'Failed to approve claim'),
    });
  }

  protected confirmReject() {
    const claim = this.selectedClaim();
    if (!claim) return;

    const comment = this.actionForm.getRawValue().comment;
    this.claimsService.rejectClaim(claim.id, comment).subscribe({
      next: () => {
        this.toast.success('Expense claim rejected.');
        this.showRejectModal.set(false);
        this.loadClaims();
      },
      error: (err) => this.toast.error(err.message || 'Failed to reject claim'),
    });
  }

  protected downloadReceipt(claim: ExpenseClaim) {
    if (!claim.has_receipt) return;
    this.claimsService.downloadClaimAttachment(claim.id).subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = claim.receipt_original_name || `receipt_${claim.id}`;
        a.click();
        window.URL.revokeObjectURL(url);
      },
      error: () => this.toast.error('Failed to download receipt attachment.'),
    });
  }
}
