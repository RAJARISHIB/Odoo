export interface SalaryComponent {
  name: string;
  calculation_type: 'PERCENTAGE' | 'FIXED_AMOUNT';
  value: number;
  depends_on?: string;
  is_fixed_allowance_remainder?: boolean;
  calculated_amount?: number;
}

export interface RoleSalaryTemplate {
  id: string;
  role: string;
  designation?: string;
  wage_type: string;
  monthly_wage: number;
  yearly_wage: number;
  components: SalaryComponent[];
  employee_pf_rate: number;
  employer_pf_rate: number;
  pf_base_component: string;
  professional_tax: number;
  other_deductions: number;
  working_days_per_week: number;
}

export interface EmployeePayroll {
  id: string;
  employee?: {
    id: string;
    full_name: string;
    email: string;
    employee_id?: string;
    designation?: string;
    role?: string;
  };
  salary_source: 'ROLE' | 'MANUAL';
  role_template?: string | RoleSalaryTemplate;
  wage_type: string;
  monthly_wage: number;
  yearly_wage: number;
  components: SalaryComponent[];
  employee_pf_rate: number;
  employer_pf_rate: number;
  pf_base_component: string;
  professional_tax: number;
  other_deductions: number;
  gross_salary: number;
  total_deductions: number;
  net_salary: number;
  employee_pf_amount: number;
  employer_pf_amount: number;
  effective_from?: string;
  is_active: boolean;
}

export interface PayrollDocument {
  id: string;
  employee?: {
    id: string;
    full_name: string;
    email: string;
    employee_id?: string;
  };
  document_type: 'PAYSLIP' | 'OFFER_LETTER' | 'CTC_DETAILS' | 'REVISION_LETTER' | 'OTHER';
  title: string;
  payroll_month?: string;
  payroll_year?: number;
  filename: string;
  original_filename: string;
  uploaded_by?: {
    id: string;
    full_name: string;
  };
  created_at: string;
}

export interface SalaryPreview {
  monthly_wage: number;
  yearly_wage: number;
  components: SalaryComponent[];
  gross_salary: number;
  employee_pf_rate: number;
  employer_pf_rate: number;
  pf_base_component: string;
  employee_pf_amount: number;
  employer_pf_amount: number;
  professional_tax: number;
  other_deductions: number;
  total_deductions: number;
  net_salary: number;
}
