import { CurrencyPipe, DatePipe, NgClass } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormArray, FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';

import { RoleSalaryTemplate, SalaryPreview } from '../../../../core/models/payroll.model';
import { PayrollService } from '../../../../core/services/payroll';
import { Toast } from '../../../../core/services/toast';

@Component({
  selector: 'app-admin-payroll-templates',
  standalone: true,
  imports: [ReactiveFormsModule, CurrencyPipe],
  templateUrl: './admin-payroll-templates.html',
  styleUrl: './admin-payroll-templates.scss',
})
export class AdminPayrollTemplatesComponent implements OnInit {
  private readonly payrollService = inject(PayrollService);
  private readonly toast = inject(Toast);
  private readonly fb = inject(FormBuilder);

  readonly loading = signal(true);
  readonly templates = signal<RoleSalaryTemplate[]>([]);
  readonly showModal = signal(false);
  readonly preview = signal<SalaryPreview | null>(null);

  readonly roles = [
    { value: 'super_admin', label: 'Super Admin' },
    { value: 'admin', label: 'Admin / Head of Engineering' },
    { value: 'hr', label: 'HR Manager' },
    { value: 'manager', label: 'Engineering Manager' },
    { value: 'employee', label: 'Employee / Software Engineer' },
  ];

  templateForm: FormGroup = this.fb.group({
    id: [''],
    role: ['employee', Validators.required],
    designation: [''],
    monthly_wage: [50000, [Validators.required, Validators.min(1)]],
    employee_pf_rate: [12],
    employer_pf_rate: [12],
    pf_base_component: ['Basic Salary'],
    professional_tax: [200],
    other_deductions: [0],
    working_days_per_week: [5],
    components: this.fb.array([]),
  });

  get componentsArray(): FormArray {
    return this.templateForm.get('components') as FormArray;
  }

  ngOnInit(): void {
    this.loadTemplates();
  }

  loadTemplates(): void {
    this.loading.set(true);
    this.payrollService.getRoleTemplates().subscribe({
      next: (res) => {
        this.templates.set(res.items);
        this.loading.set(false);
      },
      error: () => {
        this.toast.error('Failed to load salary templates');
        this.loading.set(false);
      },
    });
  }

  openCreateModal(): void {
    this.templateForm.reset({
      role: 'employee',
      designation: '',
      monthly_wage: 50000,
      employee_pf_rate: 12,
      employer_pf_rate: 12,
      pf_base_component: 'Basic Salary',
      professional_tax: 200,
      other_deductions: 0,
      working_days_per_week: 5,
    });
    this.initDefaultComponents(50000);
    this.showModal.set(true);
    this.recalculatePreview();
  }

  openEditModal(tpl: RoleSalaryTemplate): void {
    this.templateForm.patchValue({
      id: tpl.id,
      role: tpl.role,
      designation: tpl.designation || '',
      monthly_wage: tpl.monthly_wage,
      employee_pf_rate: tpl.employee_pf_rate,
      employer_pf_rate: tpl.employer_pf_rate,
      pf_base_component: tpl.pf_base_component || 'Basic Salary',
      professional_tax: tpl.professional_tax,
      other_deductions: tpl.other_deductions || 0,
      working_days_per_week: tpl.working_days_per_week || 5,
    });

    this.componentsArray.clear();
    (tpl.components || []).forEach((c) => {
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

    this.showModal.set(true);
    this.recalculatePreview();
  }

  initDefaultComponents(wage: number): void {
    this.componentsArray.clear();
    const defaults = [
      { name: 'Basic Salary', calculation_type: 'PERCENTAGE', value: 50, depends_on: 'WAGE', is_fixed_allowance_remainder: false },
      { name: 'House Rent Allowance', calculation_type: 'PERCENTAGE', value: 50, depends_on: 'Basic Salary', is_fixed_allowance_remainder: false },
      { name: 'Standard Allowance', calculation_type: 'PERCENTAGE', value: 16.67, depends_on: 'WAGE', is_fixed_allowance_remainder: false },
      { name: 'Performance Bonus', calculation_type: 'PERCENTAGE', value: 8.33, depends_on: 'WAGE', is_fixed_allowance_remainder: false },
      { name: 'Leave Travel Allowance', calculation_type: 'PERCENTAGE', value: 8.33, depends_on: 'WAGE', is_fixed_allowance_remainder: false },
      { name: 'Fixed Allowance', calculation_type: 'FIXED_AMOUNT', value: 0, depends_on: 'WAGE', is_fixed_allowance_remainder: true },
    ];

    defaults.forEach((c) => {
      this.componentsArray.push(this.fb.group(c));
    });
  }

  addComponent(): void {
    this.componentsArray.push(
      this.fb.group({
        name: ['New Allowance', Validators.required],
        calculation_type: ['PERCENTAGE', Validators.required],
        value: [10, Validators.required],
        depends_on: ['WAGE'],
        is_fixed_allowance_remainder: [false],
      })
    );
    this.recalculatePreview();
  }

  removeComponent(index: number): void {
    this.componentsArray.removeAt(index);
    this.recalculatePreview();
  }

  recalculatePreview(): void {
    const val = this.templateForm.value;
    if (!val.monthly_wage || val.monthly_wage <= 0) return;

    this.payrollService.previewSalaryCalculation(val).subscribe({
      next: (res) => this.preview.set(res),
      error: () => {},
    });
  }

  closeModal(): void {
    this.showModal.set(false);
  }

  saveTemplate(): void {
    if (this.templateForm.invalid) {
      this.templateForm.markAllAsTouched();
      return;
    }

    this.payrollService.upsertRoleTemplate(this.templateForm.value).subscribe({
      next: () => {
        this.toast.success('Role salary template saved! Role-based employees updated.');
        this.showModal.set(false);
        this.loadTemplates();
      },
      error: (err) => this.toast.error(err?.error?.message || 'Failed to save salary template'),
    });
  }
}
