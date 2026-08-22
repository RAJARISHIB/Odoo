import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Page } from '../models/api.model';
import { EmployeeRequest, ExpenseClaim, Fine } from '../models/claims.model';
import { Api } from './api';
import { environment } from '../../../environments/environment';

@Injectable({ providedIn: 'root' })
export class ClaimsService {
  private readonly api = inject(Api);
  private readonly http = inject(HttpClient);
  private readonly baseUrl = environment.apiUrl;

  // --- Expense Claims ---
  getEmployeeClaims(page = 1, pageSize = 50): Observable<Page<ExpenseClaim>> {
    return this.api.getPage<ExpenseClaim>('claims', { page, page_size: pageSize });
  }

  createClaim(form: FormData): Observable<ExpenseClaim> {
    return this.api.postForm<ExpenseClaim>('claims', form);
  }

  getAdminClaims(status?: string, page = 1, pageSize = 50): Observable<Page<ExpenseClaim>> {
    return this.api.getPage<ExpenseClaim>('admin/claims', { status, page, page_size: pageSize });
  }

  approveClaim(id: string, comment?: string): Observable<ExpenseClaim> {
    return this.api.post<ExpenseClaim>(`admin/claims/${id}/approve`, { comment });
  }

  rejectClaim(id: string, comment?: string): Observable<ExpenseClaim> {
    return this.api.post<ExpenseClaim>(`admin/claims/${id}/reject`, { comment });
  }

  downloadClaimAttachment(id: string): Observable<Blob> {
    const url = `${this.baseUrl}/claims/${id}/attachment`;
    return this.http.get(url, { responseType: 'blob' });
  }

  // --- Fines ---
  getEmployeeFines(page = 1, pageSize = 50): Observable<Page<Fine>> {
    return this.api.getPage<Fine>('fines', { page, page_size: pageSize });
  }

  getAdminFines(employeeId?: string, page = 1, pageSize = 50): Observable<Page<Fine>> {
    return this.api.getPage<Fine>('admin/fines', { employee_id: employeeId, page, page_size: pageSize });
  }

  createFine(payload: { employee_id: string; amount: number; reason: string; date?: string }): Observable<Fine> {
    return this.api.post<Fine>('admin/fines', payload);
  }

  updateFineStatus(id: string, status: string): Observable<Fine> {
    return this.api.patch<Fine>(`admin/fines/${id}`, { status });
  }

  // --- Employee Requests ---
  getEmployeeRequests(page = 1, pageSize = 50): Observable<Page<EmployeeRequest>> {
    return this.api.getPage<EmployeeRequest>('requests', { page, page_size: pageSize });
  }

  createRequest(form: FormData): Observable<EmployeeRequest> {
    return this.api.postForm<EmployeeRequest>('requests', form);
  }

  getAdminRequests(status?: string, requestType?: string, page = 1, pageSize = 50): Observable<Page<EmployeeRequest>> {
    return this.api.getPage<EmployeeRequest>('admin/requests', { status, request_type: requestType, page, page_size: pageSize });
  }

  approveRequest(id: string): Observable<EmployeeRequest> {
    return this.api.post<EmployeeRequest>(`admin/requests/${id}/approve`, {});
  }

  rejectRequest(id: string, rejectionReason?: string): Observable<EmployeeRequest> {
    return this.api.post<EmployeeRequest>(`admin/requests/${id}/reject`, { rejection_reason: rejectionReason });
  }

  downloadRequestAttachment(id: string): Observable<Blob> {
    const url = `${this.baseUrl}/requests/${id}/attachment`;
    return this.http.get(url, { responseType: 'blob' });
  }
}
