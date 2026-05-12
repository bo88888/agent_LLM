from core.schema import ExecutionContext


class ReportAgent:
    """最终报告整理智能体。

    report_service 会生成业务报告内容，对应子任务 R1。
    本 agent 负责把 R1 的结果提取到 context.final_report，
    并把质量评估结果 execution_status 附加进去。
    """

    def run(self, context: ExecutionContext) -> ExecutionContext:
        # R1 是 router.py 中定义的报告生成任务。
        result = context.tool_results.get("R1")

        if result and result.success:
            # report_service 的标准输出是 {"final_report": {...}}。
            # 如果没有 final_report 字段，则退而使用整个 output。
            context.final_report = result.output.get("final_report", result.output)
        else:
            # 如果报告服务没有成功执行，生成一个失败报告，避免最终输出为空。
            context.final_report = {
                "task_id": context.request.task_id,
                "status": "FAILED",
                "message": "Report generation did not complete.",
            }

        # 把质量评估结果附加到最终报告中。
        # assess_quality 在 main.py 中执行，会写入 context.quality_report。
        context.final_report["execution_status"] = {
            "pass": context.quality_report.get("pass", False),
            "issues": context.quality_report.get("issues", []),
            "tasks": context.quality_report.get("task_summary", []),
        }
        return context
