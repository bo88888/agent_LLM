import json
from pathlib import Path

from agents.decompose_agent import DecomposeAgent
from agents.input_agent import InputAgent
from agents.invoker_agent import InvokerAgent
from agents.planning_agent import PlanningAgent
from agents.postprocess_agent import PostprocessAgent
from agents.report_agent import ReportAgent
from agents.understanding_agent import UnderstandingAgent
from config import (
    HTTP_TIMEOUT,
    OUTPUT_REPORT_PATH,
    QUALITY_THRESHOLD,
    REQUIREMENT_XML_PATH,
    TIFF_PATH,
    TOOL_SERVICE_MAP,
)
from core.schema import ExecutionContext, TaskRequest
from mcp.registry import ToolRegistry
from scheduler.scheduler_center import SchedulerCenter


def build_registry() -> ToolRegistry:
    """根据 config.py 中的 TOOL_SERVICE_MAP 创建工具注册表。

    ToolRegistry 保存 tool_name -> service_url 的映射。
    后续 InvokerAgent 会通过 tool_name 找到对应 FastAPI 服务地址。
    """
    registry = ToolRegistry()
    for tool_name, service_url in TOOL_SERVICE_MAP.items():
        registry.register(tool_name, service_url)
    return registry


def assess_quality(context: ExecutionContext, threshold: float):
    """对整个执行结果做简单质量评估。

    当前评估逻辑包括：
    - 子任务是否失败。
    - 子任务是否被依赖阻塞。
    - 工具服务返回的 confidence 是否低于阈值。
    """
    issues = []
    task_summary = []

    for task in context.subtasks:
        # 为最终报告整理每个子任务的执行摘要。
        task_summary.append(
            {
                "subtask_id": task.subtask_id,
                "name": task.name,
                "tool_name": task.tool_name,
                "status": task.status.value,
                "retry_count": task.retry_count,
                "dependencies": task.dependencies,
                "message": context.metadata.get(f"error_{task.subtask_id}")
                or context.metadata.get(f"last_error_{task.subtask_id}")
                or context.metadata.get(f"blocked_{task.subtask_id}", {}).get("reason", ""),
            }
        )

        # 检查任务级别的失败或阻塞。
        if task.status.value == "FAILED":
            issues.append(f"{task.subtask_id} failed")
        elif task.status.value == "BLOCKED":
            blocked_info = context.metadata.get(f"blocked_{task.subtask_id}", {})
            deps = ",".join(blocked_info.get("dependencies", []))
            issues.append(f"{task.subtask_id} blocked by dependency: {deps}")

    # 检查工具结果级别的 success 和 confidence。
    for subtask_id, result in context.tool_results.items():
        if not result.success and f"{subtask_id} failed" not in issues:
            issues.append(f"{subtask_id} failed")
        elif result.confidence < threshold:
            issues.append(f"{subtask_id} low confidence: {result.confidence:.2f}")

    # 写入上下文，后续 ReportAgent 会把它合并进 final_report。
    context.quality_report = {
        "pass": len(issues) == 0,
        "issues": issues,
        "task_summary": task_summary,
    }


def main():
    """主流程入口。

    这里把所有 agent 和调度器串起来，形成完整流水线：
    输入检查 -> 需求理解 -> 任务拆解 -> 规划 -> 调度执行 -> 后处理 -> 质检 -> 报告。
    """
    # 确保输出目录存在。
    Path("outputs").mkdir(exist_ok=True)

    # 构造一次总任务请求。
    request = TaskRequest(
        task_id="TASK_MULTI_001",
        tiff_path=TIFF_PATH,
        requirement_xml_path=REQUIREMENT_XML_PATH,
        payload_types=[],
        target_classes=[],
        target_region={},
        output_requirements={"format": "json", "need_confidence": True, "need_suggestion": True},
    )

    # ExecutionContext 是各个 agent 共享的上下文。
    context = ExecutionContext(request=request)

    # 1. 输入检查：确认数据路径和需求文档路径是否存在。
    context = InputAgent().run(context)

    # 2. 需求理解：读取 requirement.json，生成 parsed_requirement。
    context = UnderstandingAgent().run(context)

    # 3. 任务拆解：根据载荷类型和目标类别生成 SubTask 列表。
    context = DecomposeAgent().run(context)

    # 4. 简单规划：记录 execution_plan，标记依赖图已准备好。
    context = PlanningAgent().run(context)

    # 5. 构建工具注册表，并创建调用器和调度器。
    registry = build_registry()
    invoker = InvokerAgent(registry, timeout=HTTP_TIMEOUT)
    scheduler = SchedulerCenter(invoker)

    # 6. 调度执行：按照 DAG 依赖调用各个 services/*_service 的 /infer 接口。
    context = scheduler.run(context)

    # 7. 后处理摘要：统计过滤结果和融合结果数量。
    context = PostprocessAgent().run(context)

    # 8. 质量评估：检查失败、阻塞和低置信度任务。
    assess_quality(context, QUALITY_THRESHOLD)

    # 9. 最终报告整理：提取 R1 报告结果，并附加 execution_status。
    context = ReportAgent().run(context)

    # 10. 将最终报告写入文件。
    with open(OUTPUT_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(context.final_report, f, ensure_ascii=False, indent=2)

    # 控制台输出，方便直接运行 main.py 时查看结果。
    print("Quality report:", json.dumps(context.quality_report, ensure_ascii=False, indent=2))
    print("Final report path:", OUTPUT_REPORT_PATH)
    print(json.dumps(context.final_report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
