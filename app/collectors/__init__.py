from app.collectors.base import CollectorBase
from app.collectors.confluence import ConfluenceCollector
from app.collectors.git import GitCollector
from app.collectors.jira import JiraCollector
from app.collectors.slack import SlackCollector

COLLECTORS: dict[str, CollectorBase] = {
    "git": GitCollector(),
    "slack": SlackCollector(),
    "jira": JiraCollector(),
    "confluence": ConfluenceCollector(),
}
