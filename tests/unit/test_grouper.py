from datetime import datetime, timezone
from uuid import uuid4

from app.processing.grouper import ActivityGrouper
from app.schemas.activity import NormalizedActivityCreate


def activity(**kwargs):
    base = {"request_id": uuid4(), "user_id": uuid4(), "source": "git", "activity_type": "commit", "activity_ts": datetime.now(timezone.utc), "metadata": {}}
    base.update(kwargs)
    return NormalizedActivityCreate(**base)


def test_groups_same_issue_key_together():
    rid = uuid4()
    rows = [activity(request_id=rid, issue_key="PAY-1"), activity(request_id=rid, source="jira", issue_key="PAY-1", title="결제")]
    groups = ActivityGrouper().group(rows)
    assert len(groups) == 1
    assert groups[0].group_key == "PAY-1"
    assert groups[0].title == "결제"


def test_misc_group_for_missing_issue_key():
    group = ActivityGrouper().group([activity(source="slack", activity_type="message")])[0]
    assert group.group_key == "misc_slack_message"
    assert group.group_type == "misc"


def test_pull_request_url_grouping():
    group = ActivityGrouper().group([activity(metadata={"pull_request_url": "https://github/pr/1"})])[0]
    assert group.group_key == "https://github/pr/1"
