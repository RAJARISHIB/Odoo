import { CurrencyPipe, DatePipe, NgClass } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';

import { PayrollDocument } from '../../../../core/models/payroll.model';
import { User } from '../../../../core/models/user.model';
import { PayrollService } from '../../../../core/services/payroll';
import { Toast } from '../../../../core/services/toast';
import { Api } from '../../../../core/services/api';

@Component({
  selector: 'app-admin-payroll-documents',
  standalone: true,
  imports: [ReactiveFormsModule, DatePipe],
  templateUrl: './admin-payroll-documents.html',
  styleUrl: './admin-payroll-documents.scss',
})
export class AdminPayrollDocumentsComponent implements OnInit {
  private readonly payrollService = inject(PayrollService);
  private readonly api = inject(Api);
  private readonly toast = inject(Toast);
  private readonly fb = inject(FormBuilder);

  readonly loading = signal(true);
  readonly documents = signal<PayrollDocument[]>([]);
  readonly employees = signal<User[]>([]);
  readonly showModal = signal(false);
  selectedFile: File | null = null;

  readonly docTypes = [
    { value: 'PAYSLIP', label: 'Monthly Payslip' },
    { value: 'OFFER_LETTER', label: 'Offer Letter' },
    { value: 'CTC_DETAILS', label: 'Annual Salary / CTC Document' },
    { value: 'REVISION_LETTER', label: 'Salary Revision Letter' },
    { value: 'OTHER', label: 'Other Document' },
  ];

  uploadForm: FormGroup = this.fb.group({
    employee_id: ['', Validators.required],
    document_type: ['PAYSLIP', Validators.required],
    title: ['', Validators.required],
    payroll_month: [new Date().toISOString().substring(0, 7)],
    payroll_year: [new Date().getFullYear()],
  });

  ngOnInit(): void {
    this.loadDocuments();
    this.loadEmployees();
  }

  loadDocuments(): void {
    this.loading.set(true);
    this.payrollService.getAdminDocuments().subscribe({
      next: (res) => {
        this.documents.set(res.items);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  loadEmployees(): void {
    this.api.getPage<User>('users', { page_size: 200 }).subscribe({
      next: (res) => this.employees.set(res.items),
    });
  }

  openUploadModal(): void {
    this.uploadForm.reset({
      document_type: 'PAYSLIP',
      payroll_month: new Date().toISOString().substring(0, 7),
      payroll_year: new Date().getFullYear(),
    });
    this.selectedFile = null;
    this.showModal.set(true);
  }

  onFileChange(event: any): void {
    if (event.target.files && event.target.files.length > 0) {
      this.selectedFile = event.target.files[0];
    }
  }

  closeModal(): void {
    this.showModal.set(false);
  }

  submitUpload(): void {
    if (this.uploadForm.invalid) {
      this.uploadForm.markAllAsTouched();
      return;
    }
    if (!this.selectedFile) {
      this.toast.error('Please choose a file to upload');
      return;
    }

    const formData = new FormData();
    const val = this.uploadForm.value;
    formData.append('employee_id', val.employee_id);
    formData.append('document_type', val.document_type);
    formData.append('title', val.title);
    if (val.payroll_month) formData.append('payroll_month', val.payroll_month);
    if (val.payroll_year) formData.append('payroll_year', val.payroll_year.toString());
    formData.append('file', this.selectedFile, this.selectedFile.name);

    this.payrollService.uploadPayrollDocument(formData).subscribe({
      next: () => {
        this.toast.success('Payroll document uploaded successfully!');
        this.showModal.set(false);
        this.loadDocuments();
      },
      error: (err) => this.toast.error(err?.error?.message || 'Failed to upload document'),
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

  deleteDoc(doc: PayrollDocument): void {
    if (!confirm(`Are you sure you want to delete "${doc.title}"?`)) return;

    this.payrollService.deletePayrollDocument(doc.id).subscribe({
      next: () => {
        this.toast.success('Document deleted');
        this.loadDocuments();
      },
      error: () => this.toast.error('Failed to delete document'),
    });
  }
}
