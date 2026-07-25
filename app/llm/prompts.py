from collections import defaultdict

SYSTEM_PROMPT = """당신은 개발자의 하루 업무 활동을 보기 좋게 정리해주는 어시스턴트입니다.

아래 제공된 업무 활동 데이터를 바탕으로 일일 업무 보고서를 작성해주세요.

## 작성 규칙
- 제공된 데이터에 있는 내용만 사용합니다. 데이터에 없는 내용은 추측하거나 추가하지 않습니다.
- Jira 이슈 키(예: MFP-123)가 같은 활동은 하나로 묶어서 정리합니다.
- 각 항목을 구체적으로 서술하고, 관련 URL이 있으면 포함합니다.
- 데이터가 없는 섹션은 생략합니다.
- 한국어로 작성합니다.

## 보고서 구성

### 완료한 작업
오늘 완료된 작업 목록 (머지된 PR, 완료 처리된 이슈, 배포 등)

### 진행 중인 작업
아직 완료되지 않은 진행 중인 작업 (오픈된 PR, 진행 중 이슈, 작성 중인 문서 등)

### 주요 커뮤니케이션
Slack 대화, 코드 리뷰 댓글, Jira/Confluence 댓글 등 중요한 소통 내용

### 결정 사항 및 특이 사항
중요한 결정, 이슈, 블로커

### 내일 할 일
데이터에서 명확히 파악되는 다음 할 일 (불명확하면 이 섹션은 생략)"""


def build_user_message(date: str, timezone: str, activities: list[dict]) -> str:
    by_source: dict[str, list[dict]] = defaultdict(list)
    for a in activities:
        by_source[a.get("source", "unknown")].append(a)

    source_labels = {
        "git": "Git / GitHub",
        "slack": "Slack",
        "jira": "Jira",
        "confluence": "Confluence",
        "manual": "수동 추가",
    }

    lines = [
        f"날짜: {date}  |  시간대: {timezone}",
        f"총 활동 수: {len(activities)}건",
        "",
    ]

    for source, items in by_source.items():
        label = source_labels.get(source, source.upper())
        lines.append(f"## {label} ({len(items)}건)")
        lines.append("")

        for a in items:
            activity_type = a.get("activity_type") or ""
            title = (a.get("title") or "").strip()
            content = (a.get("content") or "").strip()
            url = a.get("url") or ""
            project = a.get("project") or ""
            issue_key = a.get("issue_key") or ""
            ts = a.get("activity_ts") or ""

            header_parts = []
            if issue_key:
                header_parts.append(f"[{issue_key}]")
            if activity_type:
                header_parts.append(f"[{activity_type}]")
            header = " ".join(header_parts)
            if title:
                header = f"{header} {title}" if header else title

            lines.append(f"- {header or '(내용 없음)'}")

            if ts:
                ts_str = str(ts)
                if "T" in ts_str:
                    ts_str = ts_str.split("T")[1][:8]
                lines.append(f"  시각: {ts_str}")
            if project and not issue_key:
                lines.append(f"  프로젝트: {project}")
            if content and content != title:
                lines.append(f"  내용: {content[:400]}")
            if url:
                lines.append(f"  URL: {url}")

        lines.append("")

    return "\n".join(lines)
