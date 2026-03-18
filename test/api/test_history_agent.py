"""Test History Sub-Agent full flow with streaming output.

Usage:
    cd server && uv run python ../test/api/test_history_agent.py -q "数据库连接池耗尽"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from bootstrap import console_event_callback, print_divider, run_async


async def main(query: str):
    from src.ops_agent.sub_agents.history_agent import run_history_agent

    print_divider("History Agent Start")
    print(f"Query: {query}")

    result = await run_history_agent(
        description=query,
        event_callback=console_event_callback,
    )

    print_divider("History Agent Result")
    print(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test History Sub-Agent")
    parser.add_argument("-q", "--query", type=str, help="Event description")
    args = parser.parse_args()

    query = args.query or input("Enter event description: ").strip()
    if not query:
        print("Query is required.")
        sys.exit(1)

    run_async(main(query))
