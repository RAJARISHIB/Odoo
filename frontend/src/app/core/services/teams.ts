import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Api, QueryParams } from './api';
import { Page } from '../models/api.model';
import {
  MyTeamResponse,
  Team,
  TeamAvailabilityResponse,
  TeamBirthdaysResponse,
  TeamHierarchyLevel,
  TeamMember,
} from '../models/teams.model';

@Injectable({ providedIn: 'root' })
export class Teams {
  private readonly api = inject(Api);

  // -- Employee endpoints --
  getMyTeam(): Observable<MyTeamResponse> {
    return this.api.get<MyTeamResponse>('teams/my-team');
  }

  getAvailability(params: QueryParams = {}): Observable<TeamAvailabilityResponse> {
    return this.api.get<TeamAvailabilityResponse>('teams/availability', params);
  }

  getBirthdays(params: QueryParams = {}): Observable<TeamBirthdaysResponse> {
    return this.api.get<TeamBirthdaysResponse>('teams/birthdays', params);
  }

  // -- Admin endpoints --
  listTeams(params: QueryParams = {}): Observable<Page<Team>> {
    return this.api.getPage<Team>('admin/teams', params);
  }

  createTeam(payload: Partial<Team>): Observable<Team> {
    return this.api.post<Team>('admin/teams', payload);
  }

  updateTeam(teamId: string, payload: Partial<Team>): Observable<Team> {
    return this.api.patch<Team>(`admin/teams/${teamId}`, payload);
  }

  deleteTeam(teamId: string): Observable<void> {
    return this.api.delete<void>(`admin/teams/${teamId}`);
  }

  // Hierarchy levels
  listHierarchy(teamId: string): Observable<TeamHierarchyLevel[]> {
    return this.api.get<TeamHierarchyLevel[]>(`admin/teams/${teamId}/hierarchy`);
  }

  createHierarchy(teamId: string, payload: { name: string; order?: number }): Observable<TeamHierarchyLevel> {
    return this.api.post<TeamHierarchyLevel>(`admin/teams/${teamId}/hierarchy`, payload);
  }

  updateHierarchy(teamId: string, levelId: string, payload: Partial<TeamHierarchyLevel>): Observable<TeamHierarchyLevel> {
    return this.api.patch<TeamHierarchyLevel>(`admin/teams/${teamId}/hierarchy/${levelId}`, payload);
  }

  reorderHierarchy(teamId: string, levels: { id: string; order: number }[]): Observable<TeamHierarchyLevel[]> {
    return this.api.patch<TeamHierarchyLevel[]>(`admin/teams/${teamId}/hierarchy/reorder`, { levels });
  }

  deleteHierarchy(teamId: string, levelId: string): Observable<void> {
    return this.api.delete<void>(`admin/teams/${teamId}/hierarchy/${levelId}`);
  }

  // Members
  listMembers(teamId: string): Observable<TeamMember[]> {
    return this.api.get<TeamMember[]>(`admin/teams/${teamId}/members`);
  }

  addMember(teamId: string, payload: { user_id: string; hierarchy_level_id?: string }): Observable<TeamMember> {
    return this.api.post<TeamMember>(`admin/teams/${teamId}/members`, payload);
  }

  removeMember(teamId: string, userId: string): Observable<void> {
    return this.api.delete<void>(`admin/teams/${teamId}/members/${userId}`);
  }

  moveMember(payload: { user_id: string; target_team_id: string; hierarchy_level_id?: string }): Observable<TeamMember> {
    return this.api.post<TeamMember>('admin/teams/members/move', payload);
  }

  assignMemberHierarchy(teamId: string, userId: string, hierarchyLevelId: string): Observable<TeamMember> {
    return this.api.patch<TeamMember>(`admin/teams/${teamId}/members/${userId}/hierarchy`, { hierarchy_level_id: hierarchyLevelId });
  }
}
