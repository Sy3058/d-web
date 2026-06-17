import { api, ApiError } from './api';

export interface User {
  id: string;
  email: string;
  nickname: string;
  profile_image: string | null;
  is_admin: boolean;
  is_email_verified: boolean;
  created_at: string;
}

export async function getMe(cookieHeader?: string): Promise<User | null> {
  try {
    const options = cookieHeader
      ? { headers: { Cookie: cookieHeader } }
      : undefined;
    return await api.get<User>('/auth/me', options);
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null;
    throw e;
  }
}
