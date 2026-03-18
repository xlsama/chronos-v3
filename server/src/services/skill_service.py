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
    auto_load: bool = False


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
            name=str(fm.get("name") or slug),
            description=str(fm.get("description") or ""),
            created_at=created_at,
            updated_at=updated_at,
            auto_load=fm.get("auto_load", False),
        )

    def _is_skill_ready(self, fm: dict, body: str) -> bool:
        """技能必须有 name、description 和正文才算可用。"""
        return bool(fm.get("name") and fm.get("description") and body.strip())

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
        raw = skill_file.read_text(encoding="utf-8")
        fm, _ = self._parse_skill_file(skill_file)
        return self._build_meta(slug, fm, skill_dir), raw

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
            fm, _ = self._parse_skill_file(skill_file)
            if fm.get("name") == name:
                raw = skill_file.read_text(encoding="utf-8")
                return self._build_meta(skill_dir.name, fm, skill_dir), raw
        raise FileNotFoundError(f"Skill with name '{name}' not found")

    def create_skill(self, slug: str) -> SkillMeta:
        skill_dir = self.base_dir / slug
        if skill_dir.exists():
            raise FileExistsError(f"Skill '{slug}' already exists")
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            f"---\nname: {slug}\ndescription:\n---\n\n",
            encoding="utf-8",
        )
        fm, _ = self._parse_skill_file(skill_file)
        return self._build_meta(slug, fm, skill_dir)

    def update_skill(self, slug: str, content: str) -> SkillMeta:
        skill_dir = self.base_dir / slug
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            raise FileNotFoundError(f"Skill '{slug}' not found")
        skill_file.write_text(content, encoding="utf-8")
        fm, _ = self._parse_skill_file(skill_file)
        return self._build_meta(slug, fm, skill_dir)

    def delete_skill(self, slug: str) -> None:
        skill_dir = self.base_dir / slug
        if not skill_dir.exists():
            raise FileNotFoundError(f"Skill '{slug}' not found")
        shutil.rmtree(skill_dir)

    def get_auto_load_skills(self) -> list[tuple[SkillMeta, str]]:
        """Return skills marked with auto_load: true (metadata + full body)."""
        result: list[tuple[SkillMeta, str]] = []
        if not self.base_dir.exists():
            return result
        for skill_dir in sorted(self.base_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            fm, body = self._parse_skill_file(skill_file)
            if fm.get("auto_load", False) and self._is_skill_ready(fm, body):
                meta = self._build_meta(skill_dir.name, fm, skill_dir)
                result.append((meta, body))
        return result

    def get_all_summaries(self) -> list[dict]:
        """返回所有可用技能的摘要（过滤掉不完整的技能）。"""
        result: list[dict] = []
        if not self.base_dir.exists():
            return result
        for skill_dir in sorted(self.base_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            fm, body = self._parse_skill_file(skill_file)
            if not self._is_skill_ready(fm, body):
                continue
            meta = self._build_meta(skill_dir.name, fm, skill_dir)
            result.append({"slug": meta.slug, "name": meta.name, "description": meta.description})
        return result

