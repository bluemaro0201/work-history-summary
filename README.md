# Work History Summary

로컬에서 실행하는 일일 업무 요약 도구입니다.

Git(GitHub / GitHub Enterprise / GitLab / Bitbucket Cloud), Slack, Jira, Confluence에서 하루 활동을 수집하고, Claude / ChatGPT에 붙여넣을 수 있는 프롬프트를 생성합니다.

- AI API 키 불필요 — 프롬프트 생성까지만 담당
- DB 불필요 — 토큰은 로컬 `data/providers.json`에 저장
- 여러 계정 지원 — GitHub 계정, Jira 인스턴스 등 복수 추가 가능

---

## 스크린샷

| 수집 화면 | 토큰 설정 화면 |
|---|---|
| 날짜 선택 후 수집 소스 체크 → 프롬프트 생성 | 서비스별 토큰 및 수집 범위 관리 |

---

## 요구사항

- Python 3.12+
- [Poetry](https://python-poetry.org/docs/#installation)

---

## 빠른 시작

```bash
# 1. 클론
git clone https://github.com/bluemaro0201/work-history-summary.git
cd work-history-summary

# 2. 의존성 설치
poetry install

# 3. 서버 실행
poetry run uvicorn app.main:app --reload

# 4. 브라우저에서 열기
open http://localhost:8000
```

첫 실행 시 `/settings`에서 사용할 서비스의 토큰을 추가하면 됩니다.

---

## 토큰 설정 방법

### Git (GitHub / GitHub Enterprise / GitLab / Bitbucket Cloud)

설정 화면에서 **호스트 유형**을 먼저 선택한 뒤, 해당 서비스 방식으로 토큰을 발급해 입력합니다.

**GitHub / GitHub Enterprise**
1. GitHub → Settings → Developer settings → Personal access tokens → **Tokens (classic)**
2. **Generate new token** 클릭
3. 권한 선택: `repo`, `read:user`
4. 생성된 토큰(`ghp_...`) 복사 → 설정 화면에 입력
5. GitHub Enterprise(자체 호스팅)라면 API Base URL에 `https://github.company.com/api/v3` 형식으로 입력

**GitLab** (gitlab.com 또는 self-hosted)
1. User Settings → **Access Tokens**
2. 스코프에서 `read_api` 선택 후 토큰 생성 (`glpat-...`)
3. 생성된 토큰 복사 → 설정 화면에 입력
4. Self-hosted GitLab이라면 API Base URL에 `https://gitlab.company.com/api/v4` 형식으로 입력

**Bitbucket Cloud**
1. Workspace settings → **Access Tokens** (또는 Atlassian API tokens)에서 `repository:read`, `pullrequest:read` 권한으로 토큰 생성
2. 생성된 토큰 복사 → 설정 화면에 입력
3. App Password 방식(Basic Auth)은 지원하지 않으며, Bearer 토큰 방식만 지원합니다

> 저장소는 모든 호스트 공통으로 `owner/repo`(Bitbucket은 `workspace/repo`) 형식으로 입력합니다.

### Slack

1. [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → From scratch
2. App Name 입력 후 워크스페이스 선택 → Create App
3. 좌측 **OAuth & Permissions** 클릭
4. **User Token Scopes**에 아래 권한 추가:
   - `channels:history` — 채널 메시지 읽기
   - `channels:read` — 채널 목록
   - `groups:history` — 비공개 채널 메시지
   - `search:read` — 메시지 검색
   - `users:read` — 사용자 정보
5. **Install to Workspace** 클릭 후 허용
6. **User OAuth Token** (`xoxp-...`) 복사 → 설정 화면에 입력

> 채널 ID를 설정하지 않으면 전체 채널을 검색합니다. 활동이 많은 워크스페이스라면 수집 범위에 채널 ID를 입력하는 것을 권장합니다.

### Jira / Confluence

1. [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens) → **Create API token**
2. 생성된 토큰 복사
3. 설정 화면에서 사이트 URL(`https://yourcompany.atlassian.net`), 이메일, 토큰 입력
4. Account ID는 자동으로 채워집니다

> Jira와 Confluence가 같은 인스턴스라면 동일한 토큰과 이메일을 사용하면 됩니다.

---

## 사용 방법

1. 브라우저에서 `http://localhost:8000` 접속
2. 날짜 선택
3. 수집할 소스(계정) 체크 후 **수집 및 프롬프트 생성** 클릭
4. 수집된 활동 목록에서 프롬프트에 포함할 항목을 체크박스로 선택 (기본은 전체 선택, 불필요한 항목은 해제)
5. **선택 항목으로 프롬프트 생성** 클릭 → 생성된 프롬프트를 복사해 Claude 또는 ChatGPT에 붙여넣기

---

## 수집 데이터 및 프롬프트 생성 방식

각 서비스에서 수집한 활동은 공통 형식(`activity_type`, `title`, `content`, `url`, `activity_ts` 등)으로 정리됩니다. 별도의 AI API 호출 없이 텍스트 생성까지만 이 앱이 담당하며, 실제 요약은 사용자가 프롬프트를 복사해 Claude/ChatGPT에 붙여넣을 때 이루어집니다.

수집(`POST /api/collect`)과 프롬프트 생성(`POST /api/prompt`)은 별도 단계로 분리되어 있습니다. 소스별 수집 개수에 인위적인 상한을 두지 않는 대신, 수집된 전체 활동을 화면에서 보여주고 사용자가 체크박스로 프롬프트에 포함할 항목을 직접 고릅니다 — 활동이 많은 날 프롬프트가 지나치게 길어지는 문제를 자동 절단이 아니라 사용자의 선택으로 해결하는 구조입니다.

### 소스별 수집 항목

| 소스 | 수집 항목 |
|---|---|
| **Git — GitHub / GitHub Enterprise** | 지정 레포의 커밋(메시지, SHA, URL, 시각), 오픈/머지된 PR(제목, 본문, 번호, URL), 내가 작성한 PR 리뷰 코멘트(본문, 파일 경로) |
| **Git — GitLab** | 지정 프로젝트의 커밋(작성자 이메일로 필터링), 오픈/머지된 MR(제목, 설명, URL), 내가 작성한 MR 노트(리뷰 댓글) |
| **Git — Bitbucket Cloud** | 지정 저장소의 커밋, 내가 작성한 PR과 그 머지 여부, 내가 작성한 PR 코멘트 |
| **Jira** | 지정 프로젝트에서 당일 업데이트된 이슈 중 내 활동만 필터링: 필드 변경 이력(changelog), 내가 쓴 댓글, 내가 멘션된 댓글, (활동이 없으면) 담당 이슈의 상태 변경 |
| **Confluence** | 지정 스페이스에서 당일 수정된 페이지 중: 내가 마지막으로 수정한 페이지(제목 + 본문, 옵션에 따라 HTML 원문 포함), 내가 쓴 댓글, 내가 멘션된 댓글 |
| **Slack** | 지정 채널에서 내가 보낸 메시지, 나를 멘션한 메시지(옵션으로 끌 수 있음), 스레드 답글 |

모든 항목은 커밋 메시지, PR/MR 제목, Slack 메시지 본문에서 Jira 이슈 키(`ABC-123` 형식)를 정규식으로 자동 추출해 `issue_key`로 붙입니다. 같은 이슈 키를 가진 활동은 프롬프트 상에서 함께 묶여 요약 품질을 높입니다.

> Git 소스는 provider마다 저장된 `host_type`(github / github_enterprise / gitlab / bitbucket)에 따라 알맞은 수집기로 자동 라우팅됩니다. GitLab/Bitbucket은 API 특성상 "커밋 작성자"와 "PR/MR을 머지한 사람"을 100% 정확히 구분하기 어려워, 이메일·계정 ID 기준의 best-effort 매칭을 사용합니다.

### 프롬프트 생성 방식

1. **System 프롬프트**: "제공된 데이터만 사용", "Jira 이슈 키 기준으로 묶어서 정리", "완료한 작업 / 진행 중인 작업 / 주요 커뮤니케이션 / 결정 사항 및 특이 사항 / 내일 할 일" 5개 섹션 구조로 한국어 보고서를 작성하도록 고정된 지시문입니다.
2. **User 메시지**: 수집된 활동을 소스별로 그룹핑하고, 각 항목을 `[이슈키] [활동유형] 제목 / 시각 / 프로젝트 / 내용(최대 400자) / URL` 형식의 불릿으로 나열합니다.

최종적으로 `[System]\n...\n\n[User]\n...` 형태로 합쳐져 화면에 표시되며, 이 텍스트를 그대로 복사해 원하는 LLM에 붙여넣으면 됩니다.

> **참고**: Confluence 페이지 본문/댓글은 원본이 XHTML(storage 포맷)이라, 태그를 제거하고 읽기 쉬운 텍스트로 변환한 뒤 수집합니다(멘션 감지는 변환 전 원본에서 수행하므로 정확도에 영향 없음).

---

## Docker로 실행

```bash
docker compose up
```

`./data` 디렉터리를 컨테이너의 `/app/data`에 그대로 마운트하는 구조라, 로컬에 `data/providers.json`이 없어도 최초 토큰 등록 시 자동 생성되고 컨테이너를 재시작/재빌드해도 유지됩니다. (참고: 과거 버전은 `providers.json` 파일 자체를 마운트했는데, 호스트에 파일이 없으면 Docker가 그 경로를 디렉터리로 잘못 생성해버리는 문제가 있어 디렉터리 마운트 방식으로 변경했습니다.)

포트 등을 바꾸고 싶다면 `.env` 파일을 만들어 덮어쓸 수 있습니다.

```bash
# .env (선택사항)
APP_PORT=9000
```

---

## 프로젝트 구조

```
app/
├── api/
│   ├── collect.py        # POST /api/collect — 수집 (활동 목록 반환) / POST /api/prompt — 선택된 활동으로 프롬프트 생성
│   └── settings_api.py   # CRUD /api/providers — 토큰 관리
├── collectors/
│   ├── git.py            # GitHub / GitHub Enterprise 커밋/PR/리뷰 수집
│   ├── gitlab.py         # GitLab 커밋/MR/노트 수집
│   ├── bitbucket.py      # Bitbucket Cloud 커밋/PR/댓글 수집
│   ├── __init__.py       # host_type 기반 git 수집기 라우팅 (GitDispatchCollector)
│   ├── slack.py          # Slack 메시지 검색
│   ├── jira.py           # Jira 이슈 활동 수집
│   └── confluence.py     # Confluence 페이지 편집 수집
├── llm/
│   └── prompts.py        # 프롬프트 빌더
├── templates/
│   ├── summaries/new.html  # 수집 메인 화면
│   └── settings.html       # 토큰 설정 화면
├── config.py             # 앱 설정
├── providers.py          # data/providers.json CRUD
└── main.py               # FastAPI 앱 진입점
data/providers.json       # 토큰 저장소 (자동 생성, .gitignore)
```

---

## 라이선스

MIT
