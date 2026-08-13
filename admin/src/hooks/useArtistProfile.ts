import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import type { ArtistProfile, ArtistProfileUpdate } from '../types';

const artistProfileKey = ['admin', 'artist-profile'] as const;

export const artistProfileQueryOptions = queryOptions({
  queryKey: artistProfileKey,
  queryFn: () => api.get<ArtistProfile>('/admin/artist-profile'),
});

export function useArtistProfile() {
  return useQuery(artistProfileQueryOptions);
}

export function useUpdateArtistProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ArtistProfileUpdate) =>
      api.put<ArtistProfile>('/admin/artist-profile', body),
    onSuccess: (profile) => {
      queryClient.setQueryData(artistProfileKey, profile);
    },
  });
}

export function useUploadArtistProfileImage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData();
      formData.append('image', file);
      return api.post<ArtistProfile>('/admin/artist-profile/image', undefined, { body: formData });
    },
    onSuccess: (profile) => {
      queryClient.setQueryData(artistProfileKey, profile);
    },
  });
}
