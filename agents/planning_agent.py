from core.schema import ExecutionContext


class PlanningAgent:
    """规划智能体。

    当前实现比较轻量：
    - 不重新排序任务。
    - 不做复杂优化。
    - 只把任务 ID 列表写入 context.execution_plan。

    真正的执行反馈、重试和重规划仍由 IntelligentScheduler 完成。
    """

    def run(self, context: ExecutionContext) -> ExecutionContext:
        remaining = {task.subtask_id: task for task in context.subtasks}
        completed = set()
        batches = []
        ordered_plan = []
        batch_index = 1

        while remaining:
            ready = [
                task
                for task in remaining.values()
                if all(dep in completed for dep in task.dependencies)
            ]
            if not ready:
                batches.append(
                    {
                        "batch": batch_index,
                        "tasks": list(remaining.keys()),
                        "reason": "unresolved dependencies remain; scheduler will mark blocked tasks if needed",
                        "task_reasons": {
                            task.subtask_id: task.reason for task in remaining.values()
                        },
                    }
                )
                ordered_plan.extend(remaining.keys())
                break

            task_ids = [task.subtask_id for task in ready]
            stages = sorted({task.stage or "unknown" for task in ready})
            reason = (
                "no dependencies; tasks can run in parallel"
                if batch_index == 1
                else "all upstream dependencies in previous batches are satisfied"
            )
            batches.append(
                {
                    "batch": batch_index,
                    "tasks": task_ids,
                    "stages": stages,
                    "reason": reason,
                    "task_reasons": {task.subtask_id: task.reason for task in ready},
                }
            )
            ordered_plan.extend(task_ids)
            completed.update(task_ids)
            for task_id in task_ids:
                remaining.pop(task_id, None)
            batch_index += 1

        # 保存任务 ID 顺序，方便调试、报告展示或后续扩展。
        context.execution_plan = ordered_plan
        context.plan_rationale = batches

        # 标记规划阶段完成，说明任务依赖图已经准备好。
        context.metadata["planning_stage"] = "dependency_graph_ready"
        return context
