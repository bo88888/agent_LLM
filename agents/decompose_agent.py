from core.router import build_detection_tasks, build_postprocess_tasks, build_preprocess_tasks
from core.schema import ExecutionContext


class DecomposeAgent:
    """任务拆解智能体。

    负责把“一个总任务”拆成多个可调度的 SubTask。
    具体拆解规则放在 core/router.py 中。
    """

    def run(self, context: ExecutionContext) -> ExecutionContext:
        # UnderstandingAgent 已经把 requirement.json 解析到了 parsed_requirement。
        payloads = context.parsed_requirement["payload_types"]
        targets = context.parsed_requirement["target_classes"]

        # 预处理任务，例如 SAR 去噪、光学增强、几何校正。
        preprocess_tasks = build_preprocess_tasks(payloads)

        # 检测任务，例如 SAR 船舶检测、光学车辆检测、ELINT 检测。
        detection_tasks = build_detection_tasks(payloads, targets)

        # 后处理任务，例如虚警过滤、融合、报告生成。
        post_tasks = build_postprocess_tasks(detection_tasks)

        # 按阶段合并为完整任务列表。
        # 真正执行顺序不是简单按列表顺序，而是由 SchedulerCenter 根据 dependencies 判断。
        context.subtasks = preprocess_tasks + detection_tasks + post_tasks
        return context
