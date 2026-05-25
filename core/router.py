from typing import List
from core.schema import SubTask


def build_preprocess_tasks(req: dict) -> List[SubTask]:
    """根据载荷类型生成预处理阶段任务。

    router.py 的职责是“生成任务图”，不负责执行任务。
    每个 SubTask 只描述：
    - subtask_id: 子任务编号。
    - name: 人类可读的任务名称。
    - tool_name: 实际要调用的服务名。
    - dependencies: 当前任务依赖哪些前置任务。
    - parameters: 调用服务时额外传入的参数。
    """
    tasks: List[SubTask] = []
    # 1. 提取需求数据
    payload_types = req.get("payload_types", [])
    mode = req.get("detection_mode", "base_map")
    input_files = req.get("input_files", {})
    
    # 2. 根据识别模式构造专属参数字典
    base_params = {"mode": mode}
    if mode == "slice":
        base_params.update(req.get("slice_inputs", {}))

    actual_geo_deps = []
    # 如果任务需求里包含 SAR 载荷，则添加 SAR 去噪任务。
    # 该任务没有依赖，可以在调度开始后立即执行。
    if "SAR" in payload_types:
        sar_path = input_files.get("SAR", "")
        # 只有当 XML 里的 <SAR> 标签配了具体的有效文件路径时，该任务才算有效
        if sar_path and sar_path.strip():
            sar_params = base_params.copy()
            sar_params["tiff_path"] = sar_path
            
            tasks.append(
                SubTask(
                    subtask_id="P1",
                    name="SAR denoise",
                    tool_name="sar_denoise_service",
                    parameters=sar_params
                )
            )
            # 记录有效的依赖：P3 必须等待 P1 成功
            actual_geo_deps.append("P1")
        else:
            print("[路由提示] 需求中包含 SAR 载荷，但未提供有效输入文件路径，已自动忽略 P1 节点。")


    # 如果任务需求里包含光学载荷，则添加光学增强任务。
    # 该任务也没有依赖，可以和 P1 并发执行。
    # 检查并添加 光学增强任务
    if "OPTICAL" in payload_types:
        opt_path = input_files.get("OPTICAL", "")
        # 只有当 XML 里的 <OPTICAL> 标签配了具体的有效文件路径时，该任务才算有效
        if opt_path and opt_path.strip():
            opt_params = base_params.copy()
            opt_params["tiff_path"] = opt_path
            
            tasks.append(
                SubTask(
                    subtask_id="P2",
                    name="Optical enhancement",
                    tool_name="optical_enhance_service",
                    parameters=opt_params
                )
            )
            # 记录有效的依赖：P3 必须等待 P2 成功
            actual_geo_deps.append("P2")
        else:
            print("[路由提示] 需求中包含 OPTICAL 载荷，但未提供有效输入文件路径，已自动忽略 P2 节点。")

    # 几何校正需要基于前面的预处理结果。
    # 如果 P1/P2 中至少有一个存在，就添加 P3，并让 P3 依赖所有预处理任务。   
    if actual_geo_deps:
        p3_params = {"target_resolution": "2m", "source_resolution": "200m"}
        p3_params.update(base_params)
        tasks.append(
            SubTask(
                subtask_id="P3",
                name="Geo correction",
                tool_name="geo_correction_service",
                dependencies=actual_geo_deps,  # 🌟 动态绑定！可能是 ["P1"], ["P2"] 或 ["P1", "P2"]
                parameters=p3_params,
            )
        )
    else:
        print("[路由提示] 流水线未检测到任何有效的 SAR 或光学输入图片，不生成 P3 几何校正任务。")

    return tasks
 

def build_detection_tasks(req: dict) -> List[SubTask]:
    """根据载荷类型和目标类型生成检测阶段任务。

    例如：
    - payload_types 包含 SAR，target_classes 包含 aircraft，则生成 SAR 飞机检测 D1。
    - payload_types 包含 OPTICAL，target_classes 包含 ship，则生成光学船舶检测 D5。
    """
    tasks: List[SubTask] = []
    # 1. 提取需求数据
    payload_types = req.get("payload_types", [])
    target_classes = req.get("target_classes", [])
    mode = req.get("detection_mode", "base_map")
    # 2. 根据识别模式构造专属参数字典
    if mode == "base_map":
        task_params = {"mode": "base_map", "tiff_path": req.get("tiff_path", "")}
    else:
        task_params = {"mode": "slice", **req.get("slice_inputs", {})}

    geo_dep = ["P3"] if any(p in payload_types for p in ["SAR", "OPTICAL"]) else []

    # SAR 目标检测任务。
    if "SAR" in payload_types and "aircraft" in target_classes:
        tasks.append(SubTask("D1", "SAR aircraft detection", "sar_aircraft_service", dependencies=geo_dep, parameters=task_params))
    if "SAR" in payload_types and "ship" in target_classes:
        tasks.append(SubTask("D2", "SAR ship detection", "sar_ship_service", dependencies=geo_dep, parameters=task_params))
    if "SAR" in payload_types and "vehicle" in target_classes:
        tasks.append(SubTask("D3", "SAR vehicle detection", "sar_vehicle_service", dependencies=geo_dep, parameters=task_params))

    # 光学目标检测任务。
    if "OPTICAL" in payload_types and "aircraft" in target_classes:
        tasks.append(SubTask("D4", "Optical aircraft detection", "optical_aircraft_service", dependencies=geo_dep, parameters=task_params))
    if "OPTICAL" in payload_types and "ship" in target_classes:
        tasks.append(SubTask("D5", "Optical ship detection", "optical_ship_service", dependencies=geo_dep, parameters=task_params))
    if "OPTICAL" in payload_types and "vehicle" in target_classes:
        tasks.append(SubTask("D6", "Optical vehicle detection", "optical_vehicle_service", dependencies=geo_dep, parameters=task_params))

    # ELINT 检测目前不依赖几何校正。
    # 因此它可以和预处理阶段任务并行执行。
    if "ELINT" in payload_types:
        tasks.append(SubTask("D7", "ELINT detection", "elint_detection_service"))

    return tasks


def build_postprocess_tasks(detection_tasks: List[SubTask]) -> List[SubTask]:
    """生成后处理、融合和报告阶段任务。

    后处理阶段固定为：
    1. F1: 汇总所有检测结果并做虚警过滤。
    2. F2: 对过滤后的检测结果做 QB 融合。
    3. R1: 基于融合结果生成最终报告。
    """
    # 所有检测任务完成之后，F1 才能运行。
    det_ids = [t.subtask_id for t in detection_tasks]

    return [
        SubTask(
            subtask_id="F1",
            name="False alarm filtering",
            tool_name="false_alarm_filter_service",
            dependencies=det_ids,
        ),
        SubTask(
            subtask_id="F2",
            name="QB fusion",
            tool_name="qb_fusion_service",
            dependencies=["F1"],
        ),
        SubTask(
            subtask_id="R1",
            name="Report generation",
            tool_name="report_service",
            dependencies=["F2"],
        ),
    ]
