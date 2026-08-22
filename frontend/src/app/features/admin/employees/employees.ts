import { ChangeDetectionStrategy, Component, effect, inject, input, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { SlicePipe } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { ApiErrorBody, EMPTY_PAGE_META, PageMeta } from '../../../core/models/api.model';
import { Auth } from '../../../core/services/auth';
import { Realtime } from '../../../core/services/realtime';
import { Role, User, roleSlug } from '../../../core/models/user.model';
import { Toast } from '../../../core/services/toast';
import { Users } from '../../../core/services/users';
import { RouterLink } from '@angular/router';
import { Icon } from '../../../shared/icon/icon';

/** Employee directory: search, paginate, invite, deactivate, reset passwords. */
@Component({
  selector: 'app-employees',
  imports: [ReactiveFormsModule, SlicePipe, RouterLink, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './employees.html',
  styleUrl: './employees.scss',
})
export class Employees {
  /** `?new=1` from the directory's "New employee" button, bound by
      `withComponentInputBinding()`. Opens the create form on arrival. */
  readonly new = input<string | undefined>(undefined);

  private readonly users = inject(Users);
  private readonly toast = inject(Toast);
  private readonly realtime = inject(Realtime);
  private readonly fb = inject(FormBuilder);
  protected readonly auth = inject(Auth);

  protected readonly rows = signal<User[]>([]);
  protected readonly meta = signal<PageMeta>(EMPTY_PAGE_META);
  protected readonly loading = signal(false);
  protected readonly showForm = signal(false);
  protected readonly showInviteForm = signal(false);
  protected readonly saving = signal(false);
  protected readonly inviteSaving = signal(false);
  protected readonly formErrors = signal<Record<string, string>>({});
  protected readonly inviteFormErrors = signal<Record<string, string>>({});
  /**
   * The credentials the system just issued, shown once so the admin can pass
   * them to the employee.  The password is never retrievable afterwards.
   */
  protected readonly issuedCredentials = signal<
    { loginId: string; email: string; password: string } | null
  >(null);

  protected readonly sentInviteInfo = signal<{ email: string; invite_url: string } | null>(null);

  protected readonly roles: Role[] = ['employee', 'manager', 'hr', 'admin', 'super_admin'];
  /** `roleSlug` bound as a field so the template can call it - see the
      comment on its definition for why this is needed at all. */
  protected readonly roleSlug = roleSlug;

  protected readonly filters = this.fb.nonNullable.group({
    search: [''],
    role: [''],
    status: [''],
  });

  protected readonly form = this.fb.nonNullable.group({
    first_name: ['', Validators.required],
    last_name: [''],
    email: ['', [Validators.required, Validators.email]],
    designation: [''],
    employee_id: [''],
    role: ['employee' as Role, Validators.required],
    password: [''],
  });

  protected readonly inviteForm = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    first_name: ['', Validators.required],
    last_name: [''],
    designation: [''],
    employee_id: [''],
    role: ['employee' as Role, Validators.required],
  });

  constructor() {
    this.load();

    effect(() => {
      if (this.new()) this.showForm.set(true);
    });

    // Keep the table honest when another admin adds or edits someone.
    this.realtime
      .onAny(['user.created', 'user.updated', 'user.status_changed'])
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.load(this.meta().page));
  }

  protected load(page = 1): void {
    this.loading.set(true);
    const { search, role, status } = this.filters.getRawValue();

    this.users.list({ page, page_size: this.meta().page_size, search, role, status }).subscribe({
      next: (result) => {
        this.rows.set(result.items);
        this.meta.set(result.meta);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  protected applyFilters(): void {
    this.load(1);
  }

  protected resetFilters(): void {
    this.filters.reset({ search: '', role: '', status: '' });
    this.load(1);
  }

  protected goToPage(page: number): void {
    if (page < 1 || page > this.meta().total_pages) return;
    this.load(page);
  }

  // -- create & invite ---------------------------------------------------
  protected toggleForm(): void {
    this.showForm.update((open) => !open);
    if (this.showForm()) {
      this.showInviteForm.set(false);
    }
    this.formErrors.set({});
  }

  protected toggleInviteForm(): void {
    this.showInviteForm.update((open) => !open);
    if (this.showInviteForm()) {
      this.showForm.set(false);
    }
    this.inviteFormErrors.set({});
  }

  protected sendInvite(): void {
    if (this.inviteForm.invalid || this.inviteSaving()) {
      this.inviteForm.markAllAsTouched();
      return;
    }

    this.inviteSaving.set(true);
    this.inviteFormErrors.set({});
    const payload = this.inviteForm.getRawValue();

    this.users.invite(payload).subscribe({
      next: (res) => {
        this.inviteSaving.set(false);
        this.toast.success(`Invitation sent to ${payload.email}!`);
        this.sentInviteInfo.set({ email: payload.email, invite_url: res.invite_url });
        this.inviteForm.reset({ role: 'employee' });
        this.showInviteForm.set(false);
        this.load(1);
      },
      error: (error: ApiErrorBody) => {
        this.inviteSaving.set(false);
        this.inviteFormErrors.set(error.details ?? { email: error.message });
      },
    });
  }

  protected create(): void {
    if (this.form.invalid || this.saving()) {
      this.form.markAllAsTouched();
      return;
    }

    this.saving.set(true);
    this.formErrors.set({});
    const payload = this.form.getRawValue();

    this.users.create({ ...payload, password: payload.password || undefined }).subscribe({
      next: (user) => {
        this.saving.set(false);
        this.toast.success(`${user.full_name} added.`);
        if (user.temporary_password) {
          this.issuedCredentials.set({
            loginId: user.login_id,
            email: user.email,
            password: user.temporary_password,
          });
        }
        this.form.reset({ role: 'employee' });
        this.showForm.set(false);
        this.load(1);
      },
      error: (error: ApiErrorBody) => {
        this.saving.set(false);
        this.formErrors.set(error.details ?? { email: error.message });
      },
    });
  }

  // Reset password, suspend and remove now live on the edit page
  // (features/admin/employees/employee-edit.ts), reached from the row.

  protected initials(user: User): string {
    return `${user.first_name?.[0] ?? ''}${user.last_name?.[0] ?? ''}`.toUpperCase() || 'U';
  }

  protected dismissCredentials(): void {
    this.issuedCredentials.set(null);
  }

  protected dismissInviteInfo(): void {
    this.sentInviteInfo.set(null);
  }
}
