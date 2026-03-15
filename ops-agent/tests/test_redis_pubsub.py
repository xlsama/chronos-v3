import pytest
import fakeredis.aioredis

from src.agent.event_publisher import EventPublisher


@pytest.fixture
async def redis():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


async def test_publish_and_subscribe(redis):
    publisher = EventPublisher(redis=redis)
    channel = "incident:test-123"

    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    # consume subscription confirmation message
    await pubsub.get_message(timeout=1)

    await publisher.publish(channel, event_type="thinking", data={"content": "Analyzing..."})

    msg = await pubsub.get_message(timeout=1)
    assert msg is not None
    assert msg["type"] == "message"

    import orjson
    payload = orjson.loads(msg["data"])
    assert payload["event_type"] == "thinking"
    assert payload["data"]["content"] == "Analyzing..."


async def test_publish_multiple_events_in_order(redis):
    publisher = EventPublisher(redis=redis)
    channel = "incident:test-456"

    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    await pubsub.get_message(timeout=1)

    events = [
        ("thinking", {"content": "step 1"}),
        ("tool_call", {"name": "exec_read", "args": {}}),
        ("tool_result", {"output": "ok"}),
    ]

    for event_type, data in events:
        await publisher.publish(channel, event_type=event_type, data=data)

    received = []
    for _ in range(3):
        msg = await pubsub.get_message(timeout=1)
        if msg and msg["type"] == "message":
            import orjson
            received.append(orjson.loads(msg["data"])["event_type"])

    assert received == ["thinking", "tool_call", "tool_result"]
