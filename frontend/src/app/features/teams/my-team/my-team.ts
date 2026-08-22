import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';

import { Auth } from '../../../core/services/auth';
import { Icon } from '../../../shared/icon/icon';
import {
  MyTeamResponse,
  TeamAvailabilityResponse,
  TeamBirthdaysResponse,
} from '../../../core/models/teams.model';
import { Teams } from '../../../core/services/teams';
import { Toast } from '../../../core/services/toast';

@Component({
  selector: 'app-my-team',
  imports: [DatePipe, RouterLink, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './my-team.html',
  styleUrl: './my-team.scss',
})
export class MyTeam {
  private readonly teamsService = inject(Teams);
  private readonly toast = inject(Toast);
  protected readonly auth = inject(Auth);

  protected readonly loading = signal(true);
  protected readonly teamData = signal<MyTeamResponse | null>(null);
  protected readonly availability = signal<TeamAvailabilityResponse | null>(null);
  protected readonly birthdays = signal<TeamBirthdaysResponse | null>(null);

  protected activeTab = signal<'availability' | 'roster' | 'birthdays'>('availability');

  constructor() {
    this.loadData();
  }

  protected loadData() {
    this.loading.set(true);

    this.teamsService.getMyTeam().subscribe({
      next: (data) => {
        this.teamData.set(data);
        this.loading.set(false);
      },
      error: (err) => {
        this.toast.error(err.message || 'Failed to load team data');
        this.loading.set(false);
      },
    });

    this.teamsService.getAvailability().subscribe({
      next: (data) => this.availability.set(data),
      error: () => {},
    });

    this.teamsService.getBirthdays().subscribe({
      next: (data) => this.birthdays.set(data),
      error: () => {},
    });
  }

  protected getStatusBadgeClass(status: string): string {
    switch (status) {
      case 'PRESENT':
        return 'badge-success';
      case 'ABSENT':
        return 'badge-danger';
      case 'ON_LEAVE':
        return 'badge-purple';
      case 'HALF_DAY':
      case 'LATE':
        return 'badge-warning';
      case 'HOLIDAY':
        return 'badge-info';
      default:
        return 'badge-neutral';
    }
  }

  protected getAvatarInitials(name: string): string {
    if (!name) return 'U';
    const parts = name.trim().split(' ');
    if (parts.length >= 2) {
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }
    return name.substring(0, 2).toUpperCase();
  }
}
