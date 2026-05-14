from core.router import build_detection_tasks, build_postprocess_tasks, build_preprocess_tasks
from core.schema import ExecutionContext


class DecomposeAgent:
    """任务拆解智能体。

    负责把“一个总任务”拆成多个可调度的 SubTask。
    具体拆解规则放在 core/router.py 中。
    """

    def run(self, context: ExecutionContext) -> ExecutionContext:

        # 预处理任务，例如 SAR 去噪、光学增强、几何校正。
        preprocess_tasks = build_preprocess_tasks(context.parsed_requirement)

        # 检测任务，例如 SAR 船舶检测、光学车辆检测、ELINT 检测。
        detection_tasks = build_detection_tasks(context.parsed_requirement)
        
        context.subtasks = preprocess_tasks + detection_tasks
        return context
