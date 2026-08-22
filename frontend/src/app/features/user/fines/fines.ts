import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';

import { Fine } from '../../../core/models/claims.model';
import { ClaimsService } from '../../../core/services/claims';
import { Toast } from '../../../core/services/toast';
import { Icon } from '../../../shared/icon/icon';

@Component({
  selector: 'app-fines',
  standalone: true,
  imports: [CurrencyPipe, DatePipe, Icon],
  templateUrl: './fines.html',
  styleUrl: './fines.scss',
})
export class FinesComponent implements OnInit {
  private readonly claimsService = inject(ClaimsService);
  private readonly toast = inject(Toast);

  protected readonly fines = signal<Fine[]>([]);
  protected readonly loading = signal(true);

  ngOnInit() {
    this.loadFines();
  }

  protected loadFines() {
    this.loading.set(true);
    this.claimsService.getEmployeeFines().subscribe({
      next: (page) => {
        this.fines.set(page.items);
        this.loading.set(false);
      },
      error: (err) => {
        this.toast.error(err.message || 'Failed to load fines history');
        this.loading.set(false);
      },
    });
  }
}
