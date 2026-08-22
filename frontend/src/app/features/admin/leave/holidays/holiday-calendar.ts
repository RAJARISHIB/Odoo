import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { ApiErrorBody } from '../../../../core/models/api.model';
import { HOLIDAY_TYPE_LABELS, Holiday, HolidayType } from '../../../../core/models/leaves.model';
import { Leaves } from '../../../../core/services/leaves';
import { Realtime } from '../../../../core/services/realtime';
import { Toast } from '../../../../core/services/toast';

/** Admin holiday calendar: government, festival, company and optional holidays. */
@Component({
  selector: 'app-holiday-calendar',
  imports: [ReactiveFormsModule, DatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './holiday-calendar.html',
})
export class HolidayCalendar {
  private readonly leaves = inject(Leaves);
  private readonly realtime = inject(Realtime);
  private readonly toast = inject(Toast);
  private readonly fb = inject(FormBuilder);

  protected readonly typeLabels = HOLIDAY_TYPE_LABELS;
  protected readonly types: HolidayType[] = ['government', 'festival', 'organization', 'optional'];

  protected readonly holidays = signal<Holiday[]>([]);
  protected readonly loading = signal(false);
  protected readonly year = signal(new Date().getFullYear());
  protected readonly todayStr = new Date().toISOString().slice(0, 10);

  protected readonly showForm = signal(false);
  protected readonly editingId = signal<string | null>(null);
  protected readonly saving = signal(false);
  protected readonly formErrors = signal<Record<string, string>>({});

  protected readonly form = this.fb.nonNullable.group({
    name: ['', Validators.required],
    date: ['', Validators.required],
    type: ['government' as HolidayType, Validators.required],
    description: [''],
  });

  constructor() {
    this.load();
    this.realtime
      .onAny(['holiday.updated'])
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.load());
  }

  protected load(): void {
    this.loading.set(true);
    this.leaves.getHolidays({ start_date: `${this.year()}-01-01`, end_date: `${this.year()}-12-31` }).subscribe({
      next: (holidays) => {
        this.holidays.set(holidays);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  protected changeYear(delta: number): void {
    this.year.update((y) => y + delta);
    this.load();
  }

  protected isPast(holiday: Holiday): boolean {
    return holiday.date < this.todayStr;
  }

  protected toggleForm(holiday?: Holiday): void {
    this.formErrors.set({});
    if (holiday) {
      this.editingId.set(holiday.id);
      this.form.reset({
        name: holiday.name,
        date: holiday.date,
        type: holiday.type,
        description: holiday.description ?? '',
      });
      this.showForm.set(true);
    } else {
      this.editingId.set(null);
      this.form.reset({ type: 'government' });
      this.showForm.update((open) => !open);
    }
  }

  protected save(): void {
    if (this.form.invalid || this.saving()) {
      this.form.markAllAsTouched();
      return;
    }

    this.saving.set(true);
    this.formErrors.set({});
    const payload = this.form.getRawValue();
    const editingId = this.editingId();

    const request = editingId ? this.leaves.updateHoliday(editingId, payload) : this.leaves.createHoliday(payload);
    request.subscribe({
      next: (holiday) => {
        this.saving.set(false);
        this.toast.success(`${holiday.name} saved.`);
        this.showForm.set(false);
        this.editingId.set(null);
        this.load();
      },
      error: (error: ApiErrorBody) => {
        this.saving.set(false);
        this.formErrors.set(error.details ?? { date: error.message });
      },
    });
  }
}
