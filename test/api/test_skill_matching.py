"""Test skill listing and matching logic.

Usage:
    cd server && uv run python ../test/api/test_skill_matching.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from bootstrap import print_divider

# bootstrap does os.chdir(SERVER_DIR), so relative paths work
from src.services.skill_service import SkillService


def main():
    svc = SkillService()

    # Step 1: List all skill summaries
    print_divider("All Skills (summaries)")
    summaries = svc.get_all_summaries()
    if not summaries:
        print("No skills found.")
    else:
        for s in summaries:
            print(f"  [{s['slug']}] {s['name']}: {s['description']}")

    # Step 2: List auto_load skills with content preview
    print_divider("Auto-load Skills (with content)")
    auto_skills = svc.get_auto_load_skills()
    if not auto_skills:
        print("No auto-load skills.")
    else:
        for meta, body in auto_skills:
            print(f"\n  [{meta.slug}] {meta.name} (auto_load=True)")
            print(f"  Description: {meta.description}")
            preview = body[:300]
            print(f"  Content preview:\n    {preview}")
            if len(body) > 300:
                print(f"    ... ({len(body)} chars total)")

    # Note
    print_divider("Note")
    print("Skill matching is NOT vector-based.")
    print("The main agent sees skill summaries in its system prompt,")
    print("then decides to call use_skill(slug) based on LLM reasoning.")


if __name__ == "__main__":
    main()
