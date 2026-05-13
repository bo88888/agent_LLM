from core.schema import ExecutionContext
from services.postprocess_service.processor import run_false_alarm_filter, run_qb_fusion

class PostprocessAgent:

    def run(self, context: ExecutionContext) -> ExecutionContext:
        region = context.parsed_requirement.get("target_region", {})
        # 1. 虚警剔除
        filtered_dets = run_false_alarm_filter(context.tool_results, region)
        # 2. 融合
        fused_targets = run_qb_fusion(filtered_dets)

        context.metadata["fused_targets"] = fused_targets
        context.metadata["postprocess_summary"] = {
            "filtered_detection_count": len(filtered_dets),
            "fused_target_count": len(fused_targets),
        }
        return context
