import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import type { SiteText, SiteTextKey, SiteTextUpdate } from '../types';

const siteTextKey = (key: SiteTextKey) => ['admin', 'site-texts', key] as const;
const siteTextUrl = (key: SiteTextKey) => `/admin/site-texts/${key}`;

export const siteTextQueryOptions = (key: SiteTextKey) =>
  queryOptions({
    queryKey: siteTextKey(key),
    queryFn: () => api.get<SiteText>(siteTextUrl(key)),
  });

/** 행 없음 = 404가 아니라 빈 기본값 응답(서버 시딩 규약) - 첫 편집 진입이 막히지 않는다. */
export function useSiteText(key: SiteTextKey) {
  return useQuery(siteTextQueryOptions(key));
}

/** upsert(ON CONFLICT). 빈 문자열도 허용 - 문구 비우기(공개 화면은 존 접기로 처리). */
export function useUpdateSiteText(key: SiteTextKey) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SiteTextUpdate) => api.put<SiteText>(siteTextUrl(key), body),
    onSuccess: (siteText) => {
      queryClient.setQueryData(siteTextKey(key), siteText);
    },
  });
}
