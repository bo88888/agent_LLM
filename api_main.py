import json
import uuid
import time
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Any
from pathlib import Path
from datetime import datetime
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
    # 调试时想看智能体调度过程，就注释掉下面这一行。
    # report.pop("orchestration", None)
    # report.pop("execution_status", None)
    return report

# 定义前端传过来的数据结构
class PipelineRequest(BaseModel):
    task_id: str = ""
    tiff_path: str
    requirement_xml_path: str

# 接口一：原来的全域底图识别接口 
@app.post("/api/v1/task/submit")
async def submit_task(req: PipelineRequest):
    start_time = time.time()
    task_id = req.task_id.strip() if req.task_id else f"TASK_{uuid.uuid4().hex[:6]}"

    request = TaskRequest(
        task_id=task_id,
        tiff_path=req.tiff_path,
        requirement_xml_path=req.requirement_xml_path,
        payload_types=[],
        target_classes=[],
        # target_region={},
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

    end_time = time.time()
    time_cost = round(end_time - start_time, 2)
    finish_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    raw_report = build_frontend_report(context)
    clean_report = {
        "code": raw_report["code"],
        "msg": raw_report["msg"],          
        "task_id": task_id,
        "detection_time": finish_time,     
        "time_cost_seconds": time_cost,    
        "data": raw_report["data"],
        # "orchestration": raw_report["orchestration"],
        # "execution_status":raw_report["execution_status"]
                 
    }

    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)  
    report_path = output_dir / f"report_{task_id}.json"

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(clean_report, f, ensure_ascii=False, indent=2)

    print(f"✅ 报告已成功保存至容器内部路径: {report_path}")
    return clean_report


class SlicePathItem(BaseModel):
    id: str
    path: str

class SliceRequest(BaseModel):
    payloadType: str
    targetClass: str
    pointPath: List[SlicePathItem]
    baseMapPath: str = ""
    requirement_xml_path: str = "/workspace/data/requirement.xml"

# 接口二：切片 + 大区域底图联合识别接口
@app.post("/api/v1/task/slice_infer")
async def slice_infer(req: SliceRequest):
    start_time = time.time()

    payload_type = req.payloadType.strip().upper()
    target_class = req.targetClass.strip().lower()
    task_id = f"SLICE_FUSION_{uuid.uuid4().hex[:6]}"
     # 提取切片路径和切片 ID 映射
    slice_items = req.pointPath
    slice_paths = [item.path for item in slice_items]
    slice_id_map = {
        item.path: item.id
        for item in slice_items
    }
    registry = build_registry()
    invoker = InvokerAgent(registry, timeout=HTTP_TIMEOUT)
    scheduler = IntelligentScheduler(invoker, ReplanDecisionAgent())

    all_current_targets = []

    # =========================
    # 1. 大区域底图识别流程
    # =========================
    if req.baseMapPath:
        base_request = TaskRequest(
            task_id=f"{task_id}_BASE",
            tiff_path=req.baseMapPath,
            requirement_xml_path=req.requirement_xml_path,
            payload_types=[payload_type],
            target_classes=[target_class],
            output_requirements={
                "format": "json",
                "need_confidence": True,
                "need_suggestion": True
            },
        )

        base_context = ExecutionContext(request=base_request)

        base_context = OrchestratorAgent(registry).prepare(
            base_context,
            overrides={
                "detection_mode": "base_map",
                "payload_types": [payload_type],
                "target_classes": [target_class],
                "constraints": {"need_geo_correction": True}
            }
        )

        base_context = await scheduler.run_async(base_context)
        base_context = PostprocessAgent().run(base_context)

        base_targets = base_context.metadata.get("fused_targets", [])

        for t in base_targets:
            t["resultSource"] = "base_map"

        all_current_targets.extend(base_targets)

    # =========================
    # 2. 切片识别流程
    # =========================
    slice_request = TaskRequest(
        task_id=f"{task_id}_SLICE",
        tiff_path="",
        requirement_xml_path=req.requirement_xml_path,
        payload_types=[payload_type],
        

        target_classes=[target_class],
        output_requirements={
            "format": "json",
            "need_confidence": True,
            "need_suggestion": True
        },
    )

    slice_context = ExecutionContext(request=slice_request)

    slice_context = OrchestratorAgent(registry).prepare(
        slice_context,
        overrides={
            "detection_mode": "slice",
            "slice_inputs": {
                "pointPath": slice_paths,
                "payloadType": payload_type,
                "targetClass": target_class
            },
            "constraints": {"need_geo_correction": False},
        }
    )

    slice_context = await scheduler.run_async(slice_context)
    slice_context = PostprocessAgent().run(slice_context)

    slice_targets = slice_context.metadata.get("fused_targets", [])
    
    for t in slice_targets:
        slice_path = t.get("slicePath", "")
        t["id"] = slice_id_map.get(slice_path, "")
        t["resultSource"] = "slice"
        


    all_current_targets.extend(slice_targets)

    # =========================
    # 3. 待增加融合部分
    # =========================
    final_targets = all_current_targets

    # 后续可以改成：
    # final_targets = run_qb_fusion(all_current_targets)
    # final_targets = run_history_pool_fusion(
    #     current_targets=final_targets,
    #     task_id=task_id,
    #     region={}
    # )

    end_time = time.time()
    time_cost = round(end_time - start_time, 2)
    finish_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    final_response = {
        "code": 200,
        "msg": f"success, processed base map and {len(req.pointPath)} slices",
        "task_id": task_id,
        "detection_time": finish_time,
        "time_cost_seconds": time_cost,
        "data": final_targets
    }

    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / f"report_slice_{task_id}.json"

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(final_response, f, ensure_ascii=False, indent=2)

    print(f"✅ 联合识别报告已保存至: {report_path}")

    return final_response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
