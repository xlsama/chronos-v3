"""Tests for KB sub agent."""

from src.agent.prompts.kb_agent import KB_AGENT_SYSTEM_PROMPT


class TestKBAgentPrompt:
    def test_prompt_contains_workflow(self):
        assert "search_knowledge_base" in KB_AGENT_SYSTEM_PROMPT

    def test_prompt_contains_output_format(self):
        assert "推荐排查目标" in KB_AGENT_SYSTEM_PROMPT
        assert "涉及的服务" in KB_AGENT_SYSTEM_PROMPT

    def test_prompt_instructs_chinese(self):
        assert "中文" in KB_AGENT_SYSTEM_PROMPT
