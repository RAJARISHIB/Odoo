import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { ApiErrorBody } from '../../../core/models/api.model';
import { Auth } from '../../../core/services/auth';
import { Department, Role, User, UserStatus, roleSlug } from '../../../core/models/user.model';
import { Organizations, Users } from '../../../core/services/users';
import { Toast } from '../../../core/services/toast';
import { Icon } from '../../../shared/icon/icon';

/**
 * One employee's record, as an admin sees it.
 *
 * This page exists because the People table had no edit at all — an admin
 * could create someone, suspend them or delete them, but a misspelt name or a
 * wrong role could only be fixed by removing the person and starting again.
 *
 * The row-level Reset / Suspend / Remove buttons moved here too. On a table
 * they were three destructive-ish controls repeated on every line, hit without
 * ever seeing the record they applied to; here they sit under the record
 * itself, and the dangerous pair are grouped and labelled as such.
 */
@Component({
  selector: 'app-employee-edit',
  imports: [ReactiveFormsModule, RouterLink, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './employee-edit.html',
  styleUrl: './employee-edit.scss',
})
export class EmployeeEdit {
  /** Route param, bound by `withComponentInputBinding()`. */
  readonly id = input.required<string>();

  private readonly users = inject(Users);
  private readonly organizations = inject(Organizations);
  private readonly toast = inject(Toast);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);
  protected readonly auth = inject(Auth);

  protected readonly user = signal<User | null>(null);
  protected readonly departments = signal<Department[]>([]);
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly notFound = signal(false);
  protected readonly formErrors = signal<Record<string, string>>({});
  /** The temporary password a reset just issued, shown once. */
  protected readonly issuedPassword = signal<string | null>(null);

  protected readonly roles: Role[] = ['employee', 'manager', 'hr', 'admin', 'super_admin'];

  /** Index in `roles` doubles as rank - lowest first, matching the backend's
      `_ROLE_RANK` in `apps/users/services.py`. */
  private readonly roleRank: Record<Role, number> = Object.fromEntries(
    this.roles.map((role, index) => [role, index]),
  ) as Record<Role, number>;

  /**
   * The backend refuses a self-demotion, and rightly so — an admin who removed
   * their own last privilege would lock themselves out of the page that could
   * undo it. Disabling the control says so before the request is sent.
   */
  protected readonly isSelf = computed(() => this.user()?.id === this.auth.user()?.id);

  /**
   * The backend also refuses to let an admin touch a peer or a superior at
   * all — not just the role field, the whole record — applied even between
   * two `super_admin`s. Disabling the form here says so up front instead of
   * letting Save round-trip into a rejection.
   */
  protected readonly isProtected = computed(() => {
    const target = this.user();
    const me = this.auth.user();
    if (!target || !me || this.isSelf()) return false;
    return this.roleRank[roleSlug(target.role)] >= this.roleRank[roleSlug(me.role)];
  });

  protected readonly form = this.fb.nonNullable.group({
    first_name: ['', Validators.required],
    last_name: [''],
    phone: [''],
    designation: [''],
    employee_id: [''],
    date_of_birth: [''],
    role: ['employee' as Role, Validators.required],
    department_id: [''],
    // `status` is deliberately not a form control: Suspend/Activate below owns
    // it, so it cannot be changed silently as a side effect of saving a name.
  });

  constructor() {
    this.organizations.departments({ page_size: 100 }).subscribe((page) => {
      this.departments.set(page.items);
    });

    // An effect rather than a constructor read: a required input has no value
    // yet during construction, and this also re-fetches when the route param
    // changes, which the router does by reusing this component instance.
    effect(() => {
      const id = this.id();
      this.loading.set(true);
      this.notFound.set(false);

      this.users.get(id).subscribe({
        next: (user) => this.hydrate(user),
        error: () => {
          this.loading.set(false);
          this.notFound.set(true);
        },
      });
    });
  }

  private hydrate(user: User): void {
    this.user.set(user);
    this.loading.set(false);
    this.form.patchValue({
      first_name: user.first_name,
      last_name: user.last_name ?? '',
      phone: user.phone ?? '',
      designation: user.designation ?? '',
      employee_id: user.employee_id ?? '',
      date_of_birth: user.date_of_birth ?? '',
      role: roleSlug(user.role),
      department_id: user.department_id ?? '',
    });
    if (this.isSelf()) this.form.controls.role.disable();
    if (this.isProtected()) this.form.disable();
  }

  protected initials(): string {
    const user = this.user();
    if (!user) return '?';
    return `${user.first_name?.[0] ?? ''}${user.last_name?.[0] ?? ''}`.toUpperCase() || 'U';
  }

  // -- save ----------------------------------------------------------------
  protected save(): void {
    if (this.form.invalid || this.saving() || this.isProtected()) {
      this.form.markAllAsTouched();
      return;
    }

    const user = this.user();
    if (!user) return;

    this.saving.set(true);
    this.formErrors.set({});

    // `getRawValue` includes the role control even when it is disabled for a
    // self-edit, so that one field is stripped rather than sent and rejected.
    const { role, ...rest } = this.form.getRawValue();
    const payload = {
      ...rest,
      // Empty strings mean "cleared", which the backend stores as null for
      // dates; the other fields are happy with an empty string.
      date_of_birth: rest.date_of_birth || null,
      department_id: rest.department_id || null,
      ...(this.isSelf() ? {} : { role }),
    };

    this.users.update(user.id, payload).subscribe({
      next: (updated) => {
        this.saving.set(false);
        this.user.set(updated);
        this.toast.success(`${updated.full_name} updated.`);
      },
      error: (error: ApiErrorBody) => {
        this.saving.set(false);
        this.formErrors.set(error.details ?? { first_name: error.message });
      },
    });
  }

  // -- account actions -----------------------------------------------------
  protected resetPassword(): void {
    const user = this.user();
    if (!user || this.isProtected()) return;
    if (!confirm(`Issue a new temporary password for ${user.full_name}?`)) return;

    this.users.resetPassword(user.id).subscribe((result) => {
      this.issuedPassword.set(result.temporary_password);
      this.toast.success('Password reset. Share the temporary password below.');
    });
  }

  protected toggleStatus(): void {
    const user = this.user();
    if (!user || this.isProtected()) return;
    const status: UserStatus = user.status === 'active' ? 'suspended' : 'active';

    this.users.update(user.id, { status }).subscribe((updated) => {
      this.user.set(updated);
      this.toast.success(`${updated.full_name} is now ${status}.`);
    });
  }

  protected remove(): void {
    const user = this.user();
    if (!user || this.isProtected()) return;
    if (!confirm(`Remove ${user.full_name}? Their attendance history is kept.`)) return;

    this.users.remove(user.id).subscribe(() => {
      this.toast.success(`${user.full_name} removed.`);
      this.router.navigateByUrl('/settings/people');
    });
  }

  protected dismissPassword(): void {
    this.issuedPassword.set(null);
  }
}
