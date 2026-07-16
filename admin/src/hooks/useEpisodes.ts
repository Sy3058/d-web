import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, api } from '../lib/api';
import type { Episode, EpisodeCreate, EpisodeImageUrl, EpisodeUpdate } from '../types';

// useWorks와 같은 규칙: 키를 세그먼트로 분리해 서로 prefix가 되지 않게 한다
// (prefix 매칭 무효화가 무관한 쿼리까지 재요청하는 F2 함정).
const episodesListKey = (workId: string) => ['admin', 'episodes', 'list', workId] as const;
const imageUrlsKey = (workId: string, episodeId: string) =>
  ['admin', 'episodes', 'image-urls', workId, episodeId] as const;

const episodesUrl = (workId: string) => `/admin/works/${workId}/episodes`;

export const episodesQueryOptions = (workId: string) =>
  queryOptions({
    queryKey: episodesListKey(workId),
    queryFn: () => api.get<Episode[]>(episodesUrl(workId)),
  });

/** episode_no 순 목록. 상세 GET이 없어(D3 계약) 편집 화면도 이 목록에서 찾는다. */
export function useEpisodes(workId: string) {
  return useQuery(episodesQueryOptions(workId));
}

/** 본문 이미지 노드의 presigned 미리보기 URL ({key, url} 쌍).
 *
 * URL은 10분 만료 일회성 값이라 캐시에 남기지 않는다(staleTime 0 + gcTime 0 -
 * 재마운트마다 새로 발급받는다. backend/CLAUDE.md Signed URL 캐시 금지 규칙).
 * episodeId가 null(신규 에피소드, draft 미생성)이면 조회하지 않는다 - 첫 이미지 업로드가
 * draft를 만들면 episodeId가 생겨 쿼리가 활성화된다.
 */
export function useEpisodeImageUrls(workId: string, episodeId: string | null) {
  return useQuery({
    queryKey: imageUrlsKey(workId, episodeId ?? ''),
    queryFn: () => api.get<EpisodeImageUrl[]>(`${episodesUrl(workId)}/${episodeId}/image-urls`),
    enabled: episodeId !== null,
    staleTime: 0,
    gcTime: 0,
    // 없는 에피소드의 404는 재시도해도 결과가 같다 - 무효 진입에서 요청 3배 방지(리뷰 Minor).
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 404) && failureCount < 3,
    // 에디터는 이 데이터를 imageUrlStore로 밀어넣는다 - 포커스 재발급은 화면에 반영되지
    // 않는 요청만 만들므로 끈다(리뷰 FYI).
    refetchOnWindowFocus: false,
  });
}

/** draft 생성(JSON 메타). episode_no 중복이면 이미지 업로드 전에 409가 즉시 온다. */
export function useCreateEpisode(workId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: EpisodeCreate) => api.post<Episode>(episodesUrl(workId), body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: episodesListKey(workId) });
    },
  });
}

/** 페이지 1장 업로드(multipart 단건 - D3 구조 A). 순차 반복 호출은 UploadForm이 담당.
 *
 * 응답은 append 반영된 에피소드 전체 - 새 키는 image_keys의 마지막 원소다.
 * 장마다 목록을 무효화하지 않는다(50장 = 50회 refetch). 배치가 끝난 지점(UploadForm)이
 * 마지막 응답으로 캐시를 갱신한다.
 */
export function useUploadEpisodeImage(workId: string) {
  return useMutation({
    mutationFn: ({ episodeId, file }: { episodeId: string; file: File }) => {
      const formData = new FormData();
      // 백엔드 UploadFile 파라미터명 `image`와 일치해야 한다(FastAPI 이름 바인딩).
      formData.append('image', file);
      // json 자리를 undefined로 둬야 shared api가 Content-Type을 붙이지 않는다
      // (FormData는 브라우저가 boundary 포함 헤더를 스스로 설정).
      return api.post<Episode>(`${episodesUrl(workId)}/${episodeId}/images`, undefined, {
        body: formData,
      });
    },
  });
}

/** 부분수정 저장: 본문(content) + 제목/부제 + (회차 설정 모달에서) 회차번호/판매가.
 * is_published는 절대 싣지 않는다(F4 소관 - 에코하면 서버가 published_at을 NULL로 밀어 예약이
 * 풀린다). image_keys도 싣지 않는다 - 매니페스트는 이미지 업로드 엔드포인트가 append로 관리하고,
 * 축소(미참조 키 정리)는 별도 후속이라 저장 경로가 건드리지 않는다. */
export function useUpdateEpisode(workId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ episodeId, body }: { episodeId: string; body: EpisodeUpdate }) =>
      api.put<Episode>(`${episodesUrl(workId)}/${episodeId}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: episodesListKey(workId) });
    },
  });
}

/** 업로드 배치 종료 시점에 목록 캐시를 한 번만 갱신하기 위한 헬퍼 훅. */
export function useInvalidateEpisodes(workId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: episodesListKey(workId) });
}
