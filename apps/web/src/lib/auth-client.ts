/**
 * SocietySphere Web Authentication and Session Management Client
 * Integrates with Phase 3 Authentication, Rotation, and RBAC APIs.
 */

import { apiClient } from './api-client';

export interface UserSummary {
  id: string;
  email: string | null;
  phone: string | null;
  first_name: string;
  last_name: string;
  display_name: string;
  status: string;
}

export interface SocietyOption {
  id: string;
  legal_name: string;
  display_name: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token: string;
  user: UserSummary;
  active_society_id: string | null;
  available_societies: SocietyOption[];
}

export interface RefreshResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token: string;
}

export interface UserMeResponse {
  user: UserSummary;
  memberships: SocietyOption[];
  active_society_id: string | null;
  active_roles: string[];
  active_permissions: string[];
}

const STORAGE_KEYS = {
  ACCESS_TOKEN: 'societysphere_access_token',
  REFRESH_TOKEN: 'societysphere_refresh_token',
  ACTIVE_SOCIETY_ID: 'societysphere_active_society_id',
  USER_DATA: 'societysphere_user',
};

export const authClient = {
  getAccessToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
  },

  getRefreshToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN);
  },

  getActiveSocietyId(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem(STORAGE_KEYS.ACTIVE_SOCIETY_ID);
  },

  setActiveSocietyId(societyId: string | null): void {
    if (typeof window === 'undefined') return;
    if (societyId) {
      localStorage.setItem(STORAGE_KEYS.ACTIVE_SOCIETY_ID, societyId);
    } else {
      localStorage.removeItem(STORAGE_KEYS.ACTIVE_SOCIETY_ID);
    }
  },

  getUser(): UserSummary | null {
    if (typeof window === 'undefined') return null;
    const raw = localStorage.getItem(STORAGE_KEYS.USER_DATA);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as UserSummary;
    } catch {
      return null;
    }
  },

  saveSession(response: LoginResponse): void {
    if (typeof window === 'undefined') return;
    localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, response.access_token);
    localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, response.refresh_token);
    localStorage.setItem(STORAGE_KEYS.USER_DATA, JSON.stringify(response.user));
    if (response.active_society_id) {
      localStorage.setItem(STORAGE_KEYS.ACTIVE_SOCIETY_ID, response.active_society_id);
    }
  },

  clearSession(): void {
    if (typeof window === 'undefined') return;
    localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
    localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
    localStorage.removeItem(STORAGE_KEYS.ACTIVE_SOCIETY_ID);
    localStorage.removeItem(STORAGE_KEYS.USER_DATA);
  },

  async login(identifier: string, password: string): Promise<LoginResponse> {
    const res = await apiClient<LoginResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ identifier, password }),
    });
    this.saveSession(res);
    return res;
  },

  async refresh(): Promise<RefreshResponse> {
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) throw new Error('No refresh token available');

    const res = await apiClient<RefreshResponse>('/api/v1/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, res.access_token);
      localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, res.refresh_token);
    }

    return res;
  },

  async logout(): Promise<void> {
    const token = this.getAccessToken();
    if (token) {
      try {
        await apiClient('/api/v1/auth/logout', {
          method: 'POST',
          authToken: token,
        });
      } catch {
        // Clear local state even if server logout encountered network issues
      }
    }
    this.clearSession();
  },

  async logoutAll(): Promise<void> {
    const token = this.getAccessToken();
    if (token) {
      try {
        await apiClient('/api/v1/auth/logout-all', {
          method: 'POST',
          authToken: token,
        });
      } catch {
        // Clear local state regardless
      }
    }
    this.clearSession();
  },

  async getMe(): Promise<UserMeResponse> {
    const token = this.getAccessToken();
    const activeSocietyId = this.getActiveSocietyId();
    return apiClient<UserMeResponse>('/api/v1/auth/me', {
      method: 'GET',
      authToken: token || undefined,
      societyId: activeSocietyId || undefined,
    });
  },

  async switchSociety(societyId: string): Promise<void> {
    const token = this.getAccessToken();
    await apiClient(`/api/v1/auth/societies/${societyId}/switch`, {
      method: 'POST',
      authToken: token || undefined,
    });
    this.setActiveSocietyId(societyId);
  },
};
