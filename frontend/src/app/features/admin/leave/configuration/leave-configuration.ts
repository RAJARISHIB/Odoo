import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { ApiErrorBody } from '../../../../core/models/api.model';
import { Role } from '../../../../core/models/user.model';
import {
  AllocationGenerateResult,
  LeaveAllocationRule,
  LeaveType,
} from '../../../../core/models/leaves.model';
import { Leaves } from '../../../../core/services/leaves';
import { Realtime } from '../../../../core/services/realtime';
import { Toast } from '../../../../core/services/toast';

type Tab = 'types' | 'rules';

/**
 * Admin leave configuration: the two building blocks of the leave engine -
 * what kinds of leave exist, and how much of each a role accrues.
 */
@Component({
  selector: 'app-leave-configuration',
  imports: [ReactiveFormsModule, DatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './leave-configuration.html',
})
export class LeaveConfiguration {
  private readonly leaves = inject(Leaves);
  private readonly realtime = inject(Realtime);
  private readonly toast = inject(Toast);
  private readonly fb = inject(FormBuilder);

  protected readonly tab = signal<Tab>('types');
  protected readonly roles: Role[] = ['employee', 'manager', 'hr', 'admin', 'super_admin'];

  protected readonly types = signal<LeaveType[]>([]);
  protected readonly rules = signal<LeaveAllocationRule[]>([]);
  protected readonly loading = signal(false);

  protected readonly showTypeForm = signal(false);
  protected readonly editingTypeId = signal<string | null>(null);
  protected readonly savingType = signal(false);
  protected readonly typeErrors = signal<Record<string, string>>({});

  protected readonly showRuleForm = signal(false);
  protected readonly savingRule = signal(false);
  protected readonly ruleErrors = signal<Record<string, string>>({});

  protected readonly generating = signal(false);
  protected readonly lastGenerated = signal<AllocationGenerateResult | null>(null);

  protected readonly typeForm = this.fb.nonNullable.group({
    name: ['', Validators.required],
    code: ['', Validators.required],
    description: [''],
    is_paid: [true],
    allow_fractional: [true],
    min_unit: [0.5, Validators.required],
    max_days_per_request: [null as number | null],
    requires_approval: [true],
  });

  protected readonly ruleForm = this.fb.nonNullable.group({
    leave_type_id: ['', Validators.required],
    role: ['employee' as Role, Validators.required],
    amount: [1, [Validators.required, Validators.min(0.5)]],
    frequency: ['monthly'],
    effective_from: [new Date().toISOString().slice(0, 10), Validators.required],
  });

  protected readonly generateForm = this.fb.nonNullable.group({
    year: [new Date().getFullYear(), Validators.required],
    month: [new Date().getMonth() + 1, Validators.required],
    frequency: ['monthly' as 'monthly' | 'yearly'],
  });

  constructor() {
    this.loadTypes();
    this.loadRules();

    this.realtime
      .onAny(['leave.type_updated', 'leave.allocation_updated'])
      .pipe(takeUntilDestroyed())
      .subscribe(() => {
        this.loadTypes();
        this.loadRules();
      });
  }

  protected setTab(tab: Tab): void {
    this.tab.set(tab);
  }

  // -- leave types ----------------------------------------------------------
  private loadTypes(): void {
    this.loading.set(true);
    this.leaves.types({ active_only: 'false' }).subscribe({
      next: (types) => {
        this.types.set(types);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  protected toggleTypeForm(type?: LeaveType): void {
    this.typeErrors.set({});
    if (type) {
      this.editingTypeId.set(type.id);
      this.typeForm.reset({
        name: type.name,
        code: type.code,
        description: type.description ?? '',
        is_paid: type.is_paid,
        allow_fractional: type.allow_fractional,
        min_unit: type.min_unit,
        max_days_per_request: type.max_days_per_request ?? null,
        requires_approval: type.requires_approval,
      });
      this.showTypeForm.set(true);
    } else {
      this.editingTypeId.set(null);
      this.typeForm.reset({ is_paid: true, allow_fractional: true, min_unit: 0.5, requires_approval: true });
      this.showTypeForm.update((open) => !open);
    }
  }

  protected saveType(): void {
    if (this.typeForm.invalid || this.savingType()) {
      this.typeForm.markAllAsTouched();
      return;
    }

    this.savingType.set(true);
    this.typeErrors.set({});
    const payload = this.typeForm.getRawValue();
    const editingId = this.editingTypeId();

    const request = editingId ? this.leaves.updateType(editingId, payload) : this.leaves.createType(payload);
    request.subscribe({
      next: (type) => {
        this.savingType.set(false);
        this.toast.success(`${type.name} saved.`);
        this.showTypeForm.set(false);
        this.editingTypeId.set(null);
        this.loadTypes();
      },
      error: (error: ApiErrorBody) => {
        this.savingType.set(false);
        this.typeErrors.set(error.details ?? { code: error.message });
      },
    });
  }

  protected toggleTypeActive(type: LeaveType): void {
    this.leaves.setTypeActive(type.id, !type.is_active).subscribe(() => {
      this.toast.success(`${type.name} is now ${type.is_active ? 'inactive' : 'active'}.`);
      this.loadTypes();
    });
  }

  // -- allocation rules -------------------------------------------------------
  private loadRules(): void {
    this.leaves.allocationRules().subscribe((rules) => this.rules.set(rules));
  }

  protected toggleRuleForm(): void {
    this.showRuleForm.update((open) => !open);
    this.ruleErrors.set({});
  }

  protected saveRule(): void {
    if (this.ruleForm.invalid || this.savingRule()) {
      this.ruleForm.markAllAsTouched();
      return;
    }

    this.savingRule.set(true);
    this.ruleErrors.set({});
    this.leaves.createAllocationRule(this.ruleForm.getRawValue()).subscribe({
      next: () => {
        this.savingRule.set(false);
        this.toast.success('Allocation rule saved.');
        this.ruleForm.reset({ role: 'employee', amount: 1, frequency: 'monthly', effective_from: new Date().toISOString().slice(0, 10) });
        this.showRuleForm.set(false);
        this.loadRules();
      },
      error: (error: ApiErrorBody) => {
        this.savingRule.set(false);
        this.ruleErrors.set(error.details ?? { amount: error.message });
      },
    });
  }

  protected toggleRuleActive(rule: LeaveAllocationRule): void {
    this.leaves.updateAllocationRule(rule.id, { is_active: !rule.is_active }).subscribe(() => {
      this.toast.success(rule.is_active ? 'Rule deactivated.' : 'Rule activated.');
      this.loadRules();
    });
  }

  protected typeName(id: string): string {
    return this.types().find((type) => type.id === id)?.name ?? '—';
  }

  // -- accrual generation -----------------------------------------------------
  protected generate(): void {
    this.generating.set(true);
    const value = this.generateForm.getRawValue();
    this.leaves
      .generateAllocations({
        year: value.year,
        month: value.frequency === 'yearly' ? undefined : value.month,
        frequency: value.frequency,
      })
      .subscribe({
        next: (result) => {
          this.generating.set(false);
          this.lastGenerated.set(result);
          this.toast.success(`Credited ${result.created} allocation(s) for ${result.period}.`);
        },
        error: () => this.generating.set(false),
      });
  }
}
