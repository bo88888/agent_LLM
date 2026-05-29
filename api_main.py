import json
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)