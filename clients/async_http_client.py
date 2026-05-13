import asyncio
from typing import Any, Iterable

import httpx

from mcp.protocol import MCPRequest, MCPResponse


class AsyncHTTPClient:
    """异步 HTTP 客户端。

    InvokerAgent 会把 MCPRequest 交给本类。
    本类负责把 MCPRequest 转成 JSON，通过 HTTP POST 发送到算法服务的 /infer 接口，
    再把服务返回的 JSON 转回 MCPResponse。
    """

    def __init__(self, timeout: int = 60):
        self.timeout = timeout

    async def post_mcp(self, url: str, request: MCPRequest) -> MCPResponse:
        """向某个 MCP 工具服务发送异步 POST 请求。

        参数：
        - url: 具体服务地址，例如 http://127.0.0.1:8101/infer。
        - request: 已经由 MCPWrapper 封装好的 MCPRequest。
        """
        # FastAPI 服务收到的 payload 就是这个字典。
        # services/*_service/app.py 中的 infer(payload: dict) 会读取这些字段。
        payload = {
            "task_id": request.task_id,
            "subtask_id": request.subtask_id,
            "tool_name": request.tool_name,
            "input_data": request.input_data,
            "parameters": request.parameters,
            "output_schema": request.output_schema,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # 向算法服务的 /infer 接口发送 JSON。
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        # 将服务返回的普通 dict 转为项目内部使用的 MCPResponse 数据对象。
        return MCPResponse(
            subtask_id=data["subtask_id"],
            tool_name=data["tool_name"],
            success=data["success"],
            output=data["output"],
            # confidence/message 允许服务不返回；不返回时使用默认值。
            confidence=data.get("confidence", 0.0),
            message=data.get("message", ""),
        )

    async def gather(self, coroutines: Iterable[Any]):
        """并发执行多个异步调用。

        return_exceptions=True 的作用：
        - 某个服务调用失败时，不会让整个并发调用直接崩掉。
        - 异常会作为一个结果返回给 SchedulerCenter。
        - SchedulerCenter 再针对单个失败任务做重试或标记失败。
        """
        return await asyncio.gather(*coroutines, return_exceptions=True)
