export type ExpenseType = 'Travel' | 'Food' | 'Accommodation' | 'Transportation' | 'Other';
export type ClaimStatus = 'PENDING' | 'APPROVED' | 'REJECTED';
export type FineStatus = 'ACTIVE' | 'CANCELLED';
export type RequestType = 'id_card' | 'laptop' | 'other';
export type RequestStatus = 'PENDING' | 'APPROVED' | 'REJECTED';

export interface UserSummary {
  id: string;
  full_name: string;
  email?: string;
  employee_id?: string;
  designation?: string;
  avatar_url?: string;
}

export interface ExpenseClaim {
  id: string;
  expense_type: ExpenseType;
  other_type_description?: string;
  amount: number;
  expense_date: string;
  description: string;
  receipt_filename?: string;
  receipt_original_name?: string;
  has_receipt: boolean;
  status: ClaimStatus;
  admin_comment?: string;
  employee?: UserSummary;
  processed_by?: { id: string; full_name: string };
  created_at?: string;
}

export interface Fine {
  id: string;
  amount: number;
  reason: string;
  date: string;
  status: FineStatus;
  employee?: UserSummary;
  applied_by?: { id: string; full_name: string };
  created_at?: string;
}

export interface EmployeeRequest {
  id: string;
  request_type: RequestType;
  description: string;
  attachment_filename?: string;
  attachment_original_name?: string;
  has_attachment: boolean;
  status: RequestStatus;
  rejection_reason?: string;
  employee?: UserSummary;
  processed_by?: { id: string; full_name: string };
  created_at?: string;
}
