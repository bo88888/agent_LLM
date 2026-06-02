from typing import Any, Dict, Optional

from agents.decompose_agent import DecomposeAgent
from agents.input_agent import InputAgent
from agents.planning_agent import PlanningAgent
from agents.understanding_agent import UnderstandingAgent
from core.schema import ExecutionContext


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
        context = UnderstandingAgent().run(context)
        if overrides:
            self._merge_overrides(context, overrides)
        context = DecomposeAgent(self.registry).run(context)
        context = PlanningAgent().run(context)
        return context

