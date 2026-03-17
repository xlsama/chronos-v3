import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml


SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "skills"


@dataclass
class SkillMeta:
    slug: str
    name: str
    description: str
    created_at: str
    updated_at: str


class SkillService:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or SKILLS_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _parse_skill_file(self, path: Path) -> tuple[dict, str]:
        """Parse a SKILL.md file into (frontmatter_dict, body_content)."""
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return {}, text

        parts = text.split("---", 2)
        if len(parts) < 3:
            return {}, text

        fm = yaml.safe_load(parts[1]) or {}
        body = parts[2].lstrip("\n")
        return fm, body

    def _build_meta(self, slug: str, fm: dict, skill_dir: Path) -> SkillMeta:
        stat = skill_dir.stat()
        created_at = datetime.fromtimestamp(stat.st_birthtime, tz=timezone.utc).isoformat()
        updated_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        return SkillMeta(
            slug=slug,
            name=fm.get("name", slug),
            description=fm.get("description", ""),
            created_at=created_at,
            updated_at=updated_at,
        )

    def list_skills(self) -> list[SkillMeta]:
        skills: list[SkillMeta] = []
        if not self.base_dir.exists():
            return skills
        for skill_dir in sorted(self.base_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            fm, _ = self._parse_skill_file(skill_file)
            skills.append(self._build_meta(skill_dir.name, fm, skill_dir))
        return skills

    def get_skill(self, slug: str) -> tuple[SkillMeta, str]:
        skill_dir = self.base_dir / slug
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            raise FileNotFoundError(f"Skill '{slug}' not found")
        fm, body = self._parse_skill_file(skill_file)
        return self._build_meta(slug, fm, skill_dir), body

    def get_skill_by_name(self, name: str) -> tuple[SkillMeta, str]:
        """Find a skill by its display name (frontmatter `name` field)."""
        if not self.base_dir.exists():
            raise FileNotFoundError(f"Skill with name '{name}' not found")
        for skill_dir in self.base_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            fm, body = self._parse_skill_file(skill_file)
            if fm.get("name") == name:
                return self._build_meta(skill_dir.name, fm, skill_dir), body
        raise FileNotFoundError(f"Skill with name '{name}' not found")

    def create_skill(self, slug: str, name: str, description: str, content: str) -> SkillMeta:
        skill_dir = self.base_dir / slug
        if skill_dir.exists():
            raise FileExistsError(f"Skill '{slug}' already exists")
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        self._write_skill_file(skill_file, name, description, content)
        fm, _ = self._parse_skill_file(skill_file)
        return self._build_meta(slug, fm, skill_dir)

    def update_skill(
        self,
        slug: str,
        name: str | None = None,
        description: str | None = None,
        content: str | None = None,
    ) -> SkillMeta:
        skill_dir = self.base_dir / slug
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            raise FileNotFoundError(f"Skill '{slug}' not found")
        fm, body = self._parse_skill_file(skill_file)
        if name is not None:
            fm["name"] = name
        if description is not None:
            fm["description"] = description
        if content is not None:
            body = content
        self._write_skill_file(skill_file, fm.get("name", slug), fm.get("description", ""), body)
        fm_new, _ = self._parse_skill_file(skill_file)
        return self._build_meta(slug, fm_new, skill_dir)

    def delete_skill(self, slug: str) -> None:
        skill_dir = self.base_dir / slug
        if not skill_dir.exists():
            raise FileNotFoundError(f"Skill '{slug}' not found")
        shutil.rmtree(skill_dir)

    def get_all_summaries(self) -> list[dict]:
        return [
            {"slug": s.slug, "name": s.name, "description": s.description}
            for s in self.list_skills()
        ]

    @staticmethod
    def _write_skill_file(path: Path, name: str, description: str, content: str) -> None:
        fm = yaml.dump({"name": name, "description": description}, allow_unicode=True, default_flow_style=False).strip()
        path.write_text(f"---\n{fm}\n---\n\n{content}", encoding="utf-8")
