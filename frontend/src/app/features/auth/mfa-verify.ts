import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ApiErrorBody } from '../../core/models/api.model';
import { Auth } from '../../core/services/auth';

/**
 * Second login step for an MFA-enabled account.
 *
 * Reached only mid-login, right after `Login` gets `mfa_required: true` back -
 * there is no session yet, only the narrow `mfa_pending_token` `Auth` is
 * holding in memory. Refreshing this page loses that token by design (it is
 * never persisted), which sends the user back to sign in rather than leaving
 * a half-authenticated state lying around.
 */
@Component({
  selector: 'app-mfa-verify',
  imports: [ReactiveFormsModule, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './mfa-verify.html',
  styleUrl: './auth-form.scss',
})
export class MfaVerify {
  private readonly auth = inject(Auth);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly fb = inject(FormBuilder);

  protected readonly submitting = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly hasChallenge = computed(() => this.auth.mfaPending());

  protected readonly form = this.fb.nonNullable.group({
    code: ['', [Validators.required, Validators.minLength(6)]],
  });

  protected submit(): void {
    if (this.form.invalid || this.submitting()) {
      this.form.markAllAsTouched();
      return;
    }

    this.submitting.set(true);
    this.errorMessage.set(null);

    this.auth.verifyMfa(this.form.getRawValue().code.trim()).subscribe({
      next: (result) => {
        this.submitting.set(false);
        if (result.user!.must_change_password) {
          this.router.navigate(['/change-password']);
          return;
        }
        const redirect = this.route.snapshot.queryParamMap.get('redirect');
        this.router.navigateByUrl(redirect || this.auth.homeRoute());
      },
      error: (error: ApiErrorBody) => {
        this.submitting.set(false);
        this.errorMessage.set(error.message ?? 'Invalid code.');
        this.form.controls.code.setValue('');
      },
    });
  }

  protected cancel(): void {
    this.auth.cancelMfaChallenge();
    this.router.navigate(['/auth/login']);
  }
}
