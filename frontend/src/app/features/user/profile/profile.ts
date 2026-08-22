import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiErrorBody } from '../../../core/models/api.model';
import { Auth } from '../../../core/services/auth';
import { Toast } from '../../../core/services/toast';
import { Users } from '../../../core/services/users';

/** Self-service: personal details and password. */
@Component({
  selector: 'app-profile',
  imports: [ReactiveFormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './profile.html',
})
export class Profile {
  private readonly users = inject(Users);
  private readonly toast = inject(Toast);
  private readonly fb = inject(FormBuilder);
  protected readonly auth = inject(Auth);

  protected readonly saving = signal(false);
  protected readonly changingPassword = signal(false);
  protected readonly profileErrors = signal<Record<string, string>>({});
  protected readonly passwordErrors = signal<Record<string, string>>({});

  protected readonly form = this.fb.nonNullable.group({
    first_name: ['', Validators.required],
    last_name: [''],
    phone: [''],
    designation: [''],
  });

  protected readonly passwordForm = this.fb.nonNullable.group({
    current_password: ['', Validators.required],
    new_password: ['', [Validators.required, Validators.minLength(8)]],
  });

  constructor() {
    this.users.profile().subscribe((user) => {
      this.form.patchValue({
        first_name: user.first_name,
        last_name: user.last_name ?? '',
        phone: user.phone ?? '',
        designation: user.designation ?? '',
      });
    });
  }

  protected save(): void {
    if (this.form.invalid || this.saving()) {
      this.form.markAllAsTouched();
      return;
    }

    this.saving.set(true);
    this.profileErrors.set({});

    this.users.updateProfile(this.form.getRawValue()).subscribe({
      next: (user) => {
        this.saving.set(false);
        this.auth.updateCurrentUser(user);
        this.toast.success('Profile updated.');
      },
      error: (error: ApiErrorBody) => {
        this.saving.set(false);
        this.profileErrors.set(error.details ?? {});
      },
    });
  }

  protected changePassword(): void {
    if (this.passwordForm.invalid || this.changingPassword()) {
      this.passwordForm.markAllAsTouched();
      return;
    }

    this.changingPassword.set(true);
    this.passwordErrors.set({});
    const { current_password, new_password } = this.passwordForm.getRawValue();

    this.auth.changePassword(current_password, new_password).subscribe({
      next: () => {
        this.changingPassword.set(false);
        this.toast.success('Password changed. Please sign in again.');
        // The API revokes every session on a password change.
        setTimeout(() => this.auth.logout(), 1200);
      },
      error: (error: ApiErrorBody) => {
        this.changingPassword.set(false);
        this.passwordErrors.set(error.details ?? { current_password: error.message });
      },
    });
  }
}
