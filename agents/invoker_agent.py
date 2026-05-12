from typing import Dict, List

from clients.async_http_client import AsyncHTTPClient
from core.schema import ExecutionContext, SubTask, ToolResult
from mcp.registry import ToolRegistry
from mcp.wrapper import MCPWrapper


class InvokerAgent:
    """执行端智能体：通过 MCP 和 HTTP 调用算法服务。"""

    def __init__(self, registry: ToolRegistry, timeout: int = 60):
        self.registry = registry # 工具注册表：工具名 → 服务URL
        self.client = AsyncHTTPClient(timeout=timeout)# 异步HTTP客户端

    def output_schema(self, tool_name: str) -> List[str]:
        schema_map: Dict[str, List[str]] = {
            "sar_denoise_service": ["sar_denoised_path"],
            "optical_enhance_service": ["optical_enhanced_path"],
            "geo_correction_service": ["geo_corrected_path", "target_resolution"],
            "sar_aircraft_service": ["detections"],
            "sar_ship_service": ["detections"],
            "sar_vehicle_service": ["detections"],
            "optical_aircraft_service": ["detections"],
            "optical_ship_service": ["detections"],
            "optical_vehicle_service": ["detections"],
            "elint_detection_service": ["detections"],
            "false_alarm_filter_service": ["filtered_detections", "removed_false_alarms"],
            "qb_fusion_service": ["fused_targets"],
            "report_service": ["final_report"],
        }
        return schema_map.get(tool_name, [])

    async def invoke_one(self, context: ExecutionContext, subtask: SubTask) -> ToolResult:
        request = MCPWrapper.build_request(context, subtask, self.output_schema(subtask.tool_name))
        service_url = self.registry.get(subtask.tool_name)
        response = await self.client.post_mcp(service_url, request)

        return ToolResult(
            subtask_id=response.subtask_id,
            tool_name=response.tool_name,
            success=response.success,
            output=response.output,
            confidence=response.confidence,
            message=response.message,
        )

    async def invoke_many(self, context: ExecutionContext, subtasks: List[SubTask]):
        return await self.client.gather(self.invoke_one(context, t) for t in subtasks)
