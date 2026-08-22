import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiErrorBody } from '../../../core/models/api.model';
import { Department, Organization } from '../../../core/models/user.model';
import { Organizations } from '../../../core/services/users';
import { Toast } from '../../../core/services/toast';

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

/**
 * Organization profile, working-hours policy and departments.
 *
 * The working-hours values here are what the attendance service uses to decide
 * late / half-day, so changing them changes how punches are graded.
 */
@Component({
  selector: 'app-organization-settings',
  imports: [ReactiveFormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './organization-settings.html',
})
export class OrganizationSettings {
  private readonly organizations = inject(Organizations);
  private readonly toast = inject(Toast);
  private readonly fb = inject(FormBuilder);

  protected readonly weekdays = WEEKDAYS;
  protected readonly organization = signal<Organization | null>(null);
  protected readonly departments = signal<Department[]>([]);
  protected readonly saving = signal(false);
  protected readonly formErrors = signal<Record<string, string>>({});

  protected readonly form = this.fb.nonNullable.group({
    name: ['', Validators.required],
    email: ['', [Validators.required, Validators.email]],
    phone: [''],
    city: [''],
    country: [''],
    timezone: ['Asia/Kolkata', Validators.required],
    work_start_time: ['09:30', Validators.required],
    work_end_time: ['18:30', Validators.required],
    full_day_hours: [8, [Validators.required, Validators.min(1), Validators.max(24)]],
    half_day_hours: [4, [Validators.required, Validators.min(1), Validators.max(24)]],
    late_grace_minutes: [15, [Validators.required, Validators.min(0)]],
  });

  protected readonly departmentForm = this.fb.nonNullable.group({
    name: ['', Validators.required],
    code: [''],
  });

  /** Working days as a signal so the checkbox row stays in sync. */
  protected readonly workingDays = signal<number[]>([0, 1, 2, 3, 4]);

  constructor() {
    this.load();
  }

  private load(): void {
    this.organizations.current().subscribe((organization) => {
      this.organization.set(organization);
      this.workingDays.set(organization.working_days ?? []);
      this.form.patchValue({
        name: organization.name,
        email: organization.email,
        phone: organization.phone ?? '',
        city: organization.city ?? '',
        country: organization.country ?? '',
        timezone: organization.timezone,
        work_start_time: organization.work_start_time,
        work_end_time: organization.work_end_time,
        full_day_hours: organization.full_day_hours,
        half_day_hours: organization.half_day_hours,
        late_grace_minutes: organization.late_grace_minutes,
      });
    });

    this.organizations.departments({ page_size: 100 }).subscribe((page) => {
      this.departments.set(page.items);
    });
  }

  protected toggleDay(day: number): void {
    this.workingDays.update((days) =>
      days.includes(day) ? days.filter((d) => d !== day) : [...days, day].sort(),
    );
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
          this.toast.success('Organization updated.');
        },
        error: (error: ApiErrorBody) => {
          this.saving.set(false);
          this.formErrors.set(error.details ?? {});
        },
      });
  }

  // -- departments -------------------------------------------------------
  protected addDepartment(): void {
    if (this.departmentForm.invalid) {
      this.departmentForm.markAllAsTouched();
      return;
    }
    this.organizations.createDepartment(this.departmentForm.getRawValue()).subscribe({
      next: (department) => {
        this.departments.update((list) => [...list, department]);
        this.departmentForm.reset({ name: '', code: '' });
        this.toast.success('Department added.');
      },
      error: (error: ApiErrorBody) => this.formErrors.set({ department: error.message }),
    });
  }

  protected removeDepartment(department: Department): void {
    if (!confirm(`Remove the ${department.name} department?`)) return;
    this.organizations.removeDepartment(department.id).subscribe(() => {
      this.departments.update((list) => list.filter((item) => item.id !== department.id));
      this.toast.success('Department removed.');
    });
  }
}
