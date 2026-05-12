from core.schema import ExecutionContext


class PostprocessAgent:
    """后处理汇总智能体。

    注意：
    - 真正的虚警过滤由 false_alarm_filter_service 完成，对应子任务 F1。
    - 真正的融合由 qb_fusion_service 完成，对应子任务 F2。
    - 本 agent 只是读取 F1/F2 的结果，生成一个简要统计摘要。
    """

    def run(self, context: ExecutionContext) -> ExecutionContext:
        # 从工具结果中取出虚警过滤和融合结果。
        filtered = context.tool_results.get("F1")
        fused = context.tool_results.get("F2")

        # 写入 metadata，方便最终报告或调试查看。
        context.metadata["postprocess_summary"] = {
            "has_filtered_result": filtered is not None and filtered.success,
            "has_fusion_result": fused is not None and fused.success,
            "filtered_detection_count": len(filtered.output.get("filtered_detections", [])) if filtered and filtered.success else 0,
            "fused_target_count": len(fused.output.get("fused_targets", [])) if fused and fused.success else 0,
        }
        return context
