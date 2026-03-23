import hashlib
import shutil
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.lib.logger import get_logger
from src.lib.paths import seeds_skills_dir, skills_dir

log = get_logger(component="seeder")

SEED_MARKER = ".seed_hash"


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def _save_seed_version(session: AsyncSession, slug: str, content: str, change_source: str = "seed") -> None:
    from src.services.version_service import VersionService

    vs = VersionService(session)
    await vs.save_version(
        entity_type="skill",
        entity_id=slug,
        content=content,
        change_source=change_source,
    )


async def seed_skills(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """启动时将 seeds/skills/ 复制到 data/skills/（若不存在或需更新）"""
    seeds = seeds_skills_dir()
    target_base = skills_dir()
    target_base.mkdir(parents=True, exist_ok=True)

    if not seeds.exists():
        log.warning("Seeds directory not found", path=str(seeds))
        return

    for seed_skill_dir in sorted(seeds.iterdir()):
        if not seed_skill_dir.is_dir():
            continue

        slug = seed_skill_dir.name
        seed_file = seed_skill_dir / "SKILL.md"
        if not seed_file.exists():
            continue

        target_dir = target_base / slug
        target_file = target_dir / "SKILL.md"
        marker_file = target_dir / SEED_MARKER
        seed_hash = _file_hash(seed_file)

        if not target_dir.exists():
            # 全新部署：复制整个 seed skill 目录
            shutil.copytree(seed_skill_dir, target_dir)
            marker_file.write_text(seed_hash)
            async with session_factory() as session:
                content = seed_file.read_text(encoding="utf-8")
                await _save_seed_version(session, slug, content)
                await session.commit()
            log.info("Seeded new skill", slug=slug)

        elif marker_file.exists():
            # 之前已 seed 过，检查是否有更新
            old_seed_hash = marker_file.read_text().strip()
            if seed_hash == old_seed_hash:
                continue  # seed 未变化，跳过

            # seed 有更新，检查用户是否修改过运行时副本
            if target_file.exists():
                runtime_hash = _file_hash(target_file)
                if runtime_hash == old_seed_hash:
                    # 用户未修改，安全更新
                    shutil.copytree(seed_skill_dir, target_dir, dirs_exist_ok=True)
                    marker_file.write_text(seed_hash)
                    async with session_factory() as session:
                        content = seed_file.read_text(encoding="utf-8")
                        await _save_seed_version(session, slug, content, "seed_update")
                        await session.commit()
                    log.info("Updated seed skill", slug=slug)
                else:
                    # 用户已修改，不覆盖
                    log.warning("Seed skill updated but user has modifications, skipping", slug=slug)

        else:
            # 无 marker：用户自建的同名 skill，不动
            log.info("Skill exists without seed marker, skipping", slug=slug)
