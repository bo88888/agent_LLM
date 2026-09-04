from typing import Dict, Iterable, List, Optional, Tuple

from core.schema import ExecutionContext
from core.schema import SubTask
from core.tool_capabilities import DEFAULT_TOOL_CAPABILITIES, ToolCapability


PREPROCESS_TASK_IDS = {
    "sar_denoise_service": "P1",
    "optical_enhance_service": "P2",
}

DETECTION_TASK_IDS = {
    ("SAR", "plane"): "D1",
    ("SAR", "ship"): "D2",
    ("SAR", "vehicle"): "D3",
    ("OPTICAL", "plane"): "D4",
    ("OPTICAL", "ship"): "D5",
    ("OPTICAL", "vehicle"): "D6",
    ("ELINT", ""): "D7",
}

class DecomposeAgent:
    """任务拆解智能体。
    负责把“一个总任务”拆成多个可调度的 SubTask。
    当前根据 ToolCapability 能力表动态匹配工具，而不是写死一条执行链。
    """

    def __init__(self, registry=None):
        self.registry = registry

    def _capabilities(self) -> Iterable[ToolCapability]:
        if self.registry is not None:
            return self.registry.list_capabilities().values()
        return DEFAULT_TOOL_CAPABILITIES

    def _is_registered(self, tool_name: str) -> bool:
        return self.registry is None or self.registry.has_tool(tool_name)

    def _capability(self, tool_name: str) -> Optional[ToolCapability]:
        for capability in self._capabilities():
            if capability.tool_name == tool_name:
                return capability
        return None

    def _matching_capabilities(self, stage: str, mode: str) -> List[ToolCapability]:
        return [
            capability
            for capability in self._capabilities()
            if capability.stage == stage
            and mode in capability.modes
            and self._is_registered(capability.tool_name)
        ]

    def _append_skip(
        self,
        context: ExecutionContext,
        capability: ToolCapability,
        reason: str,
        payload_type: str = "",
        target_class: str = "",
    ):
        context.skipped_tools.append(
            {
                "tool_name": capability.tool_name,
                "stage": capability.stage,
                "payload_type": payload_type,
                "target_class": target_class,
                "reason": reason,
            }
        )

    def _build_task(
        self,
        subtask_id: str,
        capability: ToolCapability,
        dependencies: Optional[List[str]] = None,
        parameters: Optional[Dict] = None,
        reason: str = "",
        optional: Optional[bool] = None,
    ) -> SubTask:
        return SubTask(
            subtask_id=subtask_id,
            name=capability.display_name,
            tool_name=capability.tool_name,
            dependencies=dependencies or [],
            parameters=parameters or {},
            stage=capability.stage,
            capability_id=capability.capability_id,
            reason=reason,
            optional=capability.optional if optional is None else optional,
            fallback_tools=list(capability.fallback_tools),
        )

    def _build_slice_tasks(self, context: ExecutionContext, mode: str) -> List[SubTask]:
        slice_capabilities = self._matching_capabilities("detect", mode)
        tasks: List[SubTask] = []
        for capability in slice_capabilities:
            if capability.tool_name != "slice_detection_service":
                continue
            params = {"mode": "slice"}
            params.update(context.parsed_requirement.get("slice_inputs", {}))
            tasks.append(
                self._build_task(
                    "SLICE_01",
                    capability,
                    parameters=params,
                    reason="slice mode selects the slice detection capability",
                )
            )
        if not tasks:
            context.metadata["decompose_error"] = "slice_detection_service is not registered"
        return tasks

    def _build_preprocess_tasks(
        self, context: ExecutionContext, mode: str
    ) -> Tuple[List[SubTask], List[str], List[str]]:
        req = context.parsed_requirement
        payload_types = set(req.get("payload_types", []))
        input_path = req.get("tiff_path", "")

        tasks: List[SubTask] = []
        geo_deps: List[str] = []
        valid_payloads: List[str] = []

        decision = req.get("stage_decisions", {}).get("preprocess", {})
        run_preprocess = decision.get("decision", "execute") == "execute"
        # 跳过预处理不代表输入无效，检测可以直接读取原始 TIFF。
        valid_payloads = [
            payload for payload in payload_types
            if payload in {"SAR", "OPTICAL", "ELINT"}
        ]

        for capability in self._matching_capabilities("preprocess", mode):
            payload = capability.payload_types[0] if capability.payload_types else ""
            if payload not in payload_types:
                continue

            if not run_preprocess:
                self._append_skip(
                    context,
                    capability,
                    decision.get("reason", "智能策略跳过预处理"),
                    payload_type=payload,
                )
                continue

            subtask_id = PREPROCESS_TASK_IDS.get(
                capability.tool_name, f"P{len(tasks) + 1}"
            )
            params = {"mode": mode, "tiff_path": input_path}
            tasks.append(
                self._build_task(
                    subtask_id,
                    capability,
                    parameters=params,
                    reason=decision.get("reason", f"{payload}预处理被选中"),
                    optional=True,
                )
            )
            geo_deps.append(subtask_id)

        return tasks, geo_deps, valid_payloads

    def _build_geo_task(
        self,
        context: ExecutionContext,
        mode: str,
        geo_deps: List[str],
    ) -> List[SubTask]:
        decision = context.parsed_requirement.get(
            "stage_decisions", {}
        ).get("geometry", {})
        need_geo = decision.get("decision", "execute") == "execute"
        payload_types = context.parsed_requirement.get("payload_types") or []
        if not any(payload in {"SAR", "OPTICAL"} for payload in payload_types):
            return []

        if not need_geo:
            capability = self._capability("geo_correction_service")
            if capability is not None:
                self._append_skip(
                    context,
                    capability,
                    decision.get("reason", "智能策略跳过几何精校正"),
                )
            return []

        capability = self._capability("geo_correction_service")
        if capability is None or not self._is_registered(capability.tool_name):
            context.metadata["decompose_error"] = "geo_correction_service is not registered"
            return []
        target_classes = context.parsed_requirement.get("target_classes")

        if not target_classes or len(target_classes) == 0:
            context.metadata["decompose_error"] = "Missing required target_classes for geo_correction"
            print(f"[ERROR] 几何校正任务创建失败: 缺少 target_classes 参数")
            return []

        primary_target = target_classes[0]

        primary_payload = payload_types[0].lower() if payload_types else ""
        params = {
            "mode": mode,
            "target_resolution": "2m",
            "source_resolution": "200m",
            "target_class": primary_target,
            "payload_type": primary_payload,
            "input_preference": "preprocessed" if geo_deps else "raw",
        }
        return [
            self._build_task(
                "P3",
                capability,
                dependencies=list(geo_deps),
                parameters=params,
                reason=decision.get("reason", "智能策略选择几何精校正"),
                optional=True,
            )
        ]

    def _build_detection_tasks(
        self,
        context: ExecutionContext,
        mode: str,
        valid_payloads: List[str],
        geo_task_ids: List[str],
    ) -> List[SubTask]:
        req = context.parsed_requirement
        requested_payloads = set(req.get("payload_types", []))
        valid_payload_set = set(valid_payloads)
        target_classes = set(req.get("target_classes", []))
        tasks: List[SubTask] = []

        for capability in self._matching_capabilities("detect", mode):
            if capability.tool_name == "slice_detection_service":
                continue

            payload = capability.payload_types[0] if capability.payload_types else ""
            target = capability.target_classes[0] if capability.target_classes else ""

            if payload and payload not in requested_payloads:
                continue
            if target and target not in target_classes:
                continue

            if payload in {"SAR", "OPTICAL"} and payload not in valid_payload_set:
                self._append_skip(
                    context,
                    capability,
                    f"{payload} detection skipped because no valid preprocessing input was available",
                    payload_type=payload,
                    target_class=target,
                )
                continue

            preprocess_id = {
                "SAR": PREPROCESS_TASK_IDS["sar_denoise_service"],
                "OPTICAL": PREPROCESS_TASK_IDS["optical_enhance_service"],
            }.get(payload)
            generated_ids = {item.subtask_id for item in context.subtasks}
            if geo_task_ids:
                dependencies = list(geo_task_ids)
                input_preference = "geo"
            elif preprocess_id and preprocess_id in generated_ids:
                dependencies = [preprocess_id]
                input_preference = "preprocessed"
            else:
                dependencies = []
                input_preference = "raw"

            subtask_id = DETECTION_TASK_IDS.get(
                (payload, target), f"D{len(tasks) + 1}"
            )
            params = {
                "mode": mode,
                "tiff_path": req.get("tiff_path", ""),
                "payload_type": payload.lower(),
                "input_preference": input_preference,
                "adaptive_attempt": 0,
            }
            reason = (
                f"{payload} {target} detection requested; input={input_preference}"
                if target
                else f"{payload} auxiliary detection requested"
            )
            tasks.append(
                self._build_task(
                    subtask_id,
                    capability,
                    dependencies=dependencies,
                    parameters=params,
                    reason=reason,
                )
            )

        return tasks

    def run(self, context: ExecutionContext) -> ExecutionContext:
        context.metadata["decompose_strategy"] = "capability_matching_v1"
        context.skipped_tools = []

        mode = context.parsed_requirement.get("detection_mode", "base_map")
        if mode == "slice":
            context.subtasks = self._build_slice_tasks(context, mode)
            return context

        preprocess_tasks, geo_deps, valid_payloads = self._build_preprocess_tasks(
            context, mode
        )
        geo_tasks = self._build_geo_task(context, mode, geo_deps)
        # 暂存上游任务，使检测节点能够选择最短有效依赖链。
        context.subtasks = preprocess_tasks + geo_tasks
        detection_tasks = self._build_detection_tasks(
            context,
            mode,
            valid_payloads,
            [task.subtask_id for task in geo_tasks],
        )

        context.subtasks = preprocess_tasks + geo_tasks + detection_tasks
        return context
