from typing import Any, Dict, Optional
from agents.decompose_agent import DecomposeAgent
from agents.input_agent import InputAgent
from agents.planning_agent import PlanningAgent
from agents.understanding_agent import UnderstandingAgent
from core.schema import ExecutionContext
from agents.llm_understanding_agent import LLMUnderstandingAgent



class OrchestratorAgent:
    """Rule-based orchestrator that owns context preparation before scheduling."""

    def __init__(self, registry):
        self.registry = registry

    def _merge_overrides(self, context: ExecutionContext, overrides: Dict[str, Any]):
        for key, value in overrides.items():
            if isinstance(value, dict) and isinstance(
                context.parsed_requirement.get(key), dict
            ):
                merged = dict(context.parsed_requirement[key])
                merged.update(value)
                context.parsed_requirement[key] = merged
            else:
                context.parsed_requirement[key] = value


    def _resolve_xml_and_instruction(
    self,
    xml_requirement: Dict[str, Any],
    llm_data: Dict[str, Any],
    ):
        final_requirement = dict(xml_requirement)
        questions = []

        # =====================================
        # 1. XML中的目标和载荷
        # =====================================

        xml_targets = list(
            xml_requirement.get("target_classes") or []
        )

        xml_payloads = list(
            xml_requirement.get("payload_types") or []
        )

        # =====================================
        # 2. instruction / LLM 提取结果
        # =====================================

        llm_targets = list(
            llm_data.get("target_classes") or []
        )

        llm_payloads = list(
            llm_data.get("payload_types") or []
        )

        # =====================================
        # 3. target_classes 判断
        # =====================================

        if llm_targets:
            # instruction明确说了识别目标

            if xml_targets:
                # XML也有目标

                if set(llm_targets).issubset(set(xml_targets)):
                    # 与XML兼容
                    final_requirement["target_classes"] = llm_targets

                else:
                    # 与XML冲突
                    questions.append({
                        "field": "target_classes",
                        "type": "conflict",
                        "question": (
                            f"用户指令中的识别目标为 {llm_targets}，"
                            f"但XML配置的目标为 {xml_targets}，"
                            "请确认最终需要识别的目标。"
                        ),
                        "xml_value": xml_targets,
                        "instruction_value": llm_targets,
                    })
            else:
                final_requirement["target_classes"] = llm_targets

        else:
            # instruction没有明确目标

            if xml_targets:
                questions.append({
                    "field": "target_classes",
                    "type": "confirm_xml",
                    "question": (
                        f"用户指令未明确识别目标，"
                        f"XML中配置的识别目标为 {xml_targets}，"
                        "是否使用XML中的目标继续执行？"
                    ),
                    "suggested_value": xml_targets,
                })

            else:
                questions.append({
                    "field": "target_classes",
                    "type": "missing",
                    "question": (
                        "用户指令和XML均未明确识别目标，"
                        "请明确需要识别飞机、舰船还是车辆。"
                    ),
                })

        # =====================================
        # 4. payload_types 判断
        # =====================================

        if llm_payloads:
            # instruction明确说了载荷

            if xml_payloads:

                if set(llm_payloads).issubset(set(xml_payloads)):
                    # 和XML兼容
                    final_requirement["payload_types"] = llm_payloads

                else:
                    # 和XML冲突
                    questions.append({
                        "field": "payload_types",
                        "type": "conflict",
                        "question": (
                            f"用户指令中的载荷类型为 {llm_payloads}，"
                            f"但XML配置的载荷类型为 {xml_payloads}，"
                            "请确认最终使用的载荷类型。"
                        ),
                        "xml_value": xml_payloads,
                        "instruction_value": llm_payloads,
                    })

            else:
                # XML没有，但instruction明确说了
                final_requirement["payload_types"] = llm_payloads

        else:
            # instruction没说载荷

            if xml_payloads:
                # XML有 → 自动继承，不需要问
                final_requirement["payload_types"] = xml_payloads

            else:
                # 两边都没有
                questions.append({
                    "field": "payload_types",
                    "type": "missing",
                    "question": (
                        "当前任务未明确载荷类型，"
                        "请确认使用SAR、OPTICAL还是ELINT。"
                    ),
                })

        # =====================================
        # 5. 保存LLM可以安全补充的描述信息
        # =====================================

        if llm_data.get("objective"):
            final_requirement["objective"] = llm_data["objective"]

        if llm_data.get("deadline_seconds") is not None:
            final_requirement["deadline_seconds"] = (
                llm_data["deadline_seconds"]
            )

        return final_requirement, questions


    def prepare(
        self,
        context: ExecutionContext,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> ExecutionContext:

        context.metadata["orchestrator_agent"] = "rule_based_orchestrator_v1"
        context.metadata["llm_api_used"] = False

        context = InputAgent().run(context)

    # 原 XML 解析
        context = UnderstandingAgent().run(context)

        if overrides:
            self._merge_overrides(context, overrides)

        context = DecomposeAgent(self.registry).run(context)
        context = PlanningAgent().run(context)

        return context
    async def prepare_with_llm(
        self,
        context: ExecutionContext,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> ExecutionContext:

        context.metadata["orchestrator_agent"] = (
            "llm_enhanced_orchestrator_v1"
        )

        # 1. 输入检查
        context = InputAgent().run(context)

        # 2. XML永远先解析
        context = UnderstandingAgent().run(context)

        xml_requirement = dict(
            context.parsed_requirement
        )

        instruction = (
            context.request.instruction or ""
        ).strip()

        # =====================================
        # 没有 instruction
        # =====================================

        if not instruction:

            context.metadata["llm_api_used"] = False
            context.metadata["understanding_mode"] = "xml_only"
            context.metadata["need_clarification"] = False

            if overrides:
                self._merge_overrides(
                    context,
                    overrides,
                )

            context = DecomposeAgent(
                self.registry
            ).run(context)

            context = PlanningAgent().run(
                context
            )

            return context

        # =====================================
        # 有 instruction
        # =====================================

        llm_agent = LLMUnderstandingAgent()

        llm_requirement = await llm_agent.run(
            user_instruction=instruction,
            xml_context=xml_requirement,
            task_context={
                "task_id": context.request.task_id,
                "tiff_path": context.request.tiff_path,
            },
        )

        if hasattr(llm_requirement, "model_dump"):
            llm_data = llm_requirement.model_dump()
        else:
            llm_data = llm_requirement.dict()

        # XML为主 + instruction辅助判别
        final_requirement, questions = (
            self._resolve_xml_and_instruction(
                xml_requirement,
                llm_data,
            )
        )
        print("\n========== Requirement ==========")
        print("instruction:", instruction)
        print("XML requirement:", xml_requirement)
        print("LLM requirement:", llm_data)
        print("Final requirement:", final_requirement)
        print("Clarification questions:", questions)
        print("=======================================\n")

        context.parsed_requirement = final_requirement

        context.parsed_requirement["tiff_path"] = (
            context.request.tiff_path
        )

        context.metadata["llm_api_used"] = True
        context.metadata["understanding_mode"] = "xml_plus_llm"
        context.metadata["xml_requirement"] = xml_requirement
        context.metadata["llm_requirement"] = llm_data

        # =====================================
        # 有歧义 / 冲突
        # =====================================

        if questions:

            context.metadata["need_clarification"] = True
            context.metadata["clarification_questions"] = questions

            return context

        # =====================================
        # 信息明确，可以继续
        # =====================================

        context.metadata["need_clarification"] = False

        if overrides:
            self._merge_overrides(
                context,
                overrides,
            )

        context = DecomposeAgent(
            self.registry
        ).run(context)

        context = PlanningAgent().run(context)

        return context