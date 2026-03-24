from src.api.schemas import ExtractedService
from src.services.import_connections_service import _build_import_warnings


def test_build_import_warnings_when_nothing_extracted():
    warnings = _build_import_warnings([], [])

    assert warnings == ["未从文档中识别到任何服务或服务器连接信息。"]


def test_build_import_warnings_when_only_services_extracted():
    warnings = _build_import_warnings(
        [ExtractedService(name="redis-dev")],
        [],
    )

    assert len(warnings) == 1
    assert "未识别到可 SSH 的服务器资产" in warnings[0]
