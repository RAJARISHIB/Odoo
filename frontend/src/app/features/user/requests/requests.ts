import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { EmployeeRequest, RequestType } from '../../../core/models/claims.model';
import { ClaimsService } from '../../../core/services/claims';
import { Toast } from '../../../core/services/toast';
import { Icon } from '../../../shared/icon/icon';

@Component({
  selector: 'app-employee-requests',
  standalone: true,
  imports: [ReactiveFormsModule, DatePipe, Icon],
  templateUrl: './requests.html',
  styleUrl: './requests.scss',
})
export class EmployeeRequestsComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly claimsService = inject(ClaimsService);
  private readonly toast = inject(Toast);

  protected readonly requests = signal<EmployeeRequest[]>([]);
  protected readonly loading = signal(true);
  protected readonly showNewRequestModal = signal(false);
  protected selectedFile: File | null = null;

  protected readonly requestTypeOptions: { value: RequestType; label: string }[] = [
    { value: 'id_card', label: 'ID Card (New, Replacement, Lost)' },
    { value: 'laptop', label: 'Laptop (New, Replacement, Hardware Issue)' },
    { value: 'other', label: 'Other Custom Request' },
  ];

  protected readonly requestForm = this.fb.nonNullable.group({
    request_type: ['id_card' as RequestType, [Validators.required]],
    description: ['', [Validators.required, Validators.maxLength(1000)]],
  });

  ngOnInit() {
    this.loadRequests();
  }

  protected loadRequests() {
    this.loading.set(true);
    this.claimsService.getEmployeeRequests().subscribe({
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

  protected openNewRequestModal() {
    this.requestForm.reset({
      request_type: 'id_card',
      description: '',
    });
    this.selectedFile = null;
    this.showNewRequestModal.set(true);
  }

  protected onFileSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      this.selectedFile = input.files[0];
    }
  }

  protected submitRequest() {
    if (this.requestForm.invalid) return;

    const val = this.requestForm.getRawValue();
    const formData = new FormData();
    formData.append('request_type', val.request_type);
    formData.append('description', val.description);

    if (this.selectedFile) {
      formData.append('attachment', this.selectedFile);
    }

    this.claimsService.createRequest(formData).subscribe({
      next: () => {
        this.toast.success('Employee request submitted successfully.');
        this.showNewRequestModal.set(false);
        this.loadRequests();
      },
      error: (err) => this.toast.error(err.message || 'Failed to submit request'),
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
