import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { Auth } from '../../../core/services/auth';
import { Icon } from '../../../shared/icon/icon';
import { Page } from '../../../core/models/api.model';
import { Team, TeamHierarchyLevel, TeamMember } from '../../../core/models/teams.model';
import { Teams } from '../../../core/services/teams';
import { Toast } from '../../../core/services/toast';
import { User } from '../../../core/models/user.model';
import { Users } from '../../../core/services/users';

@Component({
  selector: 'app-manage-teams',
  imports: [ReactiveFormsModule, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './manage-teams.html',
  styleUrl: './manage-teams.scss',
})
export class ManageTeams {
  private readonly teamsService = inject(Teams);
  private readonly usersService = inject(Users);
  private readonly toast = inject(Toast);
  private readonly fb = inject(FormBuilder);
  protected readonly auth = inject(Auth);

  protected readonly loading = signal(true);
  protected readonly teams = signal<Team[]>([]);
  protected readonly selectedTeam = signal<Team | null>(null);
  protected readonly hierarchyLevels = signal<TeamHierarchyLevel[]>([]);
  protected readonly teamMembers = signal<TeamMember[]>([]);
  protected readonly allUsers = signal<User[]>([]);

  // Modals
  protected showCreateTeamModal = signal(false);
  protected showAddLevelModal = signal(false);
  protected showAddMemberModal = signal(false);
  protected showMoveMemberModal = signal(false);
  protected editingTeam = signal<Team | null>(null);
  protected selectedMemberToMove = signal<TeamMember | null>(null);

  // Forms
  protected readonly teamForm = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(150)]],
    description: ['', [Validators.maxLength(500)]],
    status: ['active' as 'active' | 'inactive'],
  });

  protected readonly levelForm = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(100)]],
    order: [1, [Validators.required, Validators.min(1)]],
  });

  protected readonly addMemberForm = this.fb.nonNullable.group({
    user_id: ['', [Validators.required]],
    hierarchy_level_id: [''],
  });

  protected readonly moveMemberForm = this.fb.nonNullable.group({
    target_team_id: ['', [Validators.required]],
    hierarchy_level_id: [''],
  });

  constructor() {
    this.loadTeams();
    this.loadAllUsers();
  }

  protected loadTeams() {
    this.loading.set(true);
    this.teamsService.listTeams().subscribe({
      next: (page) => {
        this.teams.set(page.items);
        this.loading.set(false);

        // Auto-select first team if none selected
        if (page.items.length > 0 && !this.selectedTeam()) {
          this.selectTeam(page.items[0]);
        }
      },
      error: (err) => {
        this.toast.error(err.message || 'Failed to load teams');
        this.loading.set(false);
      },
    });
  }

  protected loadAllUsers() {
    this.usersService.list({ page_size: 200 }).subscribe({
      next: (page: Page<User>) => this.allUsers.set(page.items),
      error: () => {},
    });
  }

  protected selectTeam(team: Team) {
    this.selectedTeam.set(team);
    this.loadTeamDetails(team.id);
  }

  protected loadTeamDetails(teamId: string) {
    this.teamsService.listHierarchy(teamId).subscribe({
      next: (levels) => this.hierarchyLevels.set(levels),
      error: () => {},
    });

    this.teamsService.listMembers(teamId).subscribe({
      next: (members) => this.teamMembers.set(members),
      error: () => {},
    });
  }

  // --- Team CRUD ---
  protected openCreateTeamModal() {
    this.editingTeam.set(null);
    this.teamForm.reset({ name: '', description: '', status: 'active' });
    this.showCreateTeamModal.set(true);
  }

  protected openEditTeamModal(team: Team) {
    this.editingTeam.set(team);
    this.teamForm.setValue({
      name: team.name,
      description: team.description || '',
      status: team.status,
    });
    this.showCreateTeamModal.set(true);
  }

  protected saveTeam() {
    if (this.teamForm.invalid) return;

    const val = this.teamForm.getRawValue();
    const editing = this.editingTeam();

    if (editing) {
      this.teamsService.updateTeam(editing.id, val).subscribe({
        next: (updated) => {
          this.toast.success('Team updated successfully');
          this.showCreateTeamModal.set(false);
          this.loadTeams();
          if (this.selectedTeam()?.id === updated.id) {
            this.selectedTeam.set(updated);
          }
        },
        error: (err) => this.toast.error(err.message || 'Failed to update team'),
      });
    } else {
      this.teamsService.createTeam(val).subscribe({
        next: (created) => {
          this.toast.success('Team created successfully');
          this.showCreateTeamModal.set(false);
          this.loadTeams();
          this.selectTeam(created);
        },
        error: (err) => this.toast.error(err.message || 'Failed to create team'),
      });
    }
  }

  protected deleteTeam(team: Team) {
    if (!confirm(`Are you sure you want to deactivate team '${team.name}'?`)) return;

    this.teamsService.deleteTeam(team.id).subscribe({
      next: () => {
        this.toast.success('Team deactivated');
        if (this.selectedTeam()?.id === team.id) {
          this.selectedTeam.set(null);
        }
        this.loadTeams();
      },
      error: (err) => this.toast.error(err.message || 'Failed to deactivate team'),
    });
  }

  // --- Hierarchy CRUD ---
  protected openAddLevelModal() {
    const nextOrder = (this.hierarchyLevels().length || 0) + 1;
    this.levelForm.reset({ name: '', order: nextOrder });
    this.showAddLevelModal.set(true);
  }

  protected saveLevel() {
    const team = this.selectedTeam();
    if (!team || this.levelForm.invalid) return;

    this.teamsService.createHierarchy(team.id, this.levelForm.getRawValue()).subscribe({
      next: () => {
        this.toast.success('Hierarchy level created');
        this.showAddLevelModal.set(false);
        this.loadTeamDetails(team.id);
      },
      error: (err) => this.toast.error(err.message || 'Failed to create hierarchy level'),
    });
  }

  protected deleteLevel(levelId: string) {
    const team = this.selectedTeam();
    if (!team) return;

    if (!confirm('Are you sure you want to remove this hierarchy level?')) return;

    this.teamsService.deleteHierarchy(team.id, levelId).subscribe({
      next: () => {
        this.toast.success('Hierarchy level removed');
        this.loadTeamDetails(team.id);
      },
      error: (err) => this.toast.error(err.message || 'Failed to remove hierarchy level'),
    });
  }

  // --- Member Management ---
  protected openAddMemberModal() {
    this.addMemberForm.reset({ user_id: '', hierarchy_level_id: '' });
    this.showAddMemberModal.set(true);
  }

  protected saveMember() {
    const team = this.selectedTeam();
    if (!team || this.addMemberForm.invalid) return;

    const val = this.addMemberForm.getRawValue();
    this.teamsService.addMember(team.id, {
      user_id: val.user_id,
      hierarchy_level_id: val.hierarchy_level_id || undefined,
    }).subscribe({
      next: () => {
        this.toast.success('Employee added to team');
        this.showAddMemberModal.set(false);
        this.loadTeamDetails(team.id);
      },
      error: (err) => this.toast.error(err.message || 'Failed to add employee to team'),
    });
  }

  protected removeMember(member: TeamMember) {
    const team = this.selectedTeam();
    if (!team) return;

    if (!confirm(`Remove ${member.employee.full_name} from team?`)) return;

    this.teamsService.removeMember(team.id, member.employee.id).subscribe({
      next: () => {
        this.toast.success('Employee removed from team');
        this.loadTeamDetails(team.id);
      },
      error: (err) => this.toast.error(err.message || 'Failed to remove employee'),
    });
  }

  protected openMoveMemberModal(member: TeamMember) {
    this.selectedMemberToMove.set(member);
    this.moveMemberForm.reset({ target_team_id: '', hierarchy_level_id: '' });
    this.showMoveMemberModal.set(true);
  }

  protected saveMoveMember() {
    const member = this.selectedMemberToMove();
    if (!member || this.moveMemberForm.invalid) return;

    const val = this.moveMemberForm.getRawValue();
    this.teamsService.moveMember({
      user_id: member.employee.id,
      target_team_id: val.target_team_id,
      hierarchy_level_id: val.hierarchy_level_id || undefined,
    }).subscribe({
      next: () => {
        this.toast.success('Employee moved to new team');
        this.showMoveMemberModal.set(false);
        if (this.selectedTeam()) {
          this.loadTeamDetails(this.selectedTeam()!.id);
        }
      },
      error: (err) => this.toast.error(err.message || 'Failed to move employee'),
    });
  }

  protected onAssignLevel(member: TeamMember, event: Event) {
    const team = this.selectedTeam();
    if (!team) return;

    const levelId = (event.target as HTMLSelectElement).value;
    this.teamsService.assignMemberHierarchy(team.id, member.employee.id, levelId).subscribe({
      next: () => {
        this.toast.success('Hierarchy level assigned');
        this.loadTeamDetails(team.id);
      },
      error: (err) => this.toast.error(err.message || 'Failed to assign hierarchy level'),
    });
  }
}
