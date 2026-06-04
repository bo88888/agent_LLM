import requests

from mcp.protocol import MCPRequest, MCPResponse


class BaseHTTPClient:
    """同步 HTTP 客户端。

    这个类和 AsyncHTTPClient 的职责类似：
    - 把 MCPRequest 转换成 HTTP JSON payload。
    - POST 到算法服务的 /infer 接口。
    - 把服务返回 JSON 转成 MCPResponse。

    当前主流程使用的是 AsyncHTTPClient，本类保留为同步调用版本，
    适合测试、调试或以后不需要并发调用的场景。
    """

    def __init__(self, timeout: int = 60):
        # 单个 HTTP 请求的超时时间，单位为秒。
        self.timeout = timeout

    def post_mcp(self, url: str, request: MCPRequest) -> MCPResponse:

        # 将 dataclass 对象转换成普通 dict。
        # FastAPI 服务里的 infer(payload: dict) 收到的就是这个 payload。
        payload = {
            "task_id": request.task_id,
            "subtask_id": request.subtask_id,
            "tool_name": request.tool_name,
            "input_data": request.input_data,
            "parameters": request.parameters,
            "output_schema": request.output_schema,
        }

        # 发起同步 POST 请求。
        # json=payload 表示 requests 会自动序列化 JSON，并设置合适的请求头。
        resp = requests.post(url, json=payload, timeout=self.timeout)

        # HTTP 层失败时抛出异常，例如 404、500、连接失败等。
        resp.raise_for_status()

        # 服务返回的 JSON 应符合 MCPResponse 协议字段。
        data = resp.json()

        # 转换成项目内部统一使用的 MCPResponse。
        return MCPResponse(
            subtask_id=data["subtask_id"],
            tool_name=data["tool_name"],
            success=data["success"],
            output=data["output"],
            message=data.get("message", ""),
            confidence=data.get("confidence"),
        )
