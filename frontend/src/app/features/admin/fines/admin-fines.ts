import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { Fine } from '../../../core/models/claims.model';
import { User } from '../../../core/models/user.model';
import { ClaimsService } from '../../../core/services/claims';
import { Toast } from '../../../core/services/toast';
import { Users } from '../../../core/services/users';
import { Icon } from '../../../shared/icon/icon';

@Component({
  selector: 'app-admin-fines',
  standalone: true,
  imports: [ReactiveFormsModule, CurrencyPipe, DatePipe, Icon],
  templateUrl: './admin-fines.html',
  styleUrl: './admin-fines.scss',
})
export class AdminFinesComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly claimsService = inject(ClaimsService);
  private readonly usersService = inject(Users);
  private readonly toast = inject(Toast);

  protected readonly fines = signal<Fine[]>([]);
  protected readonly users = signal<User[]>([]);
  protected readonly loading = signal(true);
  protected readonly showApplyFineModal = signal(false);

  protected readonly fineForm = this.fb.nonNullable.group({
    employee_id: ['', [Validators.required]],
    amount: [0, [Validators.required, Validators.min(0.01)]],
    reason: ['', [Validators.required, Validators.maxLength(500)]],
    date: [new Date().toISOString().substring(0, 10), [Validators.required]],
  });

  ngOnInit() {
    this.loadFines();
    this.loadUsers();
  }

  protected loadFines() {
    this.loading.set(true);
    this.claimsService.getAdminFines().subscribe({
      next: (page) => {
        this.fines.set(page.items);
        this.loading.set(false);
      },
      error: (err) => {
        this.toast.error(err.message || 'Failed to load fines');
        this.loading.set(false);
      },
    });
  }

  protected loadUsers() {
    this.usersService.list({ page_size: 200 }).subscribe({
      next: (page) => this.users.set(page.items),
    });
  }

  protected openApplyFineModal() {
    this.fineForm.reset({
      employee_id: '',
      amount: 0,
      reason: '',
      date: new Date().toISOString().substring(0, 10),
    });
    this.showApplyFineModal.set(true);
  }

  protected applyFine() {
    if (this.fineForm.invalid) return;

    const val = this.fineForm.getRawValue();
    this.claimsService.createFine(val).subscribe({
      next: () => {
        this.toast.success('Fine applied successfully.');
        this.showApplyFineModal.set(false);
        this.loadFines();
      },
      error: (err) => this.toast.error(err.message || 'Failed to apply fine'),
    });
  }

  protected cancelFine(fine: Fine) {
    if (!confirm(`Cancel fine of ₹${fine.amount} applied to ${fine.employee?.full_name}?`)) return;

    this.claimsService.updateFineStatus(fine.id, 'CANCELLED').subscribe({
      next: () => {
        this.toast.success('Fine cancelled.');
        this.loadFines();
      },
      error: (err) => this.toast.error(err.message || 'Failed to cancel fine'),
    });
  }
}
