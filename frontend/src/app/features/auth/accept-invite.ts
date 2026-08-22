import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ApiErrorBody } from '../../core/models/api.model';
import { Auth } from '../../core/services/auth';
import { Toast } from '../../core/services/toast';
import { Icon } from '../../shared/icon/icon';
import { Logo } from '../../shared/logo/logo';

@Component({
  selector: 'app-accept-invite',
  imports: [ReactiveFormsModule, RouterLink, Icon, Logo],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './accept-invite.html',
  styleUrl: './auth-form.scss',
})
export class AcceptInvite implements OnInit {
  private readonly auth = inject(Auth);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly fb = inject(FormBuilder);
  private readonly toast = inject(Toast);

  readonly loading = signal(true);
  readonly token = signal<string>('');
  readonly inviteData = signal<any>(null);
  readonly errorMessage = signal<string | null>(null);
  readonly submitting = signal(false);
  readonly fieldErrors = signal<Record<string, string>>({});
  readonly showPassword = signal(false);

  readonly form = this.fb.nonNullable.group({
    password: ['', [Validators.required, Validators.minLength(8)]],
    confirm_password: ['', [Validators.required]],
    first_name: [''],
    last_name: [''],
    phone: [''],
  });

  ngOnInit(): void {
    const token = this.route.snapshot.queryParamMap.get('token') || '';
    this.token.set(token);

    if (!token) {
      this.errorMessage.set('Missing invitation token.');
      this.loading.set(false);
      return;
    }

    this.auth.getInviteDetails(token).subscribe({
      next: (data) => {
        this.inviteData.set(data);
        this.form.patchValue({
          first_name: data.first_name || '',
          last_name: data.last_name || '',
        });
        this.loading.set(false);
      },
      error: (err) => {
        this.errorMessage.set(err?.error?.message || 'Invalid or expired invitation token.');
        this.loading.set(false);
      },
    });
  }

  submit(): void {
    if (this.form.invalid || this.submitting()) {
      this.form.markAllAsTouched();
      return;
    }

    const { password, confirm_password, first_name, last_name, phone } = this.form.getRawValue();
    if (password !== confirm_password) {
      this.fieldErrors.set({ confirm_password: 'Passwords do not match.' });
      return;
    }

    this.submitting.set(true);
    this.errorMessage.set(null);
    this.fieldErrors.set({});

    this.auth.acceptInvite(this.token(), { password, first_name, last_name, phone }).subscribe({
      next: () => {
        this.submitting.set(false);
        this.toast.success('Welcome to HRMS Portal!');
        this.router.navigate(['/employees']);
      },
      error: (error: ApiErrorBody) => {
        this.submitting.set(false);
        this.errorMessage.set(error.message);
        this.fieldErrors.set(error.details ?? {});
      },
    });
  }

  toggleShowPassword(): void {
    this.showPassword.update((v) => !v);
  }
}
