import { api, ApiError } from './api';

export interface User {
  id: number;
  email: string;
  nickname: string;
  is_admin: boolean;
  is_email_verified: boolean;
}

export async function getMe(): Promise<User | null> {
  try {
    return await api.get<User>('/auth/me');
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null;
    throw e;
  }
}
