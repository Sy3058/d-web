# Claude Code에서 Codex로 이관

## 원칙

- Claude Code 파일은 삭제하거나 변경하지 않는다. 두 도구를 병행할 수 있게 Codex용 파일을 추가한다.
- 진행 상태는 AI memory가 아니라 현재 Git, `docs/DECISIONS.md`, `docs/MISTAKES.md`, `docs/milestones/`를 기준으로 판단한다.
- Claude의 모델명, 세션 통계, 허용 명령 이력처럼 도구에 종속되거나 시간에 따라 낡는 값은 이관하지 않는다.

## 이관 매핑

| Claude Code 원본 | Codex 대상 | 처리 |
|---|---|---|
| 루트·영역별 `CLAUDE.md` | 루트·영역별 `AGENTS.md` | 현재 코드·문서와 맞는 규칙만 정리 |
| `.claude/settings.json` hooks | `.codex/config.toml`, `.codex/hooks.json` | Codex 이벤트 형식으로 연결 |
| `.claude/hooks/session-start.py`, `study-review.py`, `guard.py` | `.codex/hooks.json` | 호환되는 스크립트를 공유해 양쪽 동작 유지 |
| Claude Write/Edit 후 검사 | `.codex/hooks/pre_patch.py`, `post_patch.py` | Codex `apply_patch` 입력에 맞춘 어댑터 추가 |
| `~/.claude/skills/fable-*` | `.agents/skills/fable-*` | project-local Codex skill로 이관 |
| `~/.claude/commands/council.md` | `.agents/skills/council-review` | Codex skill로 이관 |
| `~/.claude/.../memory/MEMORY.md` | `AGENTS.md`, skills, 기존 docs | 반복 적용 규율만 선별 이관 |

## 이관하지 않은 항목

- `.credentials.json`, OAuth/account 정보와 토큰
- 대화 transcript, history, file-history, paste-cache, shell snapshot
- 세션·작업·daemon·통계·캐시 데이터
- Claude의 모델·effort 설정과 명령별 permission 누적 기록
- 이미 머지됐거나 현재 Git과 충돌하는 과거 진행 상태 memory
- Claude plugin cache 자체. 필요한 동작은 Codex skill로 별도 작성한다.

## 운영 메모

- 이 저장소에서 Git으로 공유되는 기준은 루트와 영역별 `AGENTS.md`, `docs/`다. Codex는 루트에서 현재 작업 디렉터리까지의 `AGENTS.md`를 계층적으로 적용한다.
- `.codex/`, `.agents/`, `.claude/`는 `.gitignore`된 로컬 도구 설정이다. 현재 worktree에서는 사용할 수 있지만 clone이나 다른 worktree에 자동 배포되는 project 자산으로 간주하지 않는다.
- Codex는 저장소를 trusted project로 열어야 로컬 `.codex` 설정과 hooks를 로드한다. 새 hook이나 변경된 hook은 실행 전에 내용을 검토한다.
- 로컬 skill 목록이 갱신되지 않으면 새 세션에서 다시 확인한다. 재현 가능한 필수 규칙은 skill에만 두지 않고 추적되는 `AGENTS.md`나 관련 문서에도 남긴다.
- Claude용 설정과 Codex용 설정이 공통 규칙에서 달라지면 먼저 저장소 문서를 고친 뒤 양쪽 지침을 함께 맞춘다.
