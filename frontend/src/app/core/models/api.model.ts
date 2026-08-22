/** The response envelope every Django endpoint returns (`core/responses.py`). */
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message?: string;
  meta?: PageMeta & Record<string, unknown>;
  error?: ApiErrorBody;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  /** Per-field messages from a 422, keyed by form control name. */
  details?: Record<string, string>;
}

export interface PageMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

/** A list response unwrapped into the shape the tables consume. */
export interface Page<T> {
  items: T[];
  meta: PageMeta;
}

export const EMPTY_PAGE_META: PageMeta = {
  page: 1,
  page_size: 20,
  total: 0,
  total_pages: 0,
  has_next: false,
  has_previous: false,
};
