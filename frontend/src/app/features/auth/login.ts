import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ApiErrorBody } from '../../core/models/api.model';
import { Auth } from '../../core/services/auth';
import { Icon } from '../../shared/icon/icon';

/**
 * Sign-in page for both panels.
 *
 * One field accepts either the system-issued login ID (OIJODO20220001) or an
 * email address.  After authenticating, the user's role decides which panel
 * they land on - there is no separate admin login.
 */
@Component({
  selector: 'app-login',
  imports: [ReactiveFormsModule, RouterLink, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './login.html',
  styleUrl: './auth-form.scss',
})
export class Login {
  private readonly auth = inject(Auth);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly fb = inject(FormBuilder);

  protected readonly submitting = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly fieldErrors = signal<Record<string, string>>({});
  protected readonly showPassword = signal(false);

  protected readonly form = this.fb.nonNullable.group({
    identifier: ['', [Validators.required, Validators.minLength(3)]],
    password: ['', [Validators.required, Validators.minLength(8)]],
  });

  protected submit(): void {
    if (this.form.invalid || this.submitting()) {
      this.form.markAllAsTouched();
      return;
    }

    this.submitting.set(true);
    this.errorMessage.set(null);
    this.fieldErrors.set({});

    const { identifier, password } = this.form.getRawValue();

    this.auth.login(identifier, password).subscribe({
      next: (result) => {
        this.submitting.set(false);
        // A system-generated password has to be replaced before anything else.
        if (result.user.must_change_password) {
          this.router.navigate(['/change-password']);
          return;
        }
        // Honour ?redirect= when a guard sent them here, otherwise use the
        // panel their role belongs to.
        const redirect = this.route.snapshot.queryParamMap.get('redirect');
        this.router.navigateByUrl(redirect || this.auth.homeRoute());
      },
      error: (error: ApiErrorBody) => {
        this.submitting.set(false);
        this.errorMessage.set(error.message ?? 'Unable to sign in.');
        this.fieldErrors.set(error.details ?? {});
      },
    });
  }

  protected togglePassword(): void {
    this.showPassword.update((shown) => !shown);
  }

  /** Fills the form with a seeded demo account (`manage.py seed_demo`). */
  protected useDemo(role: 'admin' | 'employee'): void {
    this.form.setValue({
      identifier: role === 'admin' ? 'admin@acme.test' : 'dev@acme.test',
      password: 'Password123',
    });
  }

  protected invalid(control: 'identifier' | 'password'): boolean {
    const field = this.form.controls[control];
    return field.touched && field.invalid;
  }
}
