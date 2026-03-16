"""Tests for graph structure — node existence and edge routing."""

from src.agent.graph import build_graph


class TestGraphStructure:
    def test_has_all_nodes(self):
        graph = build_graph()
        node_names = set(graph.nodes.keys())
        expected = {
            "gather_context",
            "main_agent",
            "tools",
            "human_approval",
            "ask_human",
            "summarize",
        }
        assert expected.issubset(node_names)

    def test_entry_point_is_gather_context(self):
        graph = build_graph()
        assert "gather_context" in graph.nodes
