import asyncio
from typing import Any, Iterable

import httpx

from mcp.protocol import MCPRequest, MCPResponse


class AsyncHTTPClient:
    """Async HTTP client used by InvokerAgent to call MCP tool services."""

    def __init__(self, timeout: int = 300):
        self.timeout = timeout

    async def post_mcp(self, url: str, request: MCPRequest) -> MCPResponse:
        payload = {
            "task_id": request.task_id,
            "subtask_id": request.subtask_id,
            "tool_name": request.tool_name,
            "input_data": request.input_data,
            "parameters": request.parameters,
            "output_schema": request.output_schema,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"HTTP timeout after {self.timeout}s while calling "
                f"{request.subtask_id}/{request.tool_name} at {url}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:500] if exc.response is not None else ""
            raise RuntimeError(
                f"HTTP {exc.response.status_code} while calling "
                f"{request.subtask_id}/{request.tool_name} at {url}: {body}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(
                f"HTTP request failed while calling "
                f"{request.subtask_id}/{request.tool_name} at {url}: {exc}"
            ) from exc

        return MCPResponse(
            subtask_id=data["subtask_id"],
            tool_name=data["tool_name"],
            success=data["success"],
            output=data["output"],
            message=data.get("message", ""),
            confidence=data.get("confidence"),
        )

    async def gather(self, coroutines: Iterable[Any]):
        return await asyncio.gather(*coroutines, return_exceptions=True)
