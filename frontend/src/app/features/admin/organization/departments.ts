import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiErrorBody } from '../../../core/models/api.model';
import { Department } from '../../../core/models/user.model';
import { DepartmentHeadcount, Organizations } from '../../../core/services/users';
import { Toast } from '../../../core/services/toast';
import { Icon } from '../../../shared/icon/icon';

/**
 * Departments, on their own page.
 *
 * Previously a side card on the organization screen, where the list had room
 * for a name and a Remove button and nothing else. Given the full width it can
 * show headcount and support renaming — `PATCH /departments/:id` has been live
 * all along with nothing calling it, so a typo in a department name was
 * previously only fixable by deleting it and orphaning everyone in it.
 */
@Component({
  selector: 'app-departments',
  imports: [ReactiveFormsModule, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './departments.html',
  styleUrl: './departments.scss',
})
export class Departments {
  private readonly organizations = inject(Organizations);
  private readonly toast = inject(Toast);
  private readonly fb = inject(FormBuilder);

  protected readonly departments = signal<Department[]>([]);
  protected readonly headcount = signal<Record<string, number>>({});
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly formErrors = signal<Record<string, string>>({});
  /** Which row is in edit mode; only ever one at a time. */
  protected readonly editingId = signal<string | null>(null);

  protected readonly form = this.fb.nonNullable.group({
    name: ['', Validators.required],
    code: [''],
  });

  protected readonly editForm = this.fb.nonNullable.group({
    name: ['', Validators.required],
    code: [''],
  });

  constructor() {
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    this.organizations.departments({ page_size: 100 }).subscribe({
      next: (page) => {
        this.departments.set(page.items);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });

    // Headcount comes from the org overview rather than the department list,
    // which does not carry it. A failure here is not worth a toast: the page
    // is still fully usable without the counts.
    this.organizations.overview().subscribe({
      next: (result) => {
        const counts: Record<string, number> = {};
        for (const row of (result.departments ?? []) as DepartmentHeadcount[]) {
          counts[row.department_id] = row.headcount;
        }
        this.headcount.set(counts);
      },
      error: () => {},
    });
  }

  protected countFor(department: Department): number {
    return this.headcount()[department.id] ?? 0;
  }

  // -- create --------------------------------------------------------------
  protected add(): void {
    if (this.form.invalid || this.saving()) {
      this.form.markAllAsTouched();
      return;
    }

    this.saving.set(true);
    this.formErrors.set({});

    this.organizations.createDepartment(this.form.getRawValue()).subscribe({
      next: (department) => {
        this.saving.set(false);
        this.departments.update((list) => [...list, department]);
        this.form.reset({ name: '', code: '' });
        this.toast.success(`${department.name} added.`);
      },
      error: (error: ApiErrorBody) => {
        this.saving.set(false);
        this.formErrors.set(error.details ?? { name: error.message });
      },
    });
  }

  // -- rename --------------------------------------------------------------
  protected startEdit(department: Department): void {
    this.editingId.set(department.id);
    this.editForm.reset({ name: department.name, code: department.code ?? '' });
    this.formErrors.set({});
  }

  protected cancelEdit(): void {
    this.editingId.set(null);
    this.formErrors.set({});
  }

  protected saveEdit(department: Department): void {
    if (this.editForm.invalid || this.saving()) {
      this.editForm.markAllAsTouched();
      return;
    }

    this.saving.set(true);
    this.organizations.updateDepartment(department.id, this.editForm.getRawValue()).subscribe({
      next: (updated) => {
        this.saving.set(false);
        this.editingId.set(null);
        this.departments.update((list) =>
          list.map((item) => (item.id === updated.id ? updated : item)),
        );
        this.toast.success('Department renamed.');
      },
      error: (error: ApiErrorBody) => {
        this.saving.set(false);
        this.formErrors.set(error.details ?? { name: error.message });
      },
    });
  }

  // -- remove --------------------------------------------------------------
  protected remove(department: Department): void {
    const count = this.countFor(department);
    const warning = count
      ? `\n\n${count} ${count === 1 ? 'person is' : 'people are'} in it and will be left without a department.`
      : '';
    if (!confirm(`Remove the ${department.name} department?${warning}`)) return;

    this.organizations.removeDepartment(department.id).subscribe(() => {
      this.departments.update((list) => list.filter((item) => item.id !== department.id));
      this.toast.success(`${department.name} removed.`);
    });
  }
}
