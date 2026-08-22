import { CurrencyPipe, DatePipe, NgClass } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormArray, FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';

import { EmployeePayroll, RoleSalaryTemplate, SalaryPreview } from '../../../../core/models/payroll.model';
import { User } from '../../../../core/models/user.model';
import { PayrollService } from '../../../../core/services/payroll';
import { Toast } from '../../../../core/services/toast';
import { Api } from '../../../../core/services/api';

@Component({
  selector: 'app-admin-payroll-assignments',
  standalone: true,
  imports: [ReactiveFormsModule, CurrencyPipe, DatePipe],
  templateUrl: './admin-payroll-assignments.html',
  styleUrl: './admin-payroll-assignments.scss',
})
export class AdminPayrollAssignmentComponent implements OnInit {
  private readonly payrollService = inject(PayrollService);
  private readonly api = inject(Api);
  private readonly toast = inject(Toast);
  private readonly fb = inject(FormBuilder);

  readonly loading = signal(true);
  readonly payrolls = signal<EmployeePayroll[]>([]);
  readonly employees = signal<User[]>([]);
  readonly roleTemplates = signal<RoleSalaryTemplate[]>([]);
  readonly showModal = signal(false);
  readonly preview = signal<SalaryPreview | null>(null);

  assignForm: FormGroup = this.fb.group({
    employee_id: ['', Validators.required],
    salary_source: ['ROLE', Validators.required],
    role_template_id: [''],
    monthly_wage: [50000, [Validators.required, Validators.min(1)]],
    employee_pf_rate: [12],
    employer_pf_rate: [12],
    pf_base_component: ['Basic Salary'],
    professional_tax: [200],
    other_deductions: [0],
    effective_from: [new Date().toISOString().substring(0, 10)],
    components: this.fb.array([]),
  });

  get componentsArray(): FormArray {
    return this.assignForm.get('components') as FormArray;
  }

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.loading.set(true);
    this.payrollService.getAllEmployeePayrolls().subscribe({
      next: (res) => {
        this.payrolls.set(res.items);
        this.loadEmployees();
      },
      error: () => this.loading.set(false),
    });
  }

  loadEmployees(): void {
    this.api.getPage<User>('users', { page_size: 200 }).subscribe({
      next: (res) => {
        this.employees.set(res.items);
        this.loadRoleTemplates();
      },
      error: () => this.loading.set(false),
    });
  }

  loadRoleTemplates(): void {
    this.payrollService.getRoleTemplates().subscribe({
      next: (res) => {
        this.roleTemplates.set(res.items);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  openAssignModal(existing?: EmployeePayroll): void {
    if (existing && existing.employee) {
      this.assignForm.patchValue({
        employee_id: existing.employee.id,
        salary_source: existing.salary_source,
        role_template_id: typeof existing.role_template === 'object' ? existing.role_template?.id : existing.role_template || '',
        monthly_wage: existing.monthly_wage,
        employee_pf_rate: existing.employee_pf_rate,
        employer_pf_rate: existing.employer_pf_rate,
        pf_base_component: existing.pf_base_component || 'Basic Salary',
        professional_tax: existing.professional_tax,
        other_deductions: existing.other_deductions || 0,
        effective_from: existing.effective_from || new Date().toISOString().substring(0, 10),
      });

      this.componentsArray.clear();
      (existing.components || []).forEach((c) => {
        this.componentsArray.push(
          this.fb.group({
            name: [c.name, Validators.required],
            calculation_type: [c.calculation_type, Validators.required],
            value: [c.value, Validators.required],
            depends_on: [c.depends_on || 'WAGE'],
            is_fixed_allowance_remainder: [!!c.is_fixed_allowance_remainder],
          })
        );
      });
    } else {
      this.assignForm.reset({
        salary_source: 'ROLE',
        monthly_wage: 50000,
        employee_pf_rate: 12,
        employer_pf_rate: 12,
        pf_base_component: 'Basic Salary',
        professional_tax: 200,
        other_deductions: 0,
        effective_from: new Date().toISOString().substring(0, 10),
      });
      this.initDefaultComponents();
    }

    this.showModal.set(true);
    this.recalculatePreview();
  }

  initDefaultComponents(): void {
    this.componentsArray.clear();
    const defaults = [
      { name: 'Basic Salary', calculation_type: 'PERCENTAGE', value: 50, depends_on: 'WAGE', is_fixed_allowance_remainder: false },
      { name: 'House Rent Allowance', calculation_type: 'PERCENTAGE', value: 50, depends_on: 'Basic Salary', is_fixed_allowance_remainder: false },
      { name: 'Standard Allowance', calculation_type: 'PERCENTAGE', value: 16.67, depends_on: 'WAGE', is_fixed_allowance_remainder: false },
      { name: 'Performance Bonus', calculation_type: 'PERCENTAGE', value: 8.33, depends_on: 'WAGE', is_fixed_allowance_remainder: false },
      { name: 'Leave Travel Allowance', calculation_type: 'PERCENTAGE', value: 8.33, depends_on: 'WAGE', is_fixed_allowance_remainder: false },
      { name: 'Fixed Allowance', calculation_type: 'FIXED_AMOUNT', value: 0, depends_on: 'WAGE', is_fixed_allowance_remainder: true },
    ];

    defaults.forEach((c) => this.componentsArray.push(this.fb.group(c)));
  }

  onSourceChange(): void {
    const src = this.assignForm.value.salary_source;
    if (src === 'ROLE') {
      const empId = this.assignForm.value.employee_id;
      const emp = this.employees().find((e) => e.id === empId);
      if (emp) {
        const tpl = this.roleTemplates().find((t) => t.role === emp.role);
        if (tpl) {
          this.assignForm.patchValue({
            role_template_id: tpl.id,
            monthly_wage: tpl.monthly_wage,
            employee_pf_rate: tpl.employee_pf_rate,
            professional_tax: tpl.professional_tax,
          });
        }
      }
    }
    this.recalculatePreview();
  }

  recalculatePreview(): void {
    const val = this.assignForm.value;
    if (!val.monthly_wage || val.monthly_wage <= 0) return;

    this.payrollService.previewSalaryCalculation(val).subscribe({
      next: (res) => this.preview.set(res),
      error: () => {},
    });
  }

  closeModal(): void {
    this.showModal.set(false);
  }

  savePayroll(): void {
    if (this.assignForm.invalid) {
      this.assignForm.markAllAsTouched();
      return;
    }

    this.payrollService.assignEmployeePayroll(this.assignForm.value).subscribe({
      next: () => {
        this.toast.success('Employee payroll configuration saved successfully!');
        this.showModal.set(false);
        this.loadData();
      },
      error: (err) => this.toast.error(err?.error?.message || 'Failed to save employee payroll'),
    });
  }
}
