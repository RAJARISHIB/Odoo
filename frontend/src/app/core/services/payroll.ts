import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Page } from '../models/api.model';
import { EmployeePayroll, PayrollDocument, RoleSalaryTemplate, SalaryPreview } from '../models/payroll.model';
import { Api } from './api';
import { environment } from '../../../environments/environment';

@Injectable({ providedIn: 'root' })
export class PayrollService {
  private readonly api = inject(Api);
  private readonly http = inject(HttpClient);
  private readonly baseUrl = environment.apiUrl;

  // --- Employee Self-Service ---
  getMyPayroll(): Observable<EmployeePayroll> {
    return this.api.get<EmployeePayroll>('payroll/me');
  }

  getMyDocuments(documentType?: string, page = 1, pageSize = 50): Observable<Page<PayrollDocument>> {
    return this.api.getPage<PayrollDocument>('payroll/me/documents', { document_type: documentType, page, page_size: pageSize });
  }

  downloadDocument(documentId: string): Observable<Blob> {
    const url = `${this.baseUrl}/payroll/documents/${documentId}/download`;
    return this.http.get(url, { responseType: 'blob' });
  }

  // --- Admin Role Templates ---
  getRoleTemplates(page = 1, pageSize = 50): Observable<Page<RoleSalaryTemplate>> {
    return this.api.getPage<RoleSalaryTemplate>('admin/payroll/templates', { page, page_size: pageSize });
  }

  getRoleTemplateDetail(id: string): Observable<RoleSalaryTemplate> {
    return this.api.get<RoleSalaryTemplate>(`admin/payroll/templates/${id}`);
  }

  upsertRoleTemplate(payload: any): Observable<RoleSalaryTemplate> {
    return this.api.post<RoleSalaryTemplate>('admin/payroll/templates', payload);
  }

  previewSalaryCalculation(payload: any): Observable<SalaryPreview> {
    return this.api.post<SalaryPreview>('admin/payroll/preview', payload);
  }

  // --- Admin Employee Payroll Assignments ---
  getAllEmployeePayrolls(page = 1, pageSize = 100): Observable<Page<EmployeePayroll>> {
    return this.api.getPage<EmployeePayroll>('admin/payroll/employees', { page, page_size: pageSize });
  }

  getEmployeePayrollAdmin(userId: string): Observable<EmployeePayroll> {
    return this.api.get<EmployeePayroll>(`admin/payroll/employees/${userId}`);
  }

  assignEmployeePayroll(payload: any): Observable<EmployeePayroll> {
    return this.api.post<EmployeePayroll>('admin/payroll/employees', payload);
  }

  // --- Admin Payroll Documents ---
  getAdminDocuments(employeeId?: string, documentType?: string, page = 1, pageSize = 50): Observable<Page<PayrollDocument>> {
    return this.api.getPage<PayrollDocument>('admin/payroll/documents', {
      employee_id: employeeId,
      document_type: documentType,
      page,
      page_size: pageSize,
    });
  }

  uploadPayrollDocument(form: FormData): Observable<PayrollDocument> {
    return this.api.postForm<PayrollDocument>('admin/payroll/documents', form);
  }

  deletePayrollDocument(id: string): Observable<void> {
    return this.api.delete<void>(`admin/payroll/documents/${id}`);
  }
}
