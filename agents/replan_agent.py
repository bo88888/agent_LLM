from dataclasses import dataclass

from core.schema import ExecutionContext, SubTask


@dataclass
class ReplanDecision:
    action: str
    reason: str
    fallback_tool: str = ""


class ReplanDecisionAgent:

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

        if task.optional:
            return ReplanDecision(
                action="skip",
                reason=f"optional task failed and can be skipped: {message}",
            )

        return ReplanDecision(
            action="fail",
            reason=f"required task failed after retry budget: {message}",
        )

