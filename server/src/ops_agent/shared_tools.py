"""主 Agent 和子 Agent 共享的 skill 上下文构建与工具定义。"""

from src.lib.logger import get_logger
from src.services.skill_service import SkillService

_COMPACT_THRESHOLD = 10


def build_skills_context(skill_service: SkillService) -> str:
    """构建 skills 上下文，包含结构化使用规则和全量 XML 目录。

    两层格式策略:
    - Full format (≤10): <skill><name>...</name><description>...</description></skill>
    - Compact format (>10): <skill name="slug">description</skill> 单行
    """
    skill_log = get_logger(component="skill")
    available = skill_service.get_available_skills()

    if not available:
        skill_log.info("No available skills")
        return ""

    slugs = [s["slug"] for s in available]
    fmt = "compact" if len(available) > _COMPACT_THRESHOLD else "full"
    skill_log.info("build_skills_context", count=len(available), format=fmt, slugs=slugs)

    xml_lines = [
        "\n<available_skills>",
        "使用规则:",
        "1. 通用技能优先: 若存在 `incident-triage`，子 Agent 应默认先"
        ' `read_skill("incident-triage")` 获取分诊骨架，再切到专项技能。',
        "2. 渐进加载: 先读 SKILL.md 主体获取流程概要；scripts/references 等子文件"
        "只在执行到相关步骤时再按需加载。",
        "3. 上下文控制: 技能内容较长时，总结关键步骤和命令，不要大段复制粘贴原文。",
        "4. 多技能协调: 多个技能同时匹配时，选最小必要集合，声明使用顺序和原因。",
        "5. 缺失回退: 若匹配的技能无法读取或不适用当前场景，用通用排查方法继续。",
    ]

    if len(available) > _COMPACT_THRESHOLD:
        for s in available:
            xml_lines.append(f'  <skill name="{s["slug"]}">{s["description"]}</skill>')
    else:
        for s in available:
            xml_lines.append(
                f"  <skill><name>{s['slug']}</name>"
                f"<description>{s['description']}</description></skill>"
            )

    xml_lines.append("</available_skills>")
    return "\n".join(xml_lines)


def build_shared_tools():
    """构建主 Agent 和子 Agent 共享的工具：read_skill、list_servers、list_services。"""
    from langchain_core.tools import tool

    from src.ops_agent.tools.service_exec_tool import list_services as _list_services
    from src.ops_agent.tools.ssh_bash_tool import list_servers as _list_servers

    @tool
    def read_skill(path: str) -> str:
        """读取技能文件。"?" 列出所有可用技能，"slug" 读 SKILL.md，"slug/scripts/x.sh" 读脚本。"""
        service = SkillService()
        if path.strip() == "?":
            available = service.get_available_skills()
            if not available:
                return "当前没有可用技能。"
            lines = ["所有可用技能:"]
            for s in available:
                lines.append(f"- {s['slug']}: {s['description']}")
            return "\n".join(lines)
        parts = path.split("/", 1)
        slug = parts[0]
        rel_path = parts[1] if len(parts) > 1 else None
        try:
            return service.read_file(slug, rel_path)
        except FileNotFoundError:
            return f"未找到: {path}"

    @tool
    async def list_servers() -> list[dict] | str:
        """列出所有可用服务器。返回 id, name, host, status。"""
        result = await _list_servers()
        if not result:
            return "当前没有注册任何服务器。"
        return result

    @tool
    async def list_services() -> list[dict] | str:
        """列出所有可用服务。返回 id, name, service_type, host, port, status。"""
        result = await _list_services()
        if not result:
            return "当前没有注册任何服务。"
        return result

    return [read_skill, list_servers, list_services]
