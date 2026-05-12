from typing import List

from core.schema import ExecutionContext, SubTask
from mcp.protocol import MCPRequest


class MCPWrapper:
    """MCP 请求封装器。

    它负责把调度系统内部的 ExecutionContext + SubTask
    转换成算法服务能够理解的 MCPRequest。
    """

    @staticmethod
    def build_request(context: ExecutionContext, subtask: SubTask, output_schema: List[str]) -> MCPRequest:
        """为某个子任务构造 MCPRequest。

        参数：
        - context: 当前完整执行上下文，保存需求、任务列表、历史结果等。
        - subtask: 当前准备调用的子任务。
        - output_schema: 当前工具服务期望返回的 output 字段。
        """
        # 把已经完成的工具结果整理成普通 dict。
        # 注意这里只取 result.output，不把 ToolResult 整个对象传给服务。
        #
        # 例如：
        # {
        #     "P1": {"sar_denoised_path": "..."},
        #     "P2": {"optical_enhanced_path": "..."}
        # }
        # 这里提取了所有已经完成的前置任务的输出，组装成了 "previous_results"
        previous_results = {
            sid: result.output for sid, result in context.tool_results.items()
        }

        # 这个 MCPRequest 会继续交给 HTTP client。
        # HTTP client 会将它转成 JSON payload，并 POST 到服务 /infer。
        return MCPRequest(
            task_id=context.request.task_id,
            subtask_id=subtask.subtask_id,
            tool_name=subtask.tool_name,
            input_data={
                "tiff_path": context.request.tiff_path,
                "xml_config": context.parsed_requirement, # 包含切片大小、区域等
                # 前置任务输出。后续服务靠它读取上游结果。
                "previous_results": previous_results,

                # 调度过程中的辅助信息，例如输入校验、重试、阻塞原因等。
                "metadata": context.metadata,
            },
            # 当前子任务的参数，例如 {"target_resolution": "2m"}。
            parameters=subtask.parameters,
            # 告诉服务本次期望返回哪些 output 字段。
            output_schema=output_schema,
        )
