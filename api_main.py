import json
import uuid
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any
from pathlib import Path

from core.schema import ExecutionContext, TaskRequest
from agents.input_agent import InputAgent
from agents.understanding_agent import UnderstandingAgent
from agents.decompose_agent import DecomposeAgent
from agents.planning_agent import PlanningAgent
from agents.postprocess_agent import PostprocessAgent
from agents.report_agent import ReportAgent
from config import HTTP_TIMEOUT, TOOL_SERVICE_MAP
from mcp.registry import ToolRegistry
from agents.invoker_agent import InvokerAgent
from scheduler.scheduler_center import SchedulerCenter

app = FastAPI(title="智能体多载荷调度中心 API")

def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool_name, service_url in TOOL_SERVICE_MAP.items():
        registry.register(tool_name, service_url)
    return registry

# 定义前端传过来的数据结构
class PipelineRequest(BaseModel):
    task_id: str
    tiff_path: str
    requirement_xml_path: str

    output_requirements: Dict[str, Any] = {"format": "json", "need_confidence": True}

# 接口一：原来的全域底图识别接口 
@app.post("/api/v1/task/submit")
async def submit_task(req: PipelineRequest):
    """
    前端调用此接口启动整个流水线，返回最终的 JSON 报告
    """
    request = TaskRequest(
        task_id=req.task_id,
        tiff_path=req.tiff_path,
        requirement_xml_path=req.requirement_xml_path,
        payload_types=[],
        target_classes=[],
        target_region={},
        output_requirements=req.output_requirements,
    )

    context = ExecutionContext(request=request)

    # 2. 依次执行你的 Agent 流水线
    context = InputAgent().run(context)
    context = UnderstandingAgent().run(context)
    context = DecomposeAgent().run(context)
    context = PlanningAgent().run(context)

    # 3. 调度执行
    registry = build_registry()
    invoker = InvokerAgent(registry, timeout=HTTP_TIMEOUT)
    scheduler = SchedulerCenter(invoker)
    context = await scheduler.run_async(context)

    # 4. 后处理与报告
    context = PostprocessAgent().run(context)
    context = ReportAgent().run(context)

    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)  
    report_path = output_dir / f"report_{req.task_id}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(context.final_report, f, ensure_ascii=False, indent=2)

    print(f"✅ 报告已成功保存至容器内部路径: {report_path}")

    # 5. 直接将最终的 json 报告作为 HTTP 响应返回给前端！
    return {
        "code": 200,
        "msg": "Pipeline executed successfully",
        "data": {
            "final_report": context.final_report,
            "quality_report": context.quality_report
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
        requirement_xml_path="/workspace/data/requirement.xml", 
        payload_types=["OPTICAL"],
        target_classes=["plane", "ship", "vehicle"],
        target_region={}, 
        output_requirements={"format": "json"},
    )
    context = ExecutionContext(request=request)
    # 2. 前置智能体读取 XML
    context = InputAgent().run(context)
    context = UnderstandingAgent().run(context)

    if context.parsed_requirement:
        context.parsed_requirement["detection_mode"] = "slice"
        # 把前端传来的整个数组，挂载到 slice_inputs 下面
        context.parsed_requirement["slice_inputs"] = {"pointPathList": req.pointPath}
        if "constraints" not in context.parsed_requirement:
            context.parsed_requirement["constraints"] = {}
        context.parsed_requirement["constraints"]["need_geo_correction"] = False

    # 3. 拆解与规划 (DecomposeAgent 会把 pointPathList 提取出来写进 SubTask 的 parameters 里)
    context = DecomposeAgent().run(context)
    context = PlanningAgent().run(context)

    # 4. 执行调度 
    registry = build_registry()
    invoker = InvokerAgent(registry, timeout=HTTP_TIMEOUT)
    scheduler = SchedulerCenter(invoker)
    context = await scheduler.run_async(context)

    # 5. 后处理提取目标数据
    context = PostprocessAgent().run(context)
    all_extracted_targets = context.metadata.get("fused_targets", [])
    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)  
    report_path = output_dir / f"report_slice.json"

    final_response = {
        "code": 200,
        "msg": f"success, batch processed {len(req.pointPath)} slices",
        "data": all_extracted_targets
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(final_response, f, ensure_ascii=False, indent=2)

    return final_response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)