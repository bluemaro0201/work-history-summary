# Work History Summary

로컬에서 실행하는 일일 업무 요약 도구입니다.

GitHub, Slack, Jira, Confluence에서 하루 활동을 수집하고, Claude / ChatGPT에 붙여넣을 수 있는 프롬프트를 생성합니다.

- AI API 키 불필요 — 프롬프트 생성까지만 담당
- DB 불필요 — 토큰은 로컬 `providers.json`에 저장
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

### GitHub

1. GitHub → Settings → Developer settings → Personal access tokens → **Tokens (classic)**
2. **Generate new token** 클릭
3. 권한 선택: `repo`, `read:user`
4. 생성된 토큰(`ghp_...`) 복사 → 설정 화면에 입력

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
3. 수집할 소스(계정) 체크
4. **수집 및 프롬프트 생성** 클릭
5. 생성된 프롬프트를 복사해 Claude 또는 ChatGPT에 붙여넣기

---

## Docker로 실행

```bash
docker compose up
```

`providers.json`이 없으면 자동 생성됩니다. 컨테이너를 재시작해도 토큰 설정이 유지됩니다.

포트나 수집 건수 등을 바꾸고 싶다면 `.env` 파일을 만들어 덮어쓸 수 있습니다.

```bash
# .env (선택사항)
APP_PORT=9000
COLLECTOR_MAX_ACTIVITIES_PER_SOURCE=200
```

---

## 프로젝트 구조

```
app/
├── api/
│   ├── collect.py        # POST /api/collect — 수집 및 프롬프트 생성
│   └── settings_api.py   # CRUD /api/providers — 토큰 관리
├── collectors/
│   ├── git.py            # GitHub 커밋/PR/리뷰 수집
│   ├── slack.py          # Slack 메시지 검색
│   ├── jira.py           # Jira 이슈 활동 수집
│   └── confluence.py     # Confluence 페이지 편집 수집
├── llm/
│   └── prompts.py        # 프롬프트 빌더
├── templates/
│   ├── summaries/new.html  # 수집 메인 화면
│   └── settings.html       # 토큰 설정 화면
├── config.py             # 앱 설정
├── providers.py          # providers.json CRUD
└── main.py               # FastAPI 앱 진입점
providers.json            # 토큰 저장소 (자동 생성, .gitignore)
```

---

## 라이선스

MIT
