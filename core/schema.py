from dataclasses import dataclass, field
from typing import Any, Dict, List

from core.enums import TaskStatus


@dataclass
class TaskRequest:
    """用户/主程序提交给调度系统的总任务请求。

    main.py 会先创建 TaskRequest，再放入 ExecutionContext。
    后续所有 agent 都围绕这个请求展开处理。
    """

    # 总任务 ID，用于标识一次完整流程。
    task_id: str
    tiff_path: str
    requirement_xml_path: str
    payload_types: List[str] = field(default_factory=list)
    target_classes: List[str] = field(default_factory=list)
    target_region: Dict[str, Any] = field(default_factory=dict)
    slice_size: str = "1k*1k"
    output_requirements: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SubTask:
    """一个可调度的子任务节点。

    router.py 会把总任务拆成多个 SubTask。
    SchedulerCenter 再根据 dependencies 和 status 调度这些 SubTask。
    """

    # 子任务 ID，例如 P1、D3、F2、R1。
    subtask_id: str

    # 人类可读的任务名称。
    name: str

    # 要调用的工具服务名，必须能在 ToolRegistry 中找到对应 URL。
    tool_name: str

    # 当前任务依赖哪些前置任务的 subtask_id。
    dependencies: List[str] = field(default_factory=list)

    # 调用工具服务时传入的额外参数。
    parameters: Dict[str, Any] = field(default_factory=dict)

    # 当前任务状态，调度器会根据执行进度更新它。
    status: TaskStatus = TaskStatus.PENDING

    # 当前已经重试过几次。
    retry_count: int = 0

    # 最大重试次数。默认 1 表示失败后最多再尝试一次。
    max_retry: int = 1


@dataclass
class ToolResult:
    """一个工具服务执行后的结果。

    InvokerAgent 会把服务返回的 MCPResponse 转成 ToolResult。
    SchedulerCenter 会把它保存到 context.tool_results[subtask_id]。
    """

    # 结果对应哪个子任务。
    subtask_id: str

    # 结果来自哪个工具服务。
    tool_name: str

    # 业务执行是否成功。
    success: bool

    # 工具服务实际输出。
    output: Dict[str, Any]

    # 服务返回的置信度。
    confidence: float = 0.0

    # 服务返回的说明信息或错误原因。
    message: str = ""


@dataclass
class ExecutionContext:
    """一次完整任务运行过程中的共享上下文。

    各个 agent 不是直接互相传很多参数，而是读写同一个 ExecutionContext。
    这也是当前“多智能体流水线协作”的核心数据载体。
    """

    # 原始任务请求。
    request: TaskRequest

    # UnderstandingAgent 解析 requirement.json 后写入这里。
    parsed_requirement: Dict[str, Any] = field(default_factory=dict)

    # DecomposeAgent/router.py 生成的所有子任务。
    subtasks: List[SubTask] = field(default_factory=list)

    # PlanningAgent 生成的执行计划，目前主要保存 subtask_id 顺序。
    execution_plan: List[str] = field(default_factory=list)

    # 所有已执行工具服务的结果，key 是 subtask_id。
    tool_results: Dict[str, ToolResult] = field(default_factory=dict)

    # ReportAgent 生成的最终报告。
    final_report: Dict[str, Any] = field(default_factory=dict)

    # 质量评估结果，由 main.py 中 assess_quality 写入。
    quality_report: Dict[str, Any] = field(default_factory=dict)

    # 辅助元数据，例如输入校验、调度错误、重试次数、阻塞原因等。
    metadata: Dict[str, Any] = field(default_factory=dict)
