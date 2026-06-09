import json
import uuid
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Any
from pathlib import Path

from core.schema import ExecutionContext, TaskRequest
from agents.orchestrator_agent import OrchestratorAgent
from agents.postprocess_agent import PostprocessAgent
from agents.replan_agent import ReplanDecisionAgent
from agents.report_agent import ReportAgent
from config import HTTP_TIMEOUT, TOOL_SERVICE_MAP
from mcp.registry import ToolRegistry
from agents.invoker_agent import InvokerAgent
from scheduler.scheduler_center import IntelligentScheduler

app = FastAPI(title="智能体多载荷调度中心 API")

def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool_name, service_url in TOOL_SERVICE_MAP.items():
        registry.register(tool_name, service_url)
    return registry

def build_orchestration_payload(context: ExecutionContext) -> Dict[str, Any]:
    return {
        "plan": context.plan_rationale,
        "trace": context.execution_trace,
        "replan_events": context.replan_events,
        "skipped": context.skipped_tools,
    }


def build_frontend_report(context: ExecutionContext) -> Dict[str, Any]:
    report = dict(context.final_report or {})
    # 调试时想看系统信息，就注释掉下面这一行。
    report.pop("_system_info", None)
    # 调试时想看智能体调度过程，就注释掉下面这一行。
    report.pop("orchestration", None)
    report.pop("execution_status", None)
    return report

# 定义前端传过来的数据结构
class PipelineRequest(BaseModel):
    task_id: str = ""
    tiff_path: str
    requirement_xml_path: str

# 接口一：原来的全域底图识别接口 
@app.post("/api/v1/task/submit")
async def submit_task(req: PipelineRequest):
    """
    前端调用此接口启动整个流水线，返回最终的 JSON 报告
    """
    task_id = req.task_id.strip() if req.task_id else f"TASK_{uuid.uuid4().hex[:6]}"

    request = TaskRequest(
        task_id=task_id,
        tiff_path=req.tiff_path,
        requirement_xml_path=req.requirement_xml_path,
        payload_types=[],
        target_classes=[],
        target_region={},
        output_requirements={
            "format": "json",
            "need_confidence": True,
            "need_suggestion": True
        },
    )

    context = ExecutionContext(request=request)

    registry = build_registry()

    # 2. 规则型 Orchestrator 持有完整上下文，完成理解、动态拆解和可解释规划。
    context = OrchestratorAgent(registry).prepare(
        context,
        overrides={
            "detection_mode": "base_map",
            "constraints": {"need_geo_correction": True}
        }
    )

    # 3. 智能调度执行：并发、重试、失败路由和结构化轨迹。
    invoker = InvokerAgent(registry, timeout=HTTP_TIMEOUT)
    scheduler = IntelligentScheduler(invoker, ReplanDecisionAgent())
    context = await scheduler.run_async(context)

    # 4. 后处理与报告
    context = PostprocessAgent().run(context)
    context = ReportAgent().run(context)
    clean_report = build_frontend_report(context)

    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)  
    report_path = output_dir / f"report_{task_id}.json"

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(clean_report, f, ensure_ascii=False, indent=2)

    print(f"✅ 报告已成功保存至容器内部路径: {report_path}")

    # 5. 直接将最终的 json 报告作为 HTTP 响应返回给前端！
    return {
        "code": 200,
        "msg": "Pipeline executed successfully",
        "data": {
            "task_id": task_id,
            "final_report": clean_report,
            # 调试时取消下面两行注释。
            # "quality_report": context.quality_report,
            # "orchestration": build_orchestration_payload(context),
        }
    }

class SliceRequest(BaseModel):
    pointPath: List[str]

# 接口二：切片目标识别接口
@app.post("/api/v1/task/slice_infer")

async def slice_infer(req: SliceRequest):

    all_extracted_targets = []  # 用于存放所有切片跑出来的目标大池子
    print(f"🚀 收到切片批量处理请求，共计 {len(req.pointPath)} 张切片")

    request = TaskRequest(
        task_id=f"SLICE_BATCH_{uuid.uuid4().hex[:6]}", 
        tiff_path="", 
        # 固定位置后续修改
        requirement_xml_path="/workspace/data/requirement.xml", 
        payload_types=[],    
        target_classes=[],   
        target_region={},
        output_requirements={                 
            "format": "json",
            "need_confidence": True,
            "need_suggestion": True
        },
    )
    context = ExecutionContext(request=request)

    registry = build_registry()

    # 2. 通过 Orchestrator 注入切片模式覆盖项，再动态生成切片 DAG。
    context = OrchestratorAgent(registry).prepare(
        context,
        overrides={
            "detection_mode": "slice",
            "slice_inputs": {"pointPathList": req.pointPath},
            "constraints": {"need_geo_correction": False},
        },
    )

    # 3. 执行智能调度
    invoker = InvokerAgent(registry, timeout=HTTP_TIMEOUT)
    scheduler = IntelligentScheduler(invoker, ReplanDecisionAgent())
    context = await scheduler.run_async(context)

    # 4. 后处理提取目标数据，并生成质量评估。
    context = PostprocessAgent().run(context)
    context = ReportAgent().run(context)
    all_extracted_targets = context.metadata.get("fused_targets", [])
    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)  
    report_path = output_dir / f"report_slice.json"

    final_response = {
        "code": 200,
        "msg": f"success, batch processed {len(req.pointPath)} slices",
        "data": all_extracted_targets,
        # 调试时取消下面两行注释。
        # "quality_report": context.quality_report,
        # "orchestration": build_orchestration_payload(context),
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(final_response, f, ensure_ascii=False, indent=2)

    return final_response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
