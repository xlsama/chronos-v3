from datetime import datetime, timezone
from uuid import uuid4

from src.api.incidents import _message_to_event
from src.db.models import Message


def test_message_to_event_preserves_skill_read_metadata():
    message = Message(
        id=uuid4(),
        incident_id=uuid4(),
        role="assistant",
        event_type="skill_read",
        content="kfc-alert-check",
        metadata_json={
            "skill_slug": "kfc-alert-check",
            "skill_name": "KFC 告警排查",
            "content": "# KFC 告警排查",
            "success": True,
        },
        created_at=datetime.now(timezone.utc),
    )

    event = _message_to_event(message)

    assert event["event_type"] == "skill_read"
    assert event["data"]["skill_slug"] == "kfc-alert-check"
    assert event["data"]["skill_name"] == "KFC 告警排查"
    assert event["data"]["content"] == "# KFC 告警排查"
    assert event["data"]["success"] is True
