import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Incident, IncidentHistory
from src.lib.embedder import Embedder
from src.lib.logger import get_logger
from src.lib.paths import incident_history_dir
from src.lib.reranker import Reranker
from src.services.version_service import VersionService

log = get_logger()


async def _generate_title_and_severity(summary_md: str) -> tuple[str, str]:
    import json

    from langchain_core.messages import HumanMessage, SystemMessage

    from src.services.post_incident.base import get_mini_llm

    llm = get_mini_llm()
    log.info(
        "Generating title and severity",
        summary_md_len=len(summary_md),
        input_len=min(len(summary_md), 3000),
    )
    resp = await llm.ainvoke(
        [
            SystemMessage(
                content=(
                    "你是一个事件分析器。根据以下事件排查报告，生成标题和严重等级。\n\n"
                    "严重等级判定标准：\n"
                    "- P0: 核心业务完全不可用，影响大量用户\n"
                    "- P1: 核心业务严重受损，部分功能不可用\n"
                    "- P2: 非核心功能异常，有 workaround\n"
                    "- P3: 轻微问题、信息查询类、无业务影响\n\n"
                    '请输出 JSON 格式：{"title": "简短中文标题（15-30字）", "severity": "P0|P1|P2|P3"}\n'
                    "只输出 JSON，不要输出其他内容。"
                )
            ),
            HumanMessage(content=summary_md[:3000]),
        ]
    )
    raw = resp.content.strip()
    log.info(
        "LLM raw response for title/severity",
        resp_type=type(resp.content).__name__,
        resp_len=len(resp.content) if resp.content else 0,
        raw=raw,
    )
    # 尝试解析 JSON
    try:
        data = json.loads(raw)
        log.info("JSON parsed for title/severity", data=data)
        title = str(data.get("title", "")).strip().strip("\"'《》")
        severity = str(data.get("severity", "P3")).strip().upper()
    except (json.JSONDecodeError, AttributeError) as e:
        log.warning("JSON parse failed for title/severity", error=str(e), raw=raw)
        title = raw.strip().strip("\"'《》")
        severity = "P3"

    if not title or len(title) > 60:
        title = summary_md[:30].replace("\n", " ")
    if severity not in ("P0", "P1", "P2", "P3"):
        severity = "P3"

    log.info("Title and severity result", title=title, severity=severity)
    return title, severity


