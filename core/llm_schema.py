from typing import List, Literal, Optional

from pydantic import BaseModel, Field


PayloadType = Literal["SAR", "OPTICAL", "ELINT"]
TargetClass = Literal["plane", "ship", "vehicle"]
DetectionMode = Literal["base_map", "slice"]
Priority = Literal["low", "normal", "high", "urgent"]
StageMode = Literal["auto", "force", "skip"]

class RequirementConstraints(BaseModel):
    """任务约束。"""

    # 兼容旧字段；None 表示交给自动判别。
    need_geo_correction: Optional[bool] = None


class ExecutionPolicy(BaseModel):
    """用户对处理链的控制；未明确指定时保持 auto。"""

    preprocess: StageMode = "auto"
    geo_correction: StageMode = "auto"


class ResourceRequirements(BaseModel):
    """任务执行资源要求。"""

    gpu_required: bool = True

    preferred_device: Literal["GPU", "CPU", "AUTO"] = "GPU"

    max_parallel_tasks: Optional[int] = Field(
        default=None,
        ge=1,
        description="允许的最大并行任务数量",
    )


class OutputRequirements(BaseModel):
    """输出要求。"""

    format: Literal["json"] = "json"

    need_confidence: bool = True

    need_suggestion: bool = True


class RequirementSpec(BaseModel):
    """
    LLM 对用户需求解析之后输出的统一任务需求。

    后续 DecomposeAgent / PlanningAgent
    应主要读取这个结构，而不是直接读取自然语言。
    """

    task_type: str = "multi_payload_detection"

    objective: str = Field(
        ...,
        description="对用户任务目标的简洁描述",
    )

    detection_mode: DetectionMode = "base_map"

    payload_types: List[PayloadType] = Field(
        default_factory=list
    )

    target_classes: List[TargetClass] = Field(
        default_factory=list
    )

    required_capabilities: List[str] = Field(
        default_factory=list,
        description="完成任务所需能力，例如 preprocess、geometry、detect",
    )

    constraints: RequirementConstraints = Field(
        default_factory=RequirementConstraints
    )

    execution_policy: ExecutionPolicy = Field(
        default_factory=ExecutionPolicy
    )

    resources: ResourceRequirements = Field(
        default_factory=ResourceRequirements
    )

    deadline_seconds: Optional[int] = Field(
        default=None,
        ge=1,
        description="任务最大允许完成时间，单位秒",
    )

    priority: Priority = "normal"

    output_requirements: OutputRequirements = Field(
        default_factory=OutputRequirements
    )
