# develop/release 브랜치 정책 (2026-11-22)

## 변경 이유와 범위

기존 CI는 main PR·push만 검사하고 로컬 훅도 main만 보호했다. 사용자 요청에 따라 작업 통합은 develop, 배포 대상은 release로 분리한다. 원격 브랜치·기본 브랜치·GitHub 보호 규칙·CD·서버 설정은 이번 로컬 구현으로 변경되지 않는다.

## 구현

- `.github/workflows/ci.yml`: develop/release 및 최초 전환용 main PR·push에서 검사한다. PR base 변경도 edited 이벤트로 재검사한다. branch-policy job이 PR 경로와 정책 회귀 테스트를 검사하고 backend/frontend/admin은 그 성공에 의존한다. 기존 앱 검사 단계와 액션 버전은 유지한다.
- `scripts/check-pr-target.sh`: develop 및 전환용 main은 기존 area-first 작업 브랜치명을, release는 같은 저장소의 develop만 허용한다. 누락 인자·잘못된 base·외부 포크의 develop은 거부한다. PR 정보를 env를 거쳐 인자로 전달해 branch 이름을 shell 코드에 삽입하지 않는다.
- `.githooks/pre-push`: 원격 ref 기준으로 main/develop/release의 생성·수정·삭제를 거부한다. 로컬 브랜치 이름이 다르거나 여러 ref를 함께 push해도 보호한다. GitHub UI/API의 승인된 초기 브랜치 생성은 별도 절차다.
- `.githooks/prepare-commit-msg`: detached HEAD·통합 브랜치 이름을 허용하고 작업 브랜치의 기존 이름 검사는 유지한다. 이름 허용은 직접 push 승인과 다르다.
- `scripts/test-branch-policy.sh`: 임시 Git 저장소를 고정된 fixture-base에서 만들고 전역 훅 설정과 분리해 검사한다. 현재 작업 브랜치·index·원격 설정은 변경하지 않는다.

## 검증과 한계

- POSIX shell 구문 검사와 정책 회귀 테스트 24개를 실행한다. release 잘못된 출처, 포크, 누락 인자, 다중 ref와 보호 브랜치 생성·수정·삭제, 브랜치 이름 검사를 포함한다.
- PyYAML로 workflow를 파싱하고 대상 브랜치·job 의존성·정책 테스트 실행·읽기 전용 권한과 기존 앱 job 본문 보존을 확인했다.
- GitHub의 실제 Actions·required checks·merge 설정은 미검증이다. main protected 상태는 읽었지만 보호 세부 조회는 연결 도구의 관리 권한 부족으로 403이었다.
- PR 검사 파일 자체가 바뀌는 PR은 리뷰해야 한다. 로컬 훅과 저장소 안의 검사 코드는 GitHub 서버 보호 설정을 대신하지 않는다.
- 작업 브랜치가 최신 develop에서 생성됐는지는 기본 브랜치·작업 절차로 관리한다. 이름·PR base 검사만으로 분기 시점까지 강제한다고 주장하지 않는다.
- actionlint는 현재 환경에 없어 실행하지 못했다. 앱 소스·의존성·빌드 명령 변경은 없으므로 앱 전체 게이트 대신 이 정책 도구와 workflow 구조를 검증한다.

실제 전환과 release 배포 계약은 [배포 가이드](../../../guides/GUIDE_DEPLOYMENT.md), 정책은 [결정 문서](../../../DECISIONS.md#브랜치-전략-결정)를 따른다.
