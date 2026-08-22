import { AbstractControl, FormBuilder, ReactiveFormsModule, ValidationErrors, Validators } from '@angular/forms';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ApiErrorBody } from '../../core/models/api.model';
import { Auth } from '../../core/services/auth';
import { Toast } from '../../core/services/toast';
import { Icon } from '../../shared/icon/icon';

/** Landing page for the link in the password-reset email (`?token=...`). */
@Component({
  selector: 'app-reset-password',
  imports: [ReactiveFormsModule, RouterLink, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './reset-password.html',
  styleUrl: './auth-form.scss',
})
export class ResetPassword {
  private readonly auth = inject(Auth);
  private readonly router = inject(Router);
  private readonly toast = inject(Toast);
  private readonly fb = inject(FormBuilder);

  protected readonly token = inject(ActivatedRoute).snapshot.queryParamMap.get('token') ?? '';
  protected readonly submitting = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly fieldErrors = signal<Record<string, string>>({});
  protected readonly showPassword = signal(false);

  protected readonly form = this.fb.nonNullable.group(
    {
      new_password: ['', [Validators.required, Validators.minLength(8)]],
      confirm_password: ['', Validators.required],
    },
    { validators: passwordsMatch },
  );

  protected submit(): void {
    if (!this.token || this.form.invalid || this.submitting()) {
      this.form.markAllAsTouched();
      return;
    }

    this.submitting.set(true);
    this.errorMessage.set(null);
    this.fieldErrors.set({});

    this.auth.resetPassword(this.token, this.form.getRawValue().new_password).subscribe({
      next: () => {
        this.submitting.set(false);
        this.toast.success('Password reset. Please sign in with your new password.');
        this.router.navigate(['/auth/login']);
      },
      error: (error: ApiErrorBody) => {
        this.submitting.set(false);
        this.errorMessage.set(error.message ?? 'Could not reset the password.');
        this.fieldErrors.set(error.details ?? {});
      },
    });
  }

  protected togglePassword(): void {
    this.showPassword.update((shown) => !shown);
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
