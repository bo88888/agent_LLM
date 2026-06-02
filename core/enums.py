from enum import Enum


class PayloadType(str, Enum):
    """支持的载荷类型枚举。

    当前代码主要直接使用字符串，例如 "SAR"。
    这个枚举可以用于后续做更严格的类型约束。
    """

    # 合成孔径雷达载荷。
    SAR = "SAR"

    # 光学遥感载荷。
    OPTICAL = "OPTICAL"

    # 电子侦察载荷。
    ELINT = "ELINT"


class TargetClass(str, Enum):
    """支持的目标类别枚举。"""

    # 飞机目标。
    PLANE = "plane"

    # 船舶目标。
    SHIP = "ship"

    # 车辆目标。
    VEHICLE = "vehicle"


class TaskStatus(str, Enum):
    """子任务执行状态枚举。

    IntelligentScheduler 会根据工具服务调用结果更新这些状态。
    """

    # 等待执行。
    PENDING = "PENDING"

    # 正在执行。
    RUNNING = "RUNNING"

    # 执行成功。
    SUCCESS = "SUCCESS"

    # 执行失败，且已经不能继续重试。
    FAILED = "FAILED"

    # 因依赖任务失败或不存在而被阻塞。
    BLOCKED = "BLOCKED"

    # 可选任务在失败重规划后被跳过。
    SKIPPED = "SKIPPED"
