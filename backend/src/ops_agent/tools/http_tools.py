from src.ops_agent.connectors.http import HTTPConnector


async def http_request(
    method: str,
    url: str,
    headers: str | None = None,
    body: str | None = None,
) -> dict:
    """Execute an HTTP request.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE, PATCH, HEAD)
        url: Full URL to request
        headers: Optional JSON string of headers, e.g. '{"Authorization": "Bearer xxx"}'
        body: Optional request body string

    Returns:
        Dict with status_code, body, and headers.
    """
    import orjson

    parsed_headers = None
    if headers:
        try:
            parsed_headers = orjson.loads(headers)
        except Exception:
            return {"error": f"Invalid headers JSON: {headers}"}

    connector = HTTPConnector()
    try:
        result = await connector.request(
            method=method,
            url=url,
            headers=parsed_headers,
            body=body,
        )
        return {
            "status_code": result.status_code,
            "body": result.body,
            "error": None,
        }
    except Exception as e:
        return {"error": str(e)}
