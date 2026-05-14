from core.schema import ExecutionContext
from services.postprocess_service.processor import build_final_report

class ReportAgent:
    """最终报告整理智能体（本地生成报告并评估系统质量）。"""
    def _assess_quality(self, context: ExecutionContext, threshold: float = 0.75) -> dict:
        """内部方法：对网络调度的执行结果做质量评估"""
        issues = []
        task_summary = []

        for task in context.subtasks:
            task_summary.append({
                "subtask_id": task.subtask_id,
                "name": task.name,
                "tool_name": task.tool_name,
                "status": task.status.value,
                "retry_count": task.retry_count,
                "dependencies": task.dependencies,
                "message": context.metadata.get(f"error_{task.subtask_id}")
                or context.metadata.get(f"last_error_{task.subtask_id}")
                or context.metadata.get(f"blocked_{task.subtask_id}", {}).get("reason", ""),
            })

            if task.status.value == "FAILED":
                issues.append(f"{task.subtask_id} failed")
            elif task.status.value == "BLOCKED":
                blocked_info = context.metadata.get(f"blocked_{task.subtask_id}", {})
                deps = ",".join(blocked_info.get("dependencies", []))
                issues.append(f"{task.subtask_id} blocked by dependency: {deps}")

        for subtask_id, result in context.tool_results.items():
            if not result.success and f"{subtask_id} failed" not in issues:
                issues.append(f"{subtask_id} failed")
            elif result.confidence < threshold:
                issues.append(f"{subtask_id} low confidence: {result.confidence:.2f}")

        return {
            "pass": len(issues) == 0,
            "issues": issues,
            "task_summary": task_summary,
        }

    def run(self, context: ExecutionContext) -> ExecutionContext:
        fused_targets = context.metadata.get("fused_targets", [])
        region = context.parsed_requirement.get("target_region", {})
        task_id = context.request.task_id
        mode = context.parsed_requirement.get("detection_mode", "base_map")
        report_data = build_final_report(fused_targets, task_id, region, mode)
        quality_report = self._assess_quality(context)
        context.quality_report = quality_report

        # 2. 附加调度框架的质量评估状态
        report_data["execution_status"] = {
            "pass": context.quality_report.get("pass", False),
            "issues": context.quality_report.get("issues", []),
            "tasks": context.quality_report.get("task_summary", []),
        }

        context.final_report = report_data
        return context