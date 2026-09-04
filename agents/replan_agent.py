from dataclasses import dataclass

from core.schema import ExecutionContext, SubTask


@dataclass
class ReplanDecision:
    action: str
    reason: str
    fallback_tool: str = ""


class ReplanDecisionAgent:
    """Deterministic replan policy; it does not call any LLM/API."""

    def decide(
        self,
        context: ExecutionContext,
        task: SubTask,
        message: str,
        registry,
    ) -> ReplanDecision:
        if task.retry_count < task.max_retry:
            return ReplanDecision(
                action="retry",
                reason=f"retry budget available after failure: {message}",
            )

        for fallback_tool in task.fallback_tools:
            if registry.has_tool(fallback_tool):
                return ReplanDecision(
                    action="fallback",
                    fallback_tool=fallback_tool,
                    reason=f"fallback tool {fallback_tool} is registered",
                )

        # 当前仓库没有注册第二套检测器；先做输入级降级：
        # 校正/增强影像调用失败后改用原始 TIFF 再执行一次。
        if (
            task.stage == "detect"
            and task.parameters.get("input_preference") != "raw"
            and not task.parameters.get("input_fallback_used", False)
        ):
            return ReplanDecision(
                action="degrade_input",
                reason="检测服务重试失败，降级为原始影像输入",
            )

        if task.optional:
            return ReplanDecision(
                action="skip",
                reason=f"optional task failed and can be skipped: {message}",
            )

        return ReplanDecision(
            action="fail",
            reason=f"required task failed after retry budget: {message}",
        )

