import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiErrorBody } from '../../../core/models/api.model';
import { Organization } from '../../../core/models/user.model';
import { Organizations } from '../../../core/services/users';
import { Toast } from '../../../core/services/toast';

/**
 * Company profile: who the organization is and how to reach it.
 *
 * Deliberately narrow. This page used to also carry the working-hours policy
 * and the department list, which made it three unrelated jobs behind one
 * heading — changing an office phone number and changing how attendance is
 * graded are not the same kind of edit and should not share a Save button.
 * Those now live at /settings/work-policy and /settings/departments.
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

  protected readonly organization = signal<Organization | null>(null);
  protected readonly saving = signal(false);
  protected readonly formErrors = signal<Record<string, string>>({});

  protected readonly form = this.fb.nonNullable.group({
    name: ['', Validators.required],
    email: ['', [Validators.required, Validators.email]],
    phone: [''],
    city: [''],
    country: [''],
    timezone: ['Asia/Kolkata', Validators.required],
  });

  constructor() {
    this.organizations.current().subscribe((organization) => {
      this.organization.set(organization);
      this.form.patchValue({
        name: organization.name,
        email: organization.email,
        phone: organization.phone ?? '',
        city: organization.city ?? '',
        country: organization.country ?? '',
        timezone: organization.timezone,
      });
    });
  }

  protected save(): void {
    if (this.form.invalid || this.saving()) {
      this.form.markAllAsTouched();
      return;
    }

    this.saving.set(true);
    this.formErrors.set({});

    // A partial patch: the backend picks only the fields it is sent, so the
    // work-policy values this form does not carry are left untouched.
    this.organizations.update(this.form.getRawValue()).subscribe({
      next: (organization) => {
        this.saving.set(false);
        this.organization.set(organization);
        this.toast.success('Organization profile updated.');
      },
      error: (error: ApiErrorBody) => {
        this.saving.set(false);
        this.formErrors.set(error.details ?? {});
      },
    });
  }
}
