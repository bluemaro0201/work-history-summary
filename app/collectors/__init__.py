from app.collectors.base import CollectorBase
from app.collectors.bitbucket import BitbucketCollector
from app.collectors.confluence import ConfluenceCollector
from app.collectors.git import GitHubCollector
from app.collectors.gitlab import GitLabCollector
from app.collectors.jira import JiraCollector
from app.collectors.slack import SlackCollector

_GIT_COLLECTORS: dict[str, CollectorBase] = {
    "github": GitHubCollector(),
    "github_enterprise": GitHubCollector(),
    "gitlab": GitLabCollector(),
    "bitbucket": BitbucketCollector(),
}


class GitDispatchCollector(CollectorBase):
    """Routes a 'git' source provider to the collector matching its host_type."""

    async def fetch(self, date: str, timezone: str, user_identity: dict, access_token: str, options: dict) -> list[dict]:
        host_type = options.get("host_type", "github")
        collector = _GIT_COLLECTORS.get(host_type, _GIT_COLLECTORS["github"])
        return await collector.fetch(date, timezone, user_identity, access_token, options)


COLLECTORS: dict[str, CollectorBase] = {
    "git": GitDispatchCollector(),
    "slack": SlackCollector(),
    "jira": JiraCollector(),
    "confluence": ConfluenceCollector(),
}
