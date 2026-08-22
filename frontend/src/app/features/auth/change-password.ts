import { AbstractControl, FormBuilder, ReactiveFormsModule, ValidationErrors, Validators } from '@angular/forms';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { ApiErrorBody } from '../../core/models/api.model';
import { Auth } from '../../core/services/auth';
import { Toast } from '../../core/services/toast';
import { Icon } from '../../shared/icon/icon';

/**
 * First-login password change.
 *
 * An employee provisioned by HR signs in with a system-generated password;
 * `passwordChangeGuard` sends them here until they have replaced it.  The API
 * revokes every session on success, so they sign in again afterwards.
 */
@Component({
  selector: 'app-change-password',
  imports: [ReactiveFormsModule, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './change-password.html',
  styleUrl: './auth-form.scss',
})
export class ChangePassword {
  private readonly router = inject(Router);
  private readonly toast = inject(Toast);
  private readonly fb = inject(FormBuilder);
  protected readonly auth = inject(Auth);

  protected readonly submitting = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly fieldErrors = signal<Record<string, string>>({});
  protected readonly showPassword = signal(false);

  protected readonly form = this.fb.nonNullable.group(
    {
      current_password: ['', Validators.required],
      new_password: ['', [Validators.required, Validators.minLength(8)]],
      confirm_password: ['', Validators.required],
    },
    { validators: passwordsMatch },
  );

  protected submit(): void {
    if (this.form.invalid || this.submitting()) {
      this.form.markAllAsTouched();
      return;
    }

    this.submitting.set(true);
    this.errorMessage.set(null);
    this.fieldErrors.set({});

    const { current_password, new_password } = this.form.getRawValue();

    this.auth.changePassword(current_password, new_password).subscribe({
      next: () => {
        this.submitting.set(false);
        this.toast.success('Password updated. Please sign in again.');
        this.auth.logout();
      },
      error: (error: ApiErrorBody) => {
        this.submitting.set(false);
        this.errorMessage.set(error.message ?? 'Could not change the password.');
        this.fieldErrors.set(error.details ?? {});
      },
    });
  }

  protected togglePassword(): void {
    this.showPassword.update((shown) => !shown);
  }

  protected signOut(): void {
    this.auth.logout();
  }

  protected get mismatch(): boolean {
    return this.form.hasError('passwordMismatch') && this.form.controls.confirm_password.touched;
  }
}

function passwordsMatch(group: AbstractControl): ValidationErrors | null {
  const password = group.get('new_password')?.value;
  const confirm = group.get('confirm_password')?.value;
  return !confirm || password === confirm ? null : { passwordMismatch: true };
}
