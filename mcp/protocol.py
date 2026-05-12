from dataclasses import dataclass
from typing import Any, Dict, List


"""MCP 协议数据结构。

本项目里的 MCP 可以理解为一套“工具服务调用协议”：
- 调度器发给算法服务的是 MCPRequest。
- 算法服务返回给调度器的是 MCPResponse。

这些类只定义数据形状，不负责网络请求，也不负责算法执行。
"""


@dataclass
class MCPRequest:
    """调度器发给某个算法服务的请求。

    这个对象最终会被 AsyncHTTPClient/BaseHTTPClient 转成 JSON，
    发送到 services/*_service/app.py 的 /infer 接口。
    """

    # 总任务 ID，例如 TASK_MULTI_001。
    task_id: str

    # 当前子任务 ID，例如 P1、D7、F2。
    subtask_id: str

    # 当前子任务要调用的工具服务名，例如 sar_denoise_service。
    tool_name: str

    # 主要输入数据。
    # 通常包含 tiff_path、parsed_requirement、previous_results、metadata。
    input_data: Dict[str, Any]

    # 当前子任务的专属参数，例如几何校正的分辨率参数。
    parameters: Dict[str, Any]

    # 期望算法服务在 output 中返回哪些字段。
    # 例如 sar_denoise_service 对应 ["sar_denoised_path"]。
    output_schema: List[str]


@dataclass
class MCPResponse:
    """算法服务返回给调度器的响应。

    每个 services/*_service/app.py 的 infer 函数都应该返回这些字段。
    HTTP client 会把返回 JSON 解析成 MCPResponse。
    """

    # 响应对应的子任务 ID，通常原样返回请求里的 subtask_id。
    subtask_id: str

    # 响应对应的工具服务名，通常原样返回请求里的 tool_name。
    tool_name: str

    # 业务执行是否成功。
    # HTTP 成功不等于业务成功；如果算法失败，应返回 success=False。
    success: bool

    # 算法输出主体，例如 {"detections": [...]} 或 {"fused_targets": [...]}。
    output: Dict[str, Any]

    # 结果置信度，范围通常是 0.0-1.0。
    confidence: float

    # 可选说明文本，常用于成功提示或失败原因。
    message: str = ""
