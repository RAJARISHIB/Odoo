import { CurrencyPipe, DatePipe, NgClass } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';

import { EmployeePayroll, PayrollDocument } from '../../../core/models/payroll.model';
import { PayrollService } from '../../../core/services/payroll';
import { Toast } from '../../../core/services/toast';
import { Icon } from '../../../shared/icon/icon';

@Component({
  selector: 'app-my-payroll',
  standalone: true,
  imports: [CurrencyPipe, DatePipe, Icon],
  templateUrl: './my-payroll.html',
  styleUrl: './my-payroll.scss',
})
export class MyPayrollComponent implements OnInit {
  private readonly payrollService = inject(PayrollService);
  private readonly toast = inject(Toast);

  readonly loading = signal(true);
  readonly payroll = signal<EmployeePayroll | null>(null);
  readonly documents = signal<PayrollDocument[]>([]);

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.loading.set(true);
    this.payrollService.getMyPayroll().subscribe({
      next: (data) => {
        this.payroll.set(data);
        this.loadDocuments();
      },
      error: (err) => {
        this.toast.error('Failed to load payroll details');
        this.loading.set(false);
      },
    });
  }

  loadDocuments(): void {
    this.payrollService.getMyDocuments().subscribe({
      next: (res) => {
        this.documents.set(res.items);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  downloadDoc(doc: PayrollDocument): void {
    this.payrollService.downloadDocument(doc.id).subscribe({
      next: (blobData) => {
        const filename = doc.original_filename || doc.filename || 'payroll_document.pdf';
        const mimeType = this.getMimeType(filename) || blobData.type || 'application/pdf';
        const blob = new Blob([blobData], { type: mimeType });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
      },
      error: () => this.toast.error('Failed to download document'),
    });
  }

  private getMimeType(filename: string): string {
    const ext = filename.split('.').pop()?.toLowerCase();
    if (ext === 'pdf') return 'application/pdf';
    if (ext === 'png') return 'image/png';
    if (ext === 'jpg' || ext === 'jpeg') return 'image/jpeg';
    if (ext === 'doc') return 'application/msword';
    if (ext === 'docx') return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
    return 'application/octet-stream';
  }
}
