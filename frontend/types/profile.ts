export interface Profile {
  id: string;
  name: string;
  headline: string | null;
  about: string | null;
  skills: any[] | null;
  experience: any[] | null;
  projects: any[] | null;
  education: any[] | null;
  contact_preferences: Record<string, any> | null;
  is_public: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProfileCreateInput {
  name: string;
  headline?: string | null;
  about?: string | null;
  skills?: any[] | null;
  experience?: any[] | null;
  projects?: any[] | null;
  education?: any[] | null;
  contact_preferences?: Record<string, any> | null;
}

export interface ProfileUpdateInput {
  name?: string | null;
  headline?: string | null;
  about?: string | null;
  skills?: any[] | null;
  experience?: any[] | null;
  projects?: any[] | null;
  education?: any[] | null;
  contact_preferences?: Record<string, any> | null;
  is_public?: boolean;
}
