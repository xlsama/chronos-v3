import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.lib.logger import get_logger
from src.lib.paths import skills_dir

log = get_logger(component="skill")

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_ALLOWED_SUBDIRS = {"scripts", "references", "assets"}


@dataclass
class SkillMeta:
    slug: str
    name: str
    description: str
    created_at: str
    updated_at: str
    has_scripts: bool = False
    has_references: bool = False
    has_assets: bool = False
    script_files: list[str] = field(default_factory=list)
    reference_files: list[str] = field(default_factory=list)
    asset_files: list[str] = field(default_factory=list)
    draft: bool = False


class SkillService:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or skills_dir()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ── Parsing ──────────────────────────────────────────────

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

        scripts_dir = skill_dir / "scripts"
        refs_dir = skill_dir / "references"
        assets_dir = skill_dir / "assets"
        script_files = (
            sorted(f.name for f in scripts_dir.iterdir() if f.is_file())
            if scripts_dir.is_dir()
            else []
        )
        reference_files = (
            sorted(f.name for f in refs_dir.iterdir() if f.is_file()) if refs_dir.is_dir() else []
        )
        asset_files = (
            sorted(f.name for f in assets_dir.iterdir() if f.is_file())
            if assets_dir.is_dir()
            else []
        )

        return SkillMeta(
            slug=slug,
            name=str(fm.get("name") or slug),
            description=str(fm.get("description") or ""),
            created_at=created_at,
            updated_at=updated_at,
            has_scripts=len(script_files) > 0,
            has_references=len(reference_files) > 0,
            has_assets=len(asset_files) > 0,
            script_files=script_files,
            reference_files=reference_files,
            asset_files=asset_files,
            draft=bool(fm.get("draft", False)),
        )

    def _is_skill_ready(self, fm: dict, body: str) -> bool:
        """技能必须有 name、description 和正文才算可用。"""
        return bool(fm.get("name") and fm.get("description") and body.strip())

    # ── Validation ───────────────────────────────────────────

    def _validate_slug(self, slug: str) -> list[str]:
        """校验 slug 格式，返回错误列表。"""
        errors: list[str] = []
        if len(slug) > 64:
            errors.append("Slug 长度不能超过 64 字符")
        if not _SLUG_RE.match(slug):
            errors.append(
                "Slug 只能包含小写字母、数字和连字符，不能以连字符开头/结尾，不能有连续连字符"
            )
        return errors

    def _validate_skill(self, slug: str, fm: dict, body: str) -> list[str]:
        """校验 skill 内容，返回错误列表（空表示通过）。"""
        errors: list[str] = []

        name = fm.get("name", "")
        if not name:
            errors.append("Name 不能为空")
        elif len(str(name)) > 64:
            errors.append("Name 长度不能超过 64 字符")

        description = fm.get("description", "")
        if not description:
            errors.append("Description 不能为空")
        elif len(str(description)) > 1024:
            errors.append("Description 长度不能超过 1024 字符")

        if not body.strip():
            errors.append("Body 不能为空")

        return errors

    # ── Path Safety ──────────────────────────────────────────

    def _safe_rel_path(self, slug: str, rel_path: str) -> Path:
        """校验并返回安全的绝对路径。"""
        if ".." in rel_path or rel_path.startswith("/") or rel_path.startswith("~"):
            raise ValueError(f"非法路径: {rel_path}")

        # 必须在 scripts/ 或 references/ 子目录下
        parts = Path(rel_path).parts
        if len(parts) < 2 or parts[0] not in _ALLOWED_SUBDIRS:
            raise ValueError(f"非法路径: {rel_path}（必须在 scripts/、references/ 或 assets/ 下）")

        full_path = (self.base_dir / slug / rel_path).resolve()
        skill_dir = (self.base_dir / slug).resolve()

        # 确保解析后的路径在 skill 目录内
        if not str(full_path).startswith(str(skill_dir)):
            raise ValueError(f"非法路径: {rel_path}")

        return full_path

    # ── CRUD ─────────────────────────────────────────────────

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

    # ── File Management ──────────────────────────────────────

    def list_skill_files(self, slug: str) -> dict[str, list[str]]:
        """列出 skill 的附属文件。"""
        skill_dir = self.base_dir / slug
        if not skill_dir.exists():
            raise FileNotFoundError(f"Skill '{slug}' not found")

        result: dict[str, list[str]] = {"scripts": [], "references": [], "assets": []}
        for subdir in _ALLOWED_SUBDIRS:
            sub_path = skill_dir / subdir
            if sub_path.is_dir():
                result[subdir] = sorted(f.name for f in sub_path.iterdir() if f.is_file())
        return result

    def read_skill_file(self, slug: str, rel_path: str) -> str:
        """读取 skill 目录下的附属文件。"""
        full_path = self._safe_rel_path(slug, rel_path)
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {slug}/{rel_path}")
        return full_path.read_text(encoding="utf-8")

    def write_skill_file(self, slug: str, rel_path: str, content: str) -> None:
        """创建/更新附属文件，lazy 创建子目录。"""
        full_path = self._safe_rel_path(slug, rel_path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")

    def delete_skill_file(self, slug: str, rel_path: str) -> None:
        """删除附属文件。"""
        full_path = self._safe_rel_path(slug, rel_path)
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {slug}/{rel_path}")
        full_path.unlink()

    # ── Agent 接口 ───────────────────────────────────────────

    def get_available_skills(self) -> list[dict]:
        """返回所有可用技能摘要（排除 draft 和不完整的技能）。"""
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
            if fm.get("draft", False):
                continue
            meta = self._build_meta(skill_dir.name, fm, skill_dir)
            result.append(
                {
                    "slug": meta.slug,
                    "name": meta.name,
                    "description": meta.description,
                    "has_scripts": meta.has_scripts,
                    "has_references": meta.has_references,
                    "has_assets": meta.has_assets,
                }
            )
        log.info("get_available_skills returning", count=len(result))
        return result

    def read_file(self, slug: str, rel_path: str | None = None) -> str:
        """为 read_skill tool 服务。

        - rel_path 为空/None → 返回 SKILL.md body + 文件目录
        - rel_path 非空 → 返回该文件内容
        """
        skill_dir = self.base_dir / slug
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            raise FileNotFoundError(f"Skill '{slug}' not found")

        log.info("read_file called", slug=slug, rel_path=rel_path)

        if rel_path:
            content = self.read_skill_file(slug, rel_path)
            log.info(
                "read_file returning file content",
                slug=slug,
                file=rel_path,
                content_len=len(content),
            )
            log.debug("read_file content", content=content)
            return content

        # 返回 SKILL.md body + 文件列表
        _, body = self._parse_skill_file(skill_file)
        files = self.list_skill_files(slug)

        has_files = any(files[k] for k in files)
        file_count = sum(len(files[k]) for k in files)
        log.info(
            "read_file returning SKILL.md", slug=slug, body_len=len(body), attached_files=file_count
        )
        log.debug("read_file SKILL.md body", body=body)

        if not has_files:
            return body

        lines = [body.rstrip(), "", "---", "## 附属文件"]
        lines.append('以下文件可通过 read_skill("{slug}/{path}") 获取：')
        for subdir in ("scripts", "references", "assets"):
            if files[subdir]:
                lines.append(f"\n### {subdir}/")
                for f in files[subdir]:
                    lines.append(f"- {subdir}/{f}")

        return "\n".join(lines)
