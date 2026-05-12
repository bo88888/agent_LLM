from core.schema import ExecutionContext


class PlanningAgent:
    """规划智能体。

    当前实现比较轻量：
    - 不重新排序任务。
    - 不做复杂优化。
    - 只把任务 ID 列表写入 context.execution_plan。

    真正的依赖调度仍由 SchedulerCenter 完成。
    """

    def run(self, context: ExecutionContext) -> ExecutionContext:
        # 保存任务 ID 顺序，方便调试、报告展示或后续扩展。
        context.execution_plan = [task.subtask_id for task in context.subtasks]

        # 标记规划阶段完成，说明任务依赖图已经准备好。
        context.metadata["planning_stage"] = "dependency_graph_ready"
        return context
