import asyncio
from typing import List

from core.enums import TaskStatus
from core.schema import ExecutionContext, SubTask, ToolResult


class SchedulerCenter:
    """根据依赖状态调度子任务，并保留可报告的失败信息。"""

    def __init__(self, invoker_agent):
        self.invoker_agent = invoker_agent

    def _ready_tasks(self, context: ExecutionContext) -> List[SubTask]:
        ready = []
        for task in context.subtasks:
            if task.status != TaskStatus.PENDING:
                continue
            # 打印调试信息
            deps_status = {dep: context.tool_results.get(dep) for dep in task.dependencies}
            print(f"[调度调试] 检查任务 {task.subtask_id}, 依赖状态: {deps_status}")
            
            all_deps_ok = True
            for dep in task.dependencies:
                dep_result = context.tool_results.get(dep)
                if dep_result is None or not dep_result.success:
                    all_deps_ok = False
                    break

            if all_deps_ok:
                ready.append(task)
        return ready

    def _blocked_tasks(self, context: ExecutionContext) -> List[SubTask]:
        blocked = []
        # 定义终端失败状态：一旦进入这些状态，永远不会再执行
        terminal_failure = {TaskStatus.FAILED, TaskStatus.BLOCKED}
        task_by_id = {task.subtask_id: task for task in context.subtasks}

        for task in context.subtasks:
            if task.status != TaskStatus.PENDING:
                continue
            # 只要有一个依赖处于终端失败状态 → 当前任务被阻塞
            for dep in task.dependencies:
                dep_task = task_by_id.get(dep)
                if dep_task is None or dep_task.status in terminal_failure:
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
            confidence=0.0,
            message=message,
        )

    def _mark_blocked_tasks(self, context: ExecutionContext, tasks: List[SubTask]):
        task_by_id = {task.subtask_id: task for task in context.subtasks}

        for task in tasks:
            failed_deps = [
                dep
                for dep in task.dependencies
                if dep not in task_by_id
                or task_by_id[dep].status in {TaskStatus.FAILED, TaskStatus.BLOCKED}
            ]
            task.status = TaskStatus.BLOCKED
            context.metadata[f"blocked_{task.subtask_id}"] = {
                "reason": "dependency_failed",
                "dependencies": failed_deps,
            }

    def _retry_or_fail(self, context: ExecutionContext, task: SubTask, message: str):
        # 如果重试次数未用完 → 重试
        if task.retry_count < task.max_retry:
            task.retry_count += 1
            task.status = TaskStatus.PENDING
            # 记录重试次数和上次错误信息
            context.metadata[f"retry_{task.subtask_id}"] = task.retry_count
            context.metadata[f"last_error_{task.subtask_id}"] = message
            return
        # 重试次数用完 → 标记为失败
        task.status = TaskStatus.FAILED
        self._record_failure(context, task, message)

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
                break

            for task in ready_tasks:
                task.status = TaskStatus.RUNNING

            results = await self.invoker_agent.invoke_many(context, ready_tasks)

            for task, result in zip(ready_tasks, results):
                if isinstance(result, Exception):
                    self._retry_or_fail(context, task, str(result))
                    continue

                context.tool_results[task.subtask_id] = result
                if result.success:
                    task.status = TaskStatus.SUCCESS
                else:
                    self._retry_or_fail(context, task, result.message)

        return context

    def run(self, context: ExecutionContext) -> ExecutionContext:
        return asyncio.run(self.run_async(context))
