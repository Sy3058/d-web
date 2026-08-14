import { useEffect, useMemo, useRef, useState } from 'react';
import { generateHTML, type Extensions } from '@tiptap/core';
import { buildViewerExtensions } from './extensions';
import {
  calculateBlockOffsetBp,
  calculateBlockRestoreY,
  clampBlockIndex,
  getEpisodeContent,
  getProgress,
  imageFetchPriority,
  isLoggedIn,
  putProgress,
  type ContentDocNode,
  type EpisodeContentResponse,
} from '../../lib/viewer';

interface Props {
  episodeId: string;
}

interface Block {
  node: ContentDocNode;
  // 이 블록이 image면 전체 이미지 순번(fetchPriority 배정용), 아니면 null.
  imageOrdinal: number | null;
}

interface ProgressAnchor {
  index: number;
  offsetBp: number;
}

// 진행도 저장 debounce. 스크롤할 때마다 쏘지 않고 멈춘 뒤에만 저장(C1은 저장 실패를
// 조용히 무시하는 부가 기능이라 과도한 요청을 낼 이유가 없다).
const PROGRESS_SAVE_DEBOUNCE_MS = 800;

// 복원 위치보다 위쪽 이미지 로드 대기 상한(F1 계획검증 결정 - CLS/복원오차 완화). 상한
// 없이 기다리면 이미지 하나가 영영 안 끝나 복원 자체가 멈춘다 - 무기한 대기가 아니라,
// 이 타임아웃 이후에도 이미지가 계속 로드될 수 있으므로 그 뒤늦은 load 이벤트를 버리지
// 않고 재-앵커에 활용한다. 타임아웃 후 포기해도 이미지 자체는 어차피 로드되지만(리스너
// 유무와 무관), 그때 레이아웃이 자라며 스크롤 위치만 문서 위치와 어긋난 채로 남는다.
const RESTORE_IMAGE_TIMEOUT_MS = 2000;

function buildBlocks(nodes: ContentDocNode[]): Block[] {
  let imageOrdinal = 0;
  return nodes.map((node) => {
    if (node.type === 'image') {
      const ordinal = imageOrdinal;
      imageOrdinal += 1;
      return { node, imageOrdinal: ordinal };
    }
    return { node, imageOrdinal: null };
  });
}

function renderNodeHtml(node: ContentDocNode, extensions: Extensions): string {
  try {
    return generateHTML({ type: 'doc', content: [node] }, extensions);
  } catch (e) {
    // 서버 lib/content_doc._validate_node는 최상위 노드 타입을 블록으로 제한하지 않아
    // (예: 최상위 text도 통과) TipTap 스키마가 거부하는 문서가 이론상 가능하다 - 조각
    // 하나의 렌더 실패로 뷰어 전체가 죽지 않게 그 블록만 비워서 넘긴다(B2의 "노드 폐기+
    // 로그"와 같은 원칙 - 공개 읽기 경로가 데이터 상태로 죽지 않게).
    console.warn('뷰어 블록 렌더 실패', e);
    return '';
  }
}

