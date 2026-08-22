import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import {
  FormBuilder,
  FormGroup,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';

import { CalendarFeed, Holiday, LeaveBalance, LeaveRequest } from '../../../core/models/leaves.model';
import { Leaves } from '../../../core/services/leaves';
import { Toast } from '../../../core/services/toast';

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
  imports: [CommonModule, ReactiveFormsModule],
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

  protected readonly applyForm: FormGroup = this.fb.group({
    start_date: ['', Validators.required],
    end_date: ['', Validators.required],
    reason: ['', [Validators.required, Validators.maxLength(1000)]],
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
      start_date: val.start_date,
      end_date: val.end_date,
      reason: val.reason,
    }).subscribe({
      next: (res) => {
        this.submitting.set(false);
        this.toast.success(`Leave request submitted (${res.status}).`);
        this.closeApplyModal();
        this.loadCalendar();
      },
      error: (err) => {
        this.submitting.set(false);
        const details = err.error?.error?.details || {};
        const mainMsg = err.error?.error?.message || 'Failed to submit leave request.';
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
      error: (err) => {
        const msg = err.error?.error?.message || 'Failed to cancel leave request.';
        this.toast.error(msg);
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
