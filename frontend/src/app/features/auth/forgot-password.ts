import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ApiErrorBody } from '../../core/models/api.model';
import { Auth } from '../../core/services/auth';

/**
 * Self-service "forgot password".  The response is identical whether or not
 * the account exists - see `services.request_password_reset` - so this page
 * always shows the same generic confirmation, never an error tied to a
 * specific identifier.
 */
@Component({
  selector: 'app-forgot-password',
  imports: [ReactiveFormsModule, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './forgot-password.html',
  styleUrl: './auth-form.scss',
})
export class ForgotPassword {
  private readonly auth = inject(Auth);
  private readonly fb = inject(FormBuilder);

  protected readonly submitting = signal(false);
  protected readonly sent = signal(false);
  protected readonly errorMessage = signal<string | null>(null);

  protected readonly form = this.fb.nonNullable.group({
    identifier: ['', [Validators.required, Validators.minLength(3)]],
  });

  protected submit(): void {
    if (this.form.invalid || this.submitting()) {
      this.form.markAllAsTouched();
      return;
    }

    this.submitting.set(true);
    this.errorMessage.set(null);
    this.auth.forgotPassword(this.form.getRawValue().identifier).subscribe({
      // A 200 here never means "the account exists" - see the class doc.
      next: () => {
        this.submitting.set(false);
        this.sent.set(true);
      },
      // A genuine failure (rate-limited, server error) is safe to surface as
      // itself: the message is the same regardless of whether the identifier
      // maps to a real account, so it cannot be used to enumerate accounts.
      error: (error: ApiErrorBody) => {
        this.submitting.set(false);
        this.errorMessage.set(error.message ?? 'Something went wrong. Try again shortly.');
      },
    });
  }
}