export default function Viewer({ episodeId }: Props) {
  const extensions = useMemo(() => buildViewerExtensions(), []);
  // undefined=로딩 중, null=404(회차 없음), 그 외=정상 응답.
  const [content, setContent] = useState<EpisodeContentResponse | null | undefined>(undefined);
  const [restoredAnchor, setRestoredAnchor] = useState<ProgressAnchor | null>(null);
  // 기존 진행도를 읽고 복원할지 결정하기 전에는 상단의 초기 observer 값으로 PUT하지 않는다.
  const [canSaveProgress, setCanSaveProgress] = useState(false);
  const retriedRef = useRef(false);
  const blockRefs = useRef(new Map<number, HTMLDivElement>());
  const topVisibleRef = useRef(0);
  const blockOffsetBpRef = useRef(0);
  const hasObservedRef = useRef(false);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // 복원 스크롤과 무관하게 마운트 즉시부터 켜둔다 - 복원 effect 안에서만 감지를 시작하면
  // getProgress 응답을 기다리는 동안(특히 느린 연결) 이미 시작된 독자의 스크롤을 놓쳐,
  // 나중에 복원 스크롤이 그 위치를 되돌려버린다.
  const userScrolledRef = useRef(false);
  const programmaticScrollRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    getEpisodeContent(episodeId).then((res) => {
      if (!cancelled) setContent(res);
    });
    return () => {
      cancelled = true;
    };
  }, [episodeId]);

  useEffect(() => {
    const onUserScroll = () => {
      if (!programmaticScrollRef.current) userScrolledRef.current = true;
    };
    window.addEventListener('scroll', onUserScroll, { passive: true });
    window.addEventListener('wheel', onUserScroll, { passive: true });
    window.addEventListener('touchmove', onUserScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onUserScroll);
      window.removeEventListener('wheel', onUserScroll);
      window.removeEventListener('touchmove', onUserScroll);
    };
  }, []);

  const blocks = useMemo(() => (content ? buildBlocks(content.content.content) : []), [content]);

  // 진행도 복원 - 로그인 상태에서만 GET을 쏜다(비로그인 401 자체를 만들지 않는다).
  useEffect(() => {
    if (blocks.length === 0 || !isLoggedIn(document.cookie)) return;
    let cancelled = false;
    setCanSaveProgress(false);
    setRestoredAnchor(null);
    getProgress(episodeId)
      .then((progress) => {
        if (cancelled) return;
        // GET을 기다리는 동안 사용자가 이미 읽기 시작했다면 늦은 자동 복원으로 위치를
        // 되돌리지 않는다. observer가 계산해둔 현재 위치를 다음 effect에서 저장한다.
        if (!progress || userScrolledRef.current) {
          setCanSaveProgress(true);
          return;
        }
        setRestoredAnchor({
          index: clampBlockIndex(progress.page_no, blocks.length),
          // BE보다 FE가 먼저 배포되는 짧은 구간에는 구 응답에 필드가 없을 수 있다.
          offsetBp: progress.block_offset_bp ?? 0,
        });
      })
      .catch(() => {
        // 조회 실패 상태에서 상단 값을 덮어쓰는 것보다 이번 방문의 저장을 포기하는 편이 안전하다.
      });
    return () => {
      cancelled = true;
    };
  }, [episodeId, blocks.length]);

  useEffect(() => {
    if (restoredAnchor === null) return;
    const target = blockRefs.current.get(restoredAnchor.index);
    if (!target) return;

    let cancelled = false;

    const scrollToTarget = () => {
      if (userScrolledRef.current) return;
      programmaticScrollRef.current = true;
      const rect = target.getBoundingClientRect();
      window.scrollTo({
        top: calculateBlockRestoreY(
          window.scrollY + rect.top,
          rect.height,
          restoredAnchor.offsetBp,
        ),
        behavior: 'auto',
      });
      requestAnimationFrame(() => {
        programmaticScrollRef.current = false;
      });
    };

    // 복원 위치까지(포함) 등장하는 이미지 전부 - 이 중 하나라도 로드 전에 스크롤하면
    // 그만큼 레이아웃이 덜 자란 상태라 위치가 밀린다.
    const imagesAbove: HTMLImageElement[] = [];
    for (let i = 0; i <= restoredAnchor.index; i += 1) {
      const el = blockRefs.current.get(i);
      if (el) imagesAbove.push(...Array.from(el.querySelectorAll('img')));
    }

    // 재-앵커: img.complete가 이미 true여도(또는 decode()가 성공으로 착각해도) 나중에
    // src가 바뀌어(예: onError 폴백의 콘텐츠 재요청) 실제로 다시 로드되면 'load'가 다시
    // 발생한다 - 그 사실 하나에만 의존해 이 effect가 정리될 때까지 계속 듣는다. once로
    // 한 번만 듣거나 이미 완료된 이미지를 건너뛰면, 재요청으로 뒤늦게 바뀐 이미지의
    // 레이아웃 변화를 못 잡는다.
    const detachFns = imagesAbove.map((img) => {
      const onLoad = () => {
        if (!cancelled) scrollToTarget();
      };
      img.addEventListener('load', onLoad);
      return () => img.removeEventListener('load', onLoad);
    });

    const waitForImage = (img: HTMLImageElement) =>
      img.complete
        ? Promise.resolve()
        : Promise.race([
            img.decode().catch(() => undefined),
            new Promise<void>((resolve) => setTimeout(resolve, RESTORE_IMAGE_TIMEOUT_MS)),
          ]);

    Promise.all(imagesAbove.map(waitForImage)).then(() => {
      if (cancelled) return;
      scrollToTarget();
      setCanSaveProgress(true);
    });

    return () => {
      cancelled = true;
      detachFns.forEach((detach) => detach());
    };
  }, [restoredAnchor]);

  // IntersectionObserver는 긴 이미지 하나의 내부를 계속 스크롤해도 교차 상태가 바뀌지 않아
  // callback을 다시 호출하지 않는다. observer로 후보 블록을 좁히고, scroll 이벤트에서는
  // requestAnimationFrame당 한 번 현재 블록 내부 오프셋을 다시 계산한다.
  useEffect(() => {
    if (blocks.length === 0 || !isLoggedIn(document.cookie)) return;

    const visible = new Set<number>();
    let animationFrame: number | null = null;

    const updateAnchor = () => {
      animationFrame = null;
      if (visible.size === 0) return;

      const visibleIndices = [...visible];
      const containingViewportTop = visibleIndices.filter((index) => {
        const rect = blockRefs.current.get(index)?.getBoundingClientRect();
        return rect !== undefined && rect.top <= 0 && rect.bottom > 0;
      });
      // 뷰포트 상단을 실제로 포함하는 블록이 있으면 그 블록을 택한다. 위쪽 블록과 다음
      // 블록이 함께 보이되 상단이 여백에 걸린 경우에는 기존 원칙대로 최소 인덱스를 쓴다.
      const index =
        containingViewportTop.length > 0
          ? Math.max(...containingViewportTop)
          : Math.min(...visibleIndices);
      const target = blockRefs.current.get(index);
      if (!target) return;

      const rect = target.getBoundingClientRect();
      hasObservedRef.current = true;
      topVisibleRef.current = index;
      blockOffsetBpRef.current = calculateBlockOffsetBp(rect.top, rect.height);
      if (!canSaveProgress) return;
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(() => {
        void putProgress(episodeId, topVisibleRef.current, blockOffsetBpRef.current);
      }, PROGRESS_SAVE_DEBOUNCE_MS);
    };

    const scheduleAnchorUpdate = () => {
      if (animationFrame === null) animationFrame = requestAnimationFrame(updateAnchor);
    };

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const index = Number((entry.target as HTMLElement).dataset.blockIndex);
          if (entry.isIntersecting) visible.add(index);
          else visible.delete(index);
        }
        scheduleAnchorUpdate();
      },
      { threshold: 0 },
    );
    for (const el of blockRefs.current.values()) observer.observe(el);
    window.addEventListener('scroll', scheduleAnchorUpdate, { passive: true });

    // 페이지 이탈 직전(탭 전환·닫기) 대기 중인 저장을 즉시 시도한다. keepalive는 보장되지
    // 않아 유실 가능 - C1 결정(저장 실패는 조용히 무시)상 허용 범위, 최선 노력일 뿐이다.
    function flushOnHide() {
      // 관측이 한 번도 없었으면(예: 진입 직후 바로 이탈) 저장할 위치가 없다 - page_no=0을
      // 실제 위치로 오인해 쏘지 않는다.
      if (
        document.visibilityState !== 'hidden' ||
        !hasObservedRef.current ||
        !canSaveProgress
      )
        return;
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      void putProgress(episodeId, topVisibleRef.current, blockOffsetBpRef.current);
    }
    document.addEventListener('visibilitychange', flushOnHide);

    return () => {
      observer.disconnect();
      window.removeEventListener('scroll', scheduleAnchorUpdate);
      document.removeEventListener('visibilitychange', flushOnHide);
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      if (animationFrame !== null) cancelAnimationFrame(animationFrame);
    };
  }, [blocks.length, canSaveProgress, episodeId]);

  function handleImageError() {
    // presigned 만료 등 예외적 실패의 폴백(정상 경로 - 결정 6 즉시 전량 요청 - 에선 타지
    // 않아야 정상). 1회만 재요청해 새로 발급된 presigned 세트로 교체한다.
    if (retriedRef.current) return;
    retriedRef.current = true;
    getEpisodeContent(episodeId).then(setContent);
  }

  if (content === undefined) {
    return <p className="text-sm text-muted py-12 text-center">불러오는 중...</p>;
  }
  if (content === null) {
    return <p className="text-sm text-muted py-12 text-center">회차를 찾을 수 없어요.</p>;
  }

  return (
    <div
      className="select-none [-webkit-touch-callout:none]"
      onContextMenu={(e) => e.preventDefault()}
      // 컨테이너에도 드래그 차단을 둔다 - 최상위 image는 자체 onDragStart로 이미 막히지만,
      // paragraph 자식으로 내려온(비-최상위) image는 generateHTML 렌더 경로라 개별 핸들러를
      // 못 붙인다 - 두 경로의 보호 수준을 여기서 맞춘다.
      onDragStart={(e) => e.preventDefault()}
    >
      {blocks.map((block, i) => (
        <div
          key={i}
          data-block-index={i}
          ref={(el) => {
            if (el) blockRefs.current.set(i, el);
            else blockRefs.current.delete(i);
          }}
        >
          {block.node.type === 'image' ? (
            typeof block.node.attrs?.src !== 'string' ? null : (
              <img
                src={block.node.attrs.src}
                alt=""
                draggable={false}
                fetchPriority={imageFetchPriority(block.imageOrdinal ?? 0)}
                onDragStart={(e) => e.preventDefault()}
                onError={handleImageError}
                className="w-full h-auto"
              />
            )
          ) : (
            // 서버 lib/content_doc이 검증한 노드만 렌더 대상이라 XSS 면적이 없다(#76 -
            // 화이트리스트 밖 태그·속성은 애초에 저장될 수 없다).
            <div dangerouslySetInnerHTML={{ __html: renderNodeHtml(block.node, extensions) }} />
          )}
        </div>
      ))}

      {content.has_paid_part && (
        <div className="mt-8 py-12 text-center border-t border-line">
          <p className="text-sm text-muted">여기부터는 유료 구간이에요.</p>
        </div>
      )}
    </div>
  );
}
