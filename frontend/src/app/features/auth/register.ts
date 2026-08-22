import { AbstractControl, FormBuilder, ReactiveFormsModule, ValidationErrors, Validators } from '@angular/forms';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { ApiErrorBody } from '../../core/models/api.model';
import { Auth } from '../../core/services/auth';
import { Toast } from '../../core/services/toast';
import { Icon } from '../../shared/icon/icon';
import { Logo } from '../../shared/logo/logo';

const MAX_LOGO_BYTES = 2 * 1024 * 1024;

/**
 * Organization signup - the bootstrap path.
 *
 * Creates the organization (with an optional logo) and its first super admin in
 * one call.  Every other account is created from the admin panel's employee
 * directory; a normal employee never registers themselves.
 */
@Component({
  selector: 'app-register',
  imports: [ReactiveFormsModule, RouterLink, Icon, Logo],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './register.html',
  styleUrl: './auth-form.scss',
})
export class Register {
  private readonly auth = inject(Auth);
  private readonly router = inject(Router);
  private readonly toast = inject(Toast);
  private readonly fb = inject(FormBuilder);

  protected readonly submitting = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly fieldErrors = signal<Record<string, string>>({});
  protected readonly showPassword = signal(false);
  protected readonly showConfirm = signal(false);

  /** Chosen logo plus a local preview; uploaded with the signup request. */
  protected readonly logo = signal<File | null>(null);
  protected readonly logoPreview = signal<string | null>(null);

  protected readonly form = this.fb.nonNullable.group(
    {
      organization_name: ['', [Validators.required, Validators.minLength(2)]],
      name: ['', [Validators.required, Validators.minLength(2)]],
      email: ['', [Validators.required, Validators.email]],
      phone: [''],
      password: ['', [Validators.required, Validators.minLength(8)]],
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

    this.auth.register(this.form.getRawValue(), this.logo()).subscribe({
      next: (result) => {
        this.submitting.set(false);
        // The login ID is generated server-side; show it, because it is what
        // they will sign in with from now on.
        this.toast.success(`Welcome aboard. Your login ID is ${result.user.login_id}`);
        this.router.navigateByUrl(this.auth.homeRoute());
      },
      error: (error: ApiErrorBody) => {
        this.submitting.set(false);
        this.errorMessage.set(error.message ?? 'Unable to create the organization.');
        this.fieldErrors.set(error.details ?? {});
      },
    });
  }

  // -- logo --------------------------------------------------------------
  protected pickLogo(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    if (!file) return;

    if (!file.type.startsWith('image/')) {
      this.fieldErrors.update((errors) => ({ ...errors, logo: 'Choose an image file.' }));
      input.value = '';
      return;
    }
    if (file.size > MAX_LOGO_BYTES) {
      this.fieldErrors.update((errors) => ({ ...errors, logo: 'Maximum size is 2 MB.' }));
      input.value = '';
      return;
    }

    this.fieldErrors.update(({ logo: _removed, ...rest }) => rest);
    this.logo.set(file);

    const reader = new FileReader();
    reader.onload = () => this.logoPreview.set(reader.result as string);
    reader.readAsDataURL(file);
  }

  protected clearLogo(): void {
    this.logo.set(null);
    this.logoPreview.set(null);
  }

  // -- helpers -----------------------------------------------------------
  protected togglePassword(): void {
    this.showPassword.update((shown) => !shown);
  }

  protected toggleConfirm(): void {
    this.showConfirm.update((shown) => !shown);
  }

  protected invalid(control: keyof typeof this.form.controls): boolean {
    const field = this.form.controls[control];
    return field.touched && field.invalid;
  }

  protected get mismatch(): boolean {
    return (
      this.form.hasError('passwordMismatch') && this.form.controls.confirm_password.touched
    );
  }
}

/** Cross-field rule: the two password boxes must agree. */
function passwordsMatch(group: AbstractControl): ValidationErrors | null {
  const password = group.get('password')?.value;
  const confirm = group.get('confirm_password')?.value;
  return !confirm || password === confirm ? null : { passwordMismatch: true };
}
