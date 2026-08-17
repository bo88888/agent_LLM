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
        context.metadata["orchestrator_agent"] = "llm_enhanced_orchestrator_v1"

        context = InputAgent().run(context)
        context = UnderstandingAgent().run(context)
        xml_requirement = dict(context.parsed_requirement)
        instruction = (context.request.instruction or "").strip()

        if instruction:
        # 有 instruction：调用LLM
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
            
            context.parsed_requirement.update(llm_data)
            context.parsed_requirement["tiff_path"] = (
            context.request.tiff_path
            )
        else:
        # 没有 instruction：
        # 完全使用原 UnderstandingAgent 的 XML 结果
            context.metadata["llm_api_used"] = False
            context.metadata["understanding_mode"] = "xml_only"


        if overrides:
            self._merge_overrides(context, overrides)
        context = DecomposeAgent(self.registry).run(context)
        context = PlanningAgent().run(context)
        return context

