import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import {
  FormBuilder,
  FormGroup,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';

import { ApiErrorBody } from '../../../core/models/api.model';
import {
  CalendarFeed,
  Holiday,
  LeaveBalance,
  LeaveRequest,
  LeaveType,
  LeaveTypeBalance,
} from '../../../core/models/leaves.model';
import { Leaves } from '../../../core/services/leaves';
import { Toast } from '../../../core/services/toast';
import { Icon } from '../../../shared/icon/icon';
import type { IconName } from '../../../shared/icon/icons';

/** One line in the small-screen agenda beneath the month grid. */
export interface AgendaEntry {
  key: string;
  date: Date;
  isToday: boolean;
  /** Matches the grid's event-badge modifiers, so both read the same colour. */
  kind: 'govt' | 'org' | 'approved' | 'pending';
  icon: IconName;
  title: string;
  detail: string;
}

export interface CalendarDay {
  date: Date;
  dateStr: string;
  dayNumber: number;
  isCurrentMonth: boolean;
  isToday: boolean;
  isPast: boolean;
  holidays: Holiday[];
  leaves: LeaveRequest[];
}

@Component({
  selector: 'app-user-calendar',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './calendar.html',
  styleUrl: './calendar.scss',
})
export class UserCalendar implements OnInit {
  private readonly leavesService = inject(Leaves);
  private readonly toast = inject(Toast);
  private readonly fb = inject(FormBuilder);

  // Month navigation signal (first of current month)
  protected readonly currentMonth = signal<Date>(this.getStartOfMonth(new Date()));
  protected readonly calendarFeed = signal<CalendarFeed | null>(null);
  protected readonly loading = signal<boolean>(true);
  protected readonly submitting = signal<boolean>(false);
  protected readonly showModal = signal<boolean>(false);
  protected readonly formErrors = signal<Record<string, string>>({});

  /** Leave types + this employee's own per-type balance - loaded once so the
   * apply modal can show "you have X days left" before submitting, and block
   * obviously-too-large requests client-side (the backend remains the
   * authority; this is a preview). */
  protected readonly leaveTypes = signal<LeaveType[]>([]);
  protected readonly typeBalances = signal<LeaveTypeBalance[]>([]);

  protected readonly applyForm: FormGroup = this.fb.group({
    leave_type_id: ['', Validators.required],
    start_date: ['', Validators.required],
    end_date: ['', Validators.required],
    reason: ['', [Validators.required, Validators.maxLength(1000)]],
  });

  private readonly applyFormValue = toSignal(this.applyForm.valueChanges, {
    initialValue: this.applyForm.getRawValue(),
  });

  /** The remaining balance for whichever leave type is currently selected. */
  protected readonly selectedTypeBalance = computed<LeaveTypeBalance | null>(() => {
    const typeId = this.applyFormValue()?.leave_type_id;
    if (!typeId) return null;
    return this.typeBalances().find((b) => b.leave_type_id === typeId) ?? null;
  });

  /** Calendar-day span of the currently entered dates - a client-side preview
   * only; the backend is always the authority on the final day count. */
  protected readonly requestedDays = computed<number>(() => {
    const value = this.applyFormValue();
    if (!value?.start_date || !value?.end_date) return 0;
    const start = new Date(value.start_date);
    const end = new Date(value.end_date);
    if (end < start) return 0;
    return Math.round((end.getTime() - start.getTime()) / 86_400_000) + 1;
  });

  protected readonly exceedsBalance = computed<boolean>(() => {
    const balance = this.selectedTypeBalance();
    if (!balance) return false;
    return this.requestedDays() > balance.remaining;
  });

  // Derived Month Title (e.g. "August 2026")
  protected readonly monthTitle = computed(() => {
    return this.currentMonth().toLocaleDateString('en-US', {
      month: 'long',
      year: 'numeric',
    });
  });

  // Derived Leave Balance
  protected readonly balance = computed<LeaveBalance | null>(() => {
    return this.calendarFeed()?.balance ?? null;
  });

  /**
   * Flat, date-ordered list of everything happening in the visible month.
   *
   * The month grid is the primary view, but seven columns in a 375px viewport
   * leave a ~45px day cell — too narrow for an event's name, and `title`
   * tooltips do not exist on touch, so the grid alone would hide holidays
   * behind a coloured dot with no way to read them. Below the table
   * breakpoint the grid shows dots and this list carries the detail.
   *
   * Derived from `calendarDays()` rather than the raw feed so it inherits the
   * same current-month filtering and stays in step with what the grid marks.
   */
  protected readonly agenda = computed<AgendaEntry[]>(() =>
    this.calendarDays()
      .filter((day) => day.isCurrentMonth && (day.holidays.length || day.leaves.length))
      .flatMap((day) => [
        ...day.holidays.map(
          (holiday): AgendaEntry => ({
            key: `h-${holiday.id}`,
            date: day.date,
            isToday: day.isToday,
            kind: holiday.type === 'government' ? 'govt' : 'org',
            icon: holiday.type === 'government' ? 'building' : 'briefcase',
            title: holiday.name,
            detail: holiday.description ?? '',
          }),
        ),
        ...day.leaves.map(
          (leave): AgendaEntry => ({
            key: `l-${leave.id}-${day.dateStr}`,
            date: day.date,
            isToday: day.isToday,
            kind: leave.status === 'APPROVED' ? 'approved' : 'pending',
            icon: 'calendar',
            title: `Leave (${leave.status})`,
            detail: leave.reason ?? '',
          }),
        ),
      ]),
  );

  // Derived Calendar Days Matrix (42 days for 6-week grid)
  protected readonly calendarDays = computed<CalendarDay[]>(() => {
    const feed = this.calendarFeed();
    const activeMonth = this.currentMonth();
    const year = activeMonth.getFullYear();
    const month = activeMonth.getMonth();

    const todayStr = this.formatDateStr(new Date());

    // First day of month and day of week (0=Sunday)
    const firstDay = new Date(year, month, 1);
    const startingDayOfWeek = firstDay.getDay(); // 0 is Sunday

    // We start grid from Sunday
    const startDate = new Date(year, month, 1 - startingDayOfWeek);

    const holidaysMap = new Map<string, Holiday[]>();
    (feed?.holidays ?? []).forEach((h) => {
      const list = holidaysMap.get(h.date) || [];
      list.push(h);
      holidaysMap.set(h.date, list);
    });

    const leavesList = feed?.leaves ?? [];

    const days: CalendarDay[] = [];

    for (let i = 0; i < 42; i++) {
      const d = new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate() + i);
      const dateStr = this.formatDateStr(d);
      const isCurrentMonth = d.getMonth() === month;
      const isToday = dateStr === todayStr;
      const isPast = d < new Date(new Date().setHours(0, 0, 0, 0));

      const dayHolidays = holidaysMap.get(dateStr) || [];
      const dayLeaves = leavesList.filter(
        (l) => l.start_date <= dateStr && l.end_date >= dateStr
      );

      days.push({
        date: d,
        dateStr,
        dayNumber: d.getDate(),
        isCurrentMonth,
        isToday,
        isPast,
        holidays: dayHolidays,
        leaves: dayLeaves,
      });
    }

    return days;
  });

  // Derived User's Recent Leave Requests
  protected readonly myRequests = computed<LeaveRequest[]>(() => {
    return this.calendarFeed()?.leaves ?? [];
  });

  ngOnInit(): void {
    this.loadCalendar();
    this.leavesService.types({ active_only: 'true' }).subscribe((types) => this.leaveTypes.set(types));
    this.loadTypeBalances();
  }

  private loadTypeBalances(): void {
    this.leavesService.getTypeBalances().subscribe((balances) => this.typeBalances.set(balances));
  }

  protected prevMonth(): void {
    const cur = this.currentMonth();
    this.currentMonth.set(new Date(cur.getFullYear(), cur.getMonth() - 1, 1));
    this.loadCalendar();
  }

  protected nextMonth(): void {
    const cur = this.currentMonth();
    this.currentMonth.set(new Date(cur.getFullYear(), cur.getMonth() + 1, 1));
    this.loadCalendar();
  }

  protected todayMonth(): void {
    this.currentMonth.set(this.getStartOfMonth(new Date()));
    this.loadCalendar();
  }

  protected openApplyModal(dateStr?: string): void {
    this.formErrors.set({});
    const initialDate = dateStr ?? this.formatDateStr(new Date());

    this.applyForm.reset({
      leave_type_id: '',
      start_date: initialDate,
      end_date: initialDate,
      reason: '',
    });

    this.showModal.set(true);
  }

  protected closeApplyModal(): void {
    this.showModal.set(false);
    this.formErrors.set({});
  }

  protected selectDay(day: CalendarDay): void {
    if (!day.isCurrentMonth) return;
    this.openApplyModal(day.dateStr);
  }

  protected submitLeaveApplication(): void {
    if (this.applyForm.invalid) {
      this.applyForm.markAllAsTouched();
      return;
    }

    this.formErrors.set({});
    this.submitting.set(true);

    const val = this.applyForm.value;

    this.leavesService.applyLeave({
      leave_type_id: val.leave_type_id,
      start_date: val.start_date,
      end_date: val.end_date,
      reason: val.reason,
    }).subscribe({
      next: (res) => {
        this.submitting.set(false);
        this.toast.success(`Leave request submitted (${res.status}).`);
        this.closeApplyModal();
        this.loadCalendar();
        this.loadTypeBalances();
      },
      error: (err: ApiErrorBody) => {
        this.submitting.set(false);
        // The interceptor normalises every HTTP failure into `ApiErrorBody`,
        // so the per-field messages (e.g. "insufficient balance" on
        // `end_date`) are already flat here - no `.error.error` nesting.
        const details = err.details || {};
        const mainMsg = err.message || 'Failed to submit leave request.';
        this.formErrors.set({ ...details, general: mainMsg });
        this.toast.error(mainMsg);
      },
    });
  }

  protected cancelLeave(req: LeaveRequest): void {
    if (!confirm('Are you sure you want to cancel this leave request?')) {
      return;
    }

    this.leavesService.cancelLeave(req.id).subscribe({
      next: () => {
        this.toast.success('Leave request cancelled.');
        this.loadCalendar();
      },
      error: (err: ApiErrorBody) => {
        this.toast.error(err.message || 'Failed to cancel leave request.');
      },
    });
  }

  private loadCalendar(): void {
    this.loading.set(true);
    const active = this.currentMonth();
    const year = active.getFullYear();
    const month = active.getMonth() + 1;

    // Date range for current month +/- padding
    const startStr = `${year}-${String(month).padStart(2, '0')}-01`;
    const lastDayNum = new Date(year, month, 0).getDate();
    const endStr = `${year}-${String(month).padStart(2, '0')}-${String(lastDayNum).padStart(2, '0')}`;

    this.leavesService.getCalendar({ start_date: startStr, end_date: endStr }).subscribe({
      next: (feed) => {
        this.calendarFeed.set(feed);
        this.loading.set(false);
      },
      error: () => {
        this.toast.error('Failed to load calendar data.');
        this.loading.set(false);
      },
    });
  }

  private getStartOfMonth(d: Date): Date {
    return new Date(d.getFullYear(), d.getMonth(), 1);
  }

  private formatDateStr(d: Date): string {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }
}
