export interface Team {
  id: string;
  name: string;
  description?: string;
  status: 'active' | 'inactive';
  created_at?: string;
  updated_at?: string;
  my_membership?: TeamMember;
}

export interface TeamHierarchyLevel {
  id: string;
  name: string;
  order: number;
  is_active?: boolean;
}

export interface TeamMemberEmployee {
  id: string;
  full_name: string;
  email: string;
  employee_id?: string;
  designation?: string;
  avatar_url?: string;
  date_of_birth?: string;
}

export interface TeamMember {
  id: string;
  employee: TeamMemberEmployee;
  hierarchy_level?: TeamHierarchyLevel | null;
  joined_at?: string;
  is_active?: boolean;
}

export interface MyTeamResponse {
  team: Team | null;
  hierarchy_levels: TeamHierarchyLevel[];
  members: TeamMember[];
}

export interface AvailabilitySlot {
  date: string;
  status: 'PRESENT' | 'ABSENT' | 'ON_LEAVE' | 'HALF_DAY' | 'LATE' | 'HOLIDAY' | 'SCHEDULED';
  label: string;
}

export interface MemberAvailability {
  employee: TeamMemberEmployee;
  hierarchy_level?: TeamHierarchyLevel | null;
  availability: AvailabilitySlot[];
}

export interface TeamAvailabilityResponse {
  start_date: string;
  end_date: string;
  days: string[];
  members: MemberAvailability[];
}

export interface BirthdayItem {
  employee: TeamMemberEmployee;
  hierarchy_level?: TeamHierarchyLevel | null;
  birthday_date: string;
  days_until: number;
  is_today: boolean;
}

export interface TeamBirthdaysResponse {
  birthdays_today: BirthdayItem[];
  upcoming_birthdays: BirthdayItem[];
}
