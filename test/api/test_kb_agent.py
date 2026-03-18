"""Test KB Sub-Agent full flow with streaming output.

Usage:
    cd server && uv run python ../test/api/test_kb_agent.py -q "Nginx 502"
    cd server && uv run python ../test/api/test_kb_agent.py -q "Nginx 502" -p "<project_uuid>"
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from bootstrap import console_event_callback, print_divider, run_async


async def main(query: str, project_id: str):
    from src.ops_agent.sub_agents.kb_agent import run_kb_agent

    print_divider("KB Agent Start")
    print(f"Query: {query}")
    print(f"Project ID: {project_id or '(discover mode)'}")

    result = await run_kb_agent(
        description=query,
        project_id=project_id,
        event_callback=console_event_callback,
    )

    print_divider("KB Agent Result")
    if isinstance(result, dict):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test KB Sub-Agent")
    parser.add_argument("-q", "--query", type=str, help="Event description")
    parser.add_argument("-p", "--project-id", type=str, default="", help="Project UUID (empty = discover mode)")
    args = parser.parse_args()

    query = args.query or input("Enter event description: ").strip()
    if not query:
        print("Query is required.")
        sys.exit(1)

    run_async(main(query, args.project_id))
