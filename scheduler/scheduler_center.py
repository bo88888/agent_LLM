import asyncio
from typing import List

from agents.replan_agent import ReplanDecisionAgent
from core.enums import TaskStatus
from core.schema import ExecutionContext, SubTask, ToolResult


class IntelligentScheduler:
    """Dependency scheduler with trace recording and deterministic replanning."""

    def __init__(self, invoker_agent, replan_agent=None):
        self.invoker_agent = invoker_agent
        self.replan_agent = replan_agent or ReplanDecisionAgent()

    def _record_trace(self, context: ExecutionContext, event: str, **payload):
        context.execution_trace.append(
            {
                "step": len(context.execution_trace) + 1,
                "event": event,
                **payload,
            }
        )

    def _record_replan(self, context: ExecutionContext, event: str, **payload):
        context.replan_events.append(
            {
                "event": event,
                **payload,
            }
        )

    def _task_by_id(self, context: ExecutionContext):
        return {task.subtask_id: task for task in context.subtasks}

    def _trace_exists(self, context: ExecutionContext, event: str, task: SubTask) -> bool:
        return any(
            item.get("event") == event and item.get("subtask_id") == task.subtask_id
            for item in context.execution_trace
        )

    def _dependency_satisfied(
        self,
        context: ExecutionContext,
        dep_id: str,
        task_by_id,
    ) -> bool:
        dep_task = task_by_id.get(dep_id)
        if dep_task is not None and dep_task.status == TaskStatus.SKIPPED:
            return dep_task.optional

        dep_result = context.tool_results.get(dep_id)
        return dep_result is not None and dep_result.success

    def _ready_tasks(self, context: ExecutionContext) -> List[SubTask]:
        ready = []
        task_by_id = self._task_by_id(context)
        for task in context.subtasks:
            if task.status != TaskStatus.PENDING:
                continue

            all_deps_ok = all(
                self._dependency_satisfied(context, dep, task_by_id)
                for dep in task.dependencies
            )
            if all_deps_ok:
                ready.append(task)
                if not self._trace_exists(context, "task_ready", task):
                    self._record_trace(
                        context,
                        "task_ready",
                        subtask_id=task.subtask_id,
                        tool_name=task.tool_name,
                        dependencies=task.dependencies,
                        reason=task.reason,
                    )
        return ready

    def _blocked_tasks(self, context: ExecutionContext) -> List[SubTask]:
        blocked = []
        terminal_failure = {TaskStatus.FAILED, TaskStatus.BLOCKED}
        task_by_id = self._task_by_id(context)

        for task in context.subtasks:
            if task.status != TaskStatus.PENDING:
                continue

            for dep in task.dependencies:
                dep_task = task_by_id.get(dep)
                if dep_task is None:
                    blocked.append(task)
                    break
                if dep_task.status == TaskStatus.SKIPPED and dep_task.optional:
                    continue
                if dep_task.status in terminal_failure:
                    blocked.append(task)
                    break

        return blocked

    def _record_failure(self, context: ExecutionContext, task: SubTask, message: str):
        context.metadata[f"error_{task.subtask_id}"] = message
        context.tool_results[task.subtask_id] = ToolResult(
            subtask_id=task.subtask_id,
            tool_name=task.tool_name,
            success=False,
            output={},
            message=message,
        )

    def _mark_blocked_tasks(self, context: ExecutionContext, tasks: List[SubTask]):
        task_by_id = self._task_by_id(context)

        for task in tasks:
            failed_deps = [
                dep
                for dep in task.dependencies
                if dep not in task_by_id
                or task_by_id[dep].status in {TaskStatus.FAILED, TaskStatus.BLOCKED}
                or (
                    task_by_id[dep].status == TaskStatus.SKIPPED
                    and not task_by_id[dep].optional
                )
            ]
            task.status = TaskStatus.BLOCKED
            context.metadata[f"blocked_{task.subtask_id}"] = {
                "reason": "dependency_failed",
                "dependencies": failed_deps,
            }
            self._record_trace(
                context,
                "task_blocked",
                subtask_id=task.subtask_id,
                tool_name=task.tool_name,
                dependencies=failed_deps,
            )
            self._record_replan(
                context,
                "blocked",
                subtask_id=task.subtask_id,
                reason="dependency_failed",
                dependencies=failed_deps,
            )

    def _apply_fallback(
        self,
        context: ExecutionContext,
        task: SubTask,
        fallback_tool: str,
        message: str,
    ):
        original_tool = task.tool_name
        capability = self.invoker_agent.registry.get_capability(fallback_tool)
        task.tool_name = fallback_tool
        task.name = capability.display_name
        task.stage = capability.stage
        task.capability_id = capability.capability_id
        task.optional = capability.optional
        task.fallback_tools = list(capability.fallback_tools)
        task.retry_count = 0
        task.status = TaskStatus.PENDING
        task.reason = f"fallback selected after {original_tool} failed: {message}"
        context.metadata[f"fallback_{task.subtask_id}"] = {
            "from": original_tool,
            "to": fallback_tool,
            "reason": message,
        }
        context.tool_results.pop(task.subtask_id, None)

    def _handle_failure(
        self,
        context: ExecutionContext,
        task: SubTask,
        message: str,
    ):
        self._record_trace(
            context,
            "task_failed_attempt",
            subtask_id=task.subtask_id,
            tool_name=task.tool_name,
            retry_count=task.retry_count,
            message=message,
        )

        decision = self.replan_agent.decide(
            context,
            task,
            message,
            self.invoker_agent.registry,
        )

        if decision.action == "retry":
            task.retry_count += 1
            task.status = TaskStatus.PENDING
            context.metadata[f"retry_{task.subtask_id}"] = task.retry_count
            context.metadata[f"last_error_{task.subtask_id}"] = message
            self._record_trace(
                context,
                "task_retry_scheduled",
                subtask_id=task.subtask_id,
                tool_name=task.tool_name,
                retry_count=task.retry_count,
                reason=decision.reason,
            )
            self._record_replan(
                context,
                "retry",
                subtask_id=task.subtask_id,
                tool_name=task.tool_name,
                retry_count=task.retry_count,
                reason=decision.reason,
            )
            return

        if decision.action == "fallback":
            self._apply_fallback(context, task, decision.fallback_tool, message)
            self._record_trace(
                context,
                "task_fallback_scheduled",
                subtask_id=task.subtask_id,
                fallback_tool=decision.fallback_tool,
                reason=decision.reason,
            )
            self._record_replan(
                context,
                "fallback_selected",
                subtask_id=task.subtask_id,
                fallback_tool=decision.fallback_tool,
                reason=decision.reason,
            )
            return

        if decision.action == "skip":
            task.status = TaskStatus.SKIPPED
            task.skip_reason = decision.reason
            context.tool_results.pop(task.subtask_id, None)
            context.skipped_tools.append(
                {
                    "subtask_id": task.subtask_id,
                    "tool_name": task.tool_name,
                    "stage": task.stage,
                    "reason": decision.reason,
                }
            )
            self._record_trace(
                context,
                "task_skipped",
                subtask_id=task.subtask_id,
                tool_name=task.tool_name,
                reason=decision.reason,
            )
            self._record_replan(
                context,
                "skip",
                subtask_id=task.subtask_id,
                tool_name=task.tool_name,
                reason=decision.reason,
            )
            return

        task.status = TaskStatus.FAILED
        self._record_failure(context, task, decision.reason)
        self._record_trace(
            context,
            "task_failed",
            subtask_id=task.subtask_id,
            tool_name=task.tool_name,
            reason=decision.reason,
        )
        self._record_replan(
            context,
            "fail",
            subtask_id=task.subtask_id,
            tool_name=task.tool_name,
            reason=decision.reason,
        )

    async def run_async(self, context: ExecutionContext) -> ExecutionContext:
        while True:
            pending = [t for t in context.subtasks if t.status == TaskStatus.PENDING]
            if not pending:
                break

            ready_tasks = self._ready_tasks(context)
            if not ready_tasks:
                blocked_tasks = self._blocked_tasks(context)
                if blocked_tasks:
                    self._mark_blocked_tasks(context, blocked_tasks)
                    continue

                context.metadata["scheduler_error"] = {
                    "reason": "no_ready_tasks",
                    "pending_tasks": [task.subtask_id for task in pending],
                }
                self._record_replan(
                    context,
                    "scheduler_stalled",
                    reason="no_ready_tasks",
                    pending_tasks=[task.subtask_id for task in pending],
                )
                break

            for task in ready_tasks:
                task.status = TaskStatus.RUNNING
                self._record_trace(
                    context,
                    "task_started",
                    subtask_id=task.subtask_id,
                    tool_name=task.tool_name,
                    stage=task.stage,
                )

            results = await self.invoker_agent.invoke_many(context, ready_tasks)

            for task, result in zip(ready_tasks, results):
                if isinstance(result, Exception):
                    self._handle_failure(
                        context,
                        task,
                        str(result) or result.__class__.__name__,
                    )
                    continue

                if result.success:
                    context.tool_results[task.subtask_id] = result
                    task.status = TaskStatus.SUCCESS
                    payload = {
                        "subtask_id": task.subtask_id,
                        "tool_name": task.tool_name,
                        "message": result.message,
                    }
                    if result.confidence is not None:
                        payload["confidence"] = result.confidence
                    self._record_trace(context, "task_succeeded", **payload)
                else:
                    self._handle_failure(context, task, result.message)

        return context

    def run(self, context: ExecutionContext) -> ExecutionContext:
        return asyncio.run(self.run_async(context))


SchedulerCenter = IntelligentScheduler