async def _generate_filename(title: str) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    from src.services.post_incident.base import get_mini_llm

    llm = get_mini_llm()
    log.info("Generating filename", title=title)
    resp = await llm.ainvoke(
        [
            SystemMessage(
                content=(
                    "将以下中文标题翻译为英文文件名，使用 kebab-case 格式，3-8 个单词，"
                    "只输出文件名，不要加扩展名或其他格式。"
                )
            ),
            HumanMessage(content=title),
        ]
    )
    log.info("LLM raw response for filename", raw=resp.content)
    name = resp.content.strip().strip("\"'").lower()
    name = re.sub(r"[^a-z0-9-]", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    result = name if name and len(name) <= 80 else "incident"
    log.info("Filename result", filename=result)
    return result


async def _merge_summaries(existing_md: str, new_md: str) -> str | None:
    from langchain_core.messages import HumanMessage, SystemMessage

    from src.services.post_incident.base import get_mini_llm

    llm = get_mini_llm()
    log.info("Merging summaries", existing_len=len(existing_md), new_len=len(new_md))
    resp = await llm.ainvoke(
        [
            SystemMessage(
                content=(
                    "你是一个事件记录合并助手。你需要对比两份事件排查报告，将新报告中有价值的信息补充到已有报告中。\n\n"
                    "规则：\n"
                    "1. 以「已有报告」为基础，保持其整体结构和格式\n"
                    "2. 从「新报告」中提取真实的、有价值的新增信息，补充到对应章节中\n"
                    "3. 可补充的信息包括：不同的触发条件、额外的排查步骤、补充的根因细节、替代的修复方案\n"
                    "4. 不要编造任何信息，只补充新报告中实际记录的内容\n"
                    '5. 如果新报告没有任何值得补充的新信息，只输出 "NO_CHANGE"\n'
                    "6. 输出完整的合并后报告（Markdown 格式），不要输出解释说明"
                )
            ),
            HumanMessage(content=f"## 已有报告\n\n{existing_md}\n\n## 新报告\n\n{new_md}"),
        ]
    )
    result = resp.content.strip()
    log.info("LLM responded for merge", resp_len=len(result))
    log.debug("LLM responded for merge", result=result)
    if result == "NO_CHANGE":
        log.info("Merge result: NO_CHANGE")
        return None
    log.info("Merged content", content_len=len(result))
    return result


def _sanitize_filename(title: str, max_length: int = 80) -> str:
    name = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", title)
    name = re.sub(r"_+", "_", name).strip("_. ")
    if len(name) > max_length:
        name = name[:max_length].rstrip("_. ")
    return name or "untitled"


def _write_md_file(title: str, summary_md: str, record_id: uuid.UUID | None = None) -> Path | None:
    try:
        dir_path = incident_history_dir()
        dir_path.mkdir(parents=True, exist_ok=True)
        prefix = record_id.hex[:8] if record_id else uuid.uuid4().hex[:8]
        filename = f"{prefix}_{_sanitize_filename(title)}.md"
        file_path = dir_path / filename
        file_path.write_text(summary_md, encoding="utf-8")
        log.info("Wrote incident history file", path=str(file_path))
        return file_path
    except Exception as e:
        log.error("Failed to write incident history file", error=str(e))
        return None


def _delete_md_file(record_id: uuid.UUID) -> None:
    dir_path = incident_history_dir()
    prefix = record_id.hex[:8]
    for f in dir_path.glob(f"{prefix}_*.md"):
        f.unlink()
        log.info("Deleted incident history file", path=str(f))


def _rewrite_md_file(record_id: uuid.UUID, summary_md: str) -> None:
    dir_path = incident_history_dir()
    prefix = record_id.hex[:8]
    matches = list(dir_path.glob(f"{prefix}_*.md"))
    if matches:
        matches[0].write_text(summary_md, encoding="utf-8")
        log.info("Rewrote incident history file", path=str(matches[0]))


class IncidentHistoryService:
    def __init__(
        self,
        session: AsyncSession,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
    ):
        self.session = session
        self.embedder = embedder or Embedder()
        self.reranker = reranker or Reranker()

    async def save(
        self,
        title: str,
        summary_md: str,
    ) -> IncidentHistory:
        embedding = await self.embedder.embed_text(summary_md)

        record = IncidentHistory(
            title=title,
            summary_md=summary_md,
            embedding=embedding,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def find_similar(
        self,
        embedding: list[float],
        limit: int = 5,
    ) -> list[tuple[IncidentHistory, float]]:
        stmt = (
            select(
                IncidentHistory,
                IncidentHistory.embedding.cosine_distance(embedding).label("distance"),
            )
            .where(IncidentHistory.embedding.isnot(None))
            .order_by("distance")
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def update_occurrence(self, history_id: uuid.UUID) -> None:
        record = await self.session.get(IncidentHistory, history_id)
        if record:
            record.occurrence_count += 1
            record.last_seen_at = datetime.now(timezone.utc)
            await self.session.commit()

    async def auto_save(self, incident: Incident, summary_md: str) -> dict:
        """Auto-save with similarity dedup. Returns {"action": "created|updated|skipped"}."""
        embedding = await self.embedder.embed_text(summary_md)
        log.info("Embedding computed")

        similar = await self.find_similar(embedding)

        if similar:
            for rec, dist in similar:
                log.info(
                    "Similar record found",
                    id=str(rec.id)[:8],
                    title=rec.title,
                    distance=f"{dist:.4f}",
                )

            best, distance = similar[0]
            # distance < 0.08 → similarity > 0.92 → skip
            if distance < 0.08:
                log.info("Decision: SKIP", distance=f"{distance:.4f}")
                return {"action": "skipped"}
            # distance 0.08~0.15 → similarity 0.85~0.92 → merge & update occurrence
            if distance < 0.15:
                log.info("Decision: MERGE", distance=f"{distance:.4f}")
                merged = await _merge_summaries(best.summary_md, summary_md)
                if merged:
                    # Update first, then save new content as version
                    best.summary_md = merged
                    best.embedding = await self.embedder.embed_text(merged)
                    _rewrite_md_file(best.id, merged)

                    vs = VersionService(self.session)
                    await vs.save_version(
                        entity_type="incident_history",
                        entity_id=str(best.id),
                        content=merged,
                        change_source="auto",
                    )
                    log.info("Merge result: content updated")
                else:
                    log.info("Merge result: NO_CHANGE")
                best.occurrence_count += 1
                best.last_seen_at = datetime.now(timezone.utc)
                incident.saved_to_memory = True
                await self.session.commit()
                return {"action": "updated", "history_id": str(best.id)}

        # No match → create new
        log.info("Decision: CREATE NEW")
        title = incident.summary_title or incident.description[:80]

        record = IncidentHistory(
            title=title,
            summary_md=summary_md,
            embedding=embedding,
        )
        self.session.add(record)
        incident.saved_to_memory = True
        await self.session.flush()
        # Save initial version
        vs = VersionService(self.session)
        await vs.save_version(
            entity_type="incident_history",
            entity_id=str(record.id),
            content=summary_md,
            change_source="init",
        )
        await self.session.commit()
        await self.session.refresh(record)
        try:
            filename = await _generate_filename(title)
        except Exception:
            filename = title
        _write_md_file(filename, summary_md, record_id=record.id)
        log.info("Created new incident history", id=str(record.id)[:8], title=title)
        return {"action": "created", "history_id": str(record.id)}

    async def list_all(
        self,
        page: int = 1,
        page_size: int = 20,
        query: str | None = None,
    ) -> tuple[list[IncidentHistory], int]:
        base = select(IncidentHistory)
        if query:
            base = base.where(IncidentHistory.title.ilike(f"%{query}%"))

        count_result = await self.session.execute(select(func.count()).select_from(base.subquery()))
        total = count_result.scalar() or 0

        stmt = (
            base.order_by(IncidentHistory.last_seen_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def get(self, history_id: uuid.UUID) -> IncidentHistory | None:
        return await self.session.get(IncidentHistory, history_id)

    async def delete(self, history_id: uuid.UUID) -> bool:
        record = await self.session.get(IncidentHistory, history_id)
        if not record:
            return False
        # 清理版本历史
        vs = VersionService(self.session)
        await vs.delete_versions("incident_history", str(history_id))
        # 清理磁盘 markdown 文件
        _delete_md_file(history_id)
        await self.session.delete(record)
        await self.session.commit()
        return True

    async def search(
        self,
        query: str,
        limit: int = 5,
    ) -> list[dict]:
        query_embedding = await self.embedder.embed_text(query)

        stmt = (
            select(
                IncidentHistory.id,
                IncidentHistory.title,
                IncidentHistory.summary_md,
                IncidentHistory.embedding.cosine_distance(query_embedding).label("distance"),
            )
            .where(IncidentHistory.embedding.isnot(None))
            .order_by("distance")
            .limit(limit * 4)
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        candidates = [
            {
                "id": str(row.id),
                "title": row.title,
                "summary_md": row.summary_md,
                "distance": row.distance,
            }
            for row in rows
        ]

        if not candidates:
            return []

        rerank_results = await self.reranker.rerank(
            query=query,
            documents=[c["summary_md"] for c in candidates],
            top_n=limit,
        )

        results = []
        for rr in rerank_results:
            item = candidates[rr.index].copy()
            item["relevance_score"] = rr.relevance_score
            results.append(item)

        return results
