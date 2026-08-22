import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ExpenseClaim, ExpenseType } from '../../../core/models/claims.model';
import { ClaimsService } from '../../../core/services/claims';
import { Toast } from '../../../core/services/toast';
import { Icon } from '../../../shared/icon/icon';

@Component({
  selector: 'app-claims',
  standalone: true,
  imports: [ReactiveFormsModule, CurrencyPipe, DatePipe, Icon],
  templateUrl: './claims.html',
  styleUrl: './claims.scss',
})
export class ClaimsComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly claimsService = inject(ClaimsService);
  private readonly toast = inject(Toast);

  protected readonly claims = signal<ExpenseClaim[]>([]);
  protected readonly loading = signal(true);
  protected readonly showNewClaimModal = signal(false);
  protected selectedFile: File | null = null;

  protected readonly expenseTypes: ExpenseType[] = [
    'Travel',
    'Food',
    'Accommodation',
    'Transportation',
    'Other',
  ];

  protected readonly claimForm = this.fb.nonNullable.group({
    expense_type: ['Travel' as ExpenseType, [Validators.required]],
    other_type_description: [''],
    amount: [0, [Validators.required, Validators.min(0.01)]],
    expense_date: [new Date().toISOString().substring(0, 10), [Validators.required]],
    description: ['', [Validators.required, Validators.maxLength(500)]],
  });

  ngOnInit() {
    this.loadClaims();
  }

  protected loadClaims() {
    this.loading.set(true);
    this.claimsService.getEmployeeClaims().subscribe({
      next: (page) => {
        this.claims.set(page.items);
        this.loading.set(false);
      },
      error: (err) => {
        this.toast.error(err.message || 'Failed to load expense claims');
        this.loading.set(false);
      },
    });
  }

  protected openNewClaimModal() {
    this.claimForm.reset({
      expense_type: 'Travel',
      other_type_description: '',
      amount: 0,
      expense_date: new Date().toISOString().substring(0, 10),
      description: '',
    });
    this.selectedFile = null;
    this.showNewClaimModal.set(true);
  }

  protected onFileSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      this.selectedFile = input.files[0];
    }
  }

  protected submitClaim() {
    if (this.claimForm.invalid) return;

    const val = this.claimForm.getRawValue();
    if (val.expense_type === 'Other' && !val.other_type_description.trim()) {
      this.toast.error('Please provide a description for Other expense type.');
      return;
    }

    const formData = new FormData();
    formData.append('expense_type', val.expense_type);
    formData.append('other_type_description', val.other_type_description);
    formData.append('amount', String(val.amount));
    formData.append('expense_date', val.expense_date);
    formData.append('description', val.description);

    if (this.selectedFile) {
      formData.append('receipt', this.selectedFile);
    }

    this.claimsService.createClaim(formData).subscribe({
      next: () => {
        this.toast.success('Expense claim submitted successfully.');
        this.showNewClaimModal.set(false);
        this.loadClaims();
      },
      error: (err) => this.toast.error(err.message || 'Failed to submit expense claim'),
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
