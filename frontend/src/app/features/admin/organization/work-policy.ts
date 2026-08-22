import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiErrorBody } from '../../../core/models/api.model';
import { Organization } from '../../../core/models/user.model';
import { Organizations } from '../../../core/services/users';
import { Toast } from '../../../core/services/toast';
import { Icon } from '../../../shared/icon/icon';

/** Monday-first, matching the backend's 0-6 encoding. */
const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

/**
 * The rules attendance is graded against.
 *
 * Split out of the organization profile because these values are not
 * descriptive — they are policy. Every punch already recorded is re-read
 * through them, so moving the shift start by ten minutes changes who counts as
 * late on days that have already happened. That deserves its own page and its
 * own warning, rather than sitting under a company phone number.
 */
@Component({
  selector: 'app-work-policy',
  imports: [ReactiveFormsModule, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './work-policy.html',
  styleUrl: './work-policy.scss',
})
export class WorkPolicy {
  private readonly organizations = inject(Organizations);
  private readonly toast = inject(Toast);
  private readonly fb = inject(FormBuilder);

  protected readonly weekdays = WEEKDAYS;
  protected readonly organization = signal<Organization | null>(null);
  protected readonly saving = signal(false);
  protected readonly formErrors = signal<Record<string, string>>({});

  protected readonly form = this.fb.nonNullable.group({
    work_start_time: ['09:30', Validators.required],
    work_end_time: ['18:30', Validators.required],
    full_day_hours: [8, [Validators.required, Validators.min(1), Validators.max(24)]],
    half_day_hours: [4, [Validators.required, Validators.min(1), Validators.max(24)]],
    late_grace_minutes: [15, [Validators.required, Validators.min(0)]],
  });

  /** Working days as a signal, so the day toggles stay in sync with the form. */
  protected readonly workingDays = signal<number[]>([0, 1, 2, 3, 4]);

  constructor() {
    this.organizations.current().subscribe((organization) => {
      this.organization.set(organization);
      this.workingDays.set(organization.working_days ?? []);
      this.form.patchValue({
        work_start_time: organization.work_start_time,
        work_end_time: organization.work_end_time,
        full_day_hours: organization.full_day_hours,
        half_day_hours: organization.half_day_hours,
        late_grace_minutes: organization.late_grace_minutes,
      });
    });
  }

  protected toggleDay(day: number): void {
    this.workingDays.update((days) =>
      days.includes(day) ? days.filter((d) => d !== day) : [...days, day].sort(),
    );
  }

  protected isWorking(day: number): boolean {
    return this.workingDays().includes(day);
  }

  protected save(): void {
    if (this.form.invalid || this.saving()) {
      this.form.markAllAsTouched();
      return;
    }

    this.saving.set(true);
    this.formErrors.set({});

    this.organizations
      .update({ ...this.form.getRawValue(), working_days: this.workingDays() })
      .subscribe({
        next: (organization) => {
          this.saving.set(false);
          this.organization.set(organization);
          this.toast.success('Work policy updated.');
        },
        error: (error: ApiErrorBody) => {
          this.saving.set(false);
          this.formErrors.set(error.details ?? {});
        },
      });
  }
}
