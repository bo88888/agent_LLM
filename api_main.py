import json
import uuid
import time
import os
import re
import asyncio
import requests
from osgeo import gdal, osr
from urllib.parse import urlparse, unquote, quote
from fastapi import FastAPI, HTTPException
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
from agents.llm_understanding_agent import LLMUnderstandingAgent
from clients.ollama_client import OllamaClient

app = FastAPI(title="智能体多载荷调度中心 API")

PROXY_BASE_URL = os.getenv(
    "PUBLIC_FILE_BASE_URL",
    "http://192.168.30.36:8889/home/air/code_LLM/agent_LLM/data/sample_packet",
).rstrip("/")

DATA_ROOT = Path(
    os.getenv(
        "INTERNAL_DATA_PREFIX",
        "/app/data/sample_packet",
    )
).resolve()

SLICE_PATH_FIELDS = (
    "currentSlicePath",
    "priorSlicePath",
    "slicePath",
    "opticalSlicePath",
    "sarSlicePath",
)

def download_http_file(
    url: str,
    task_id: str,
    file_type: str,
) -> str:
    """下载HTTP文件到容器。"""
    filename = Path(
        unquote(urlparse(url).path)
    ).name

    safe_task_id = re.sub(
        r"[^0-9A-Za-z_.-]+",
        "_",
        task_id,
    )

    download_dir = (
        DATA_ROOT
        / "http_inputs"
        / safe_task_id
    )

    download_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    local_path = download_dir / (
        f"{file_type}_{filename}"
    )

    print(f"[HTTP下载] {url}")

    with requests.get(
        url,
        stream=True,
        timeout=(10, 600),
    ) as response:
        response.raise_for_status()

        with local_path.open("wb") as file:
            for chunk in response.iter_content(
                chunk_size=1024 * 1024
            ):
                file.write(chunk)

    print(f"[HTTP下载完成] {local_path}")

    return str(local_path)

def local_path_to_proxy(path: str) -> str:
    """容器路径转HTTP地址。"""
    relative_path = (
        Path(path)
        .resolve()
        .relative_to(DATA_ROOT)
        .as_posix()
    )
    return (
        f"{PROXY_BASE_URL}/"
        f"{quote(relative_path, safe='/')}"
    )

def convert_slice_paths(targets: list) -> list:
    """
    将最终结果中的容器切片路径转换为HTTP地址。
    同时处理JPG、PNG和GeoTIFF路径。
    """
    path_fields = (
        "currentSlicePath",
        "currentSliceTiffPath",
        "priorSlicePath",
        "priorSliceTiffPath",
        "slicePath",
        "sliceTiffPath",
        "opticalSlicePath",
        "sarSlicePath",
    )

    for target in targets:
        for field in path_fields:
            path = target.get(field)

            if path:
                target[field] = local_path_to_proxy(
                    path
                )

    return targets

# 增加四角坐标计算函数
def get_base_map_corners(tiff_path: str) -> list:
    """获取GeoTIFF四角的WGS84经纬度。"""
    dataset = gdal.Open(tiff_path)
    if dataset is None:
        raise ValueError(f"无法读取底图文件：{tiff_path}")

    geo_transform = dataset.GetGeoTransform()
    width = dataset.RasterXSize
    height = dataset.RasterYSize

    pixel_corners = {
        "leftTop": (0, 0),
        "rightTop": (width, 0),
        "rightBot": (width, height),
        "leftBot": (0, height),
    }

    # 将像素坐标转换为影像原始坐标
    geo_corners = {
        name: gdal.ApplyGeoTransform(
            geo_transform,
            pixel_x,
            pixel_y,
        )
        for name, (pixel_x, pixel_y) in pixel_corners.items()
    }
 
    projection = dataset.GetProjection()

    if projection:
        source_srs = osr.SpatialReference()
        source_srs.ImportFromWkt(projection)
        source_srs.SetAxisMappingStrategy(
            osr.OAMS_TRADITIONAL_GIS_ORDER
        )

        # 已经是经纬度坐标系时，GeoTransform结果就是经纬度，
        # 不再创建WGS84转换器。
        if not source_srs.IsGeographic():
            target_srs = source_srs.CloneGeogCS()
            target_srs.SetAxisMappingStrategy(
                osr.OAMS_TRADITIONAL_GIS_ORDER
            )

            converter = osr.CreateCoordinateTransformation(
                source_srs,
                target_srs,
            )

            if converter is None:
                raise RuntimeError(
                    "无法创建投影坐标到经纬度坐标的转换器"
                )

            converted_corners = {}

            for name, (x, y) in geo_corners.items():
                point = converter.TransformPoint([
                    float(x),
                    float(y),
                    0.0,
                ])

                converted_corners[name] = (
                    point[0],
                    point[1],
                )

            geo_corners = converted_corners

    dataset = None
    result = {}

    for name, (lon, lat) in geo_corners.items():
        result[f"{name}Lon"] = round(float(lon), 8)
        result[f"{name}Lat"] = round(float(lat), 8)

    return [result]


TARGET_NAME_ZH_MAP = {
    # 舰船
    "aircraft_carrier": "航空母舰",
    "destroyer": "驱逐舰",
    "cruiser": "巡洋舰",
    "amphibious": "登陆舰",
    "depot_ship": "补给舰",
    "HJship": "海警船",
    "BHship": "濒海战斗舰",
    "minchuan": "民船",
    "other_junchuan": "其他",
    "huweijian": "护卫舰",

    # 飞机
    "hongzhaji": "轰炸机",
    "yunshuji": "运输机",
    "Helicopter": "直升机",
    "UAV": "无人机",
    "airline": "民航客机",
    "fighter": "战斗机",
    "jiayouji": "加油机",
    "other": "其他",
    "yujingji": "预警机",
}

def localize_target_names(targets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    localized_targets = []
    for target in targets:
        item = dict(target)
        target_name = item.get("targetName")
        if target_name is not None:
            item["targetName"] = TARGET_NAME_ZH_MAP.get(
                target_name,
                target_name,
            )
        localized_targets.append(item)
    return localized_targets

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
    instruction: str = ""
    tiff_path: str
    requirement_xml_path: str

# 接口一：原来的全域底图识别接口 
@app.post("/api/v1/task/submit")
async def submit_task(req: PipelineRequest):
    start_time = time.time()
    task_id = req.task_id.strip() if req.task_id else f"TASK_{uuid.uuid4().hex[:6]}"

     # 1. 下载HTTP输入文件，获得容器内部路径
    try:
        local_tiff_path, local_xml_path = await asyncio.gather(
            asyncio.to_thread(
                download_http_file,
                req.tiff_path,
                task_id,
                "tiff",
            ),
            asyncio.to_thread(
                download_http_file,
                req.requirement_xml_path,
                task_id,
                "requirement",
            ),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"HTTP输入文件下载失败：{exc}",
        ) from exc
    # 新增：计算底图四角坐标
    try:
        base_map_corners = await asyncio.to_thread(
            get_base_map_corners,
            local_tiff_path,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"底图四角坐标读取失败：{exc}",
        ) from exc



    # 2. 使用下载后的容器路径创建任务
    request = TaskRequest(
        task_id=task_id,
        instruction=req.instruction,

        tiff_path=local_tiff_path,
        requirement_xml_path=local_xml_path,
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

    # 3. 规则型 Orchestrator 持有完整上下文，完成理解、动态拆解和可解释规划。
    context = await OrchestratorAgent(registry).prepare_with_llm(
        context,
        overrides={
            "detection_mode": "base_map",
            # "constraints": {"need_geo_correction": True}
        }
    )
    if context.metadata.get("need_clarification"):
        return {
            "code": 202,
            "msg": "need_clarification",
            "task_id": task_id,
            "questions": context.metadata.get(
                "clarification_questions",
                [],
            )
        }
    # 4. 智能调度执行：并发、重试、失败路由和结构化轨迹。
    invoker = InvokerAgent(registry, timeout=HTTP_TIMEOUT)
    scheduler = IntelligentScheduler(invoker, ReplanDecisionAgent())
    context = await scheduler.run_async(context)

    # 5. 后处理与报告

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
        "data": localize_target_names(raw_report["data"]),
        "baseMapCorners": base_map_corners, 
        # "orchestration": raw_report["orchestration"],
        # "execution_status":raw_report["execution_status"]
    }

    # 6. 把结果中的容器切片路径转换成HTTP地址
    clean_report["data"] = convert_slice_paths(
        clean_report["data"]
    )

    # 7. 保存最终报告
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

     # 1. 下载XML、底图和所有切片
    try:
        local_xml_path = await asyncio.to_thread(
            download_http_file,
            req.requirement_xml_path,
            task_id,
            "requirement",
        )

        local_base_map_path = ""

        if req.baseMapPath:
            local_base_map_path = await asyncio.to_thread(
                download_http_file,
                req.baseMapPath,
                task_id,
                "base_map",
            )

        local_slice_paths = await asyncio.gather(
            *[
                asyncio.to_thread(
                    download_http_file,
                    item.path,
                    task_id,
                    f"slice_{index}",
                )
                for index, item in enumerate(
                    req.pointPath,
                    start=1,
                )
            ]
        )

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"HTTP输入文件下载失败：{exc}",
        ) from exc
    # 2. 重新组织成本地切片路径
    slice_paths = [
        {
            "id": item.id,
            "path": local_path,
        }
        for item, local_path in zip(
            req.pointPath,
            local_slice_paths,
        )
    ]

    registry = build_registry()

    invoker = InvokerAgent(
        registry,
        timeout=HTTP_TIMEOUT,
    )

    scheduler = IntelligentScheduler(
        invoker,
        ReplanDecisionAgent(),
    )

    all_current_targets = []

    # =========================
    # 3. 大区域底图识别流程
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
        all_current_targets.extend(base_targets)

    # 4. 切片识别流程
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

    if not slice_targets:
        response_code = 500
        response_msg = f"failed, no valid slice targets returned from {len(req.pointPath)} slices"
    else:
        response_code = 200
        response_msg = f"success, processed {len(req.pointPath)} slices"

    final_response = {
        "code": response_code,
        "msg": response_msg,
        "task_id": task_id,
        "detection_time": finish_time,
        "time_cost_seconds": time_cost,
        "data": localize_target_names(final_targets),
    }
    final_response["data"] = convert_slice_paths(
        final_response["data"]
    )

    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / f"report_slice_{task_id}.json"

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(final_response, f, ensure_ascii=False, indent=2)

    print(f"✅ 联合识别报告已保存至: {report_path}")

    return final_response


class LLMUnderstandRequest(BaseModel):
    instruction: str
    task_context: Dict[str, Any] = {}

@app.get("/api/v1/llm/health")
async def llm_health():

    client = OllamaClient()

    try:
        result = await client.health_check()

        models = [
            model.get("name")
            for model in result.get("models", [])
        ]

        return {
            "code": 200,
            "msg": "Ollama connected",
            "models": models,
        }

    except Exception as exc:
        return {
            "code": 500,
            "msg": str(exc),
        }
@app.post("/api/v1/llm/understand")
async def llm_understand(req: LLMUnderstandRequest):

    agent = LLMUnderstandingAgent()

    try:
        requirement = await agent.run(
            user_instruction=req.instruction,
            task_context=req.task_context,
        )

        # Pydantic v2
        if hasattr(requirement, "model_dump"):
            data = requirement.model_dump()

        # Pydantic v1
        else:
            data = requirement.dict()

        return {
            "code": 200,
            "msg": "success",
            "data": data,
        }

    except Exception as exc:
        return {
            "code": 500,
            "msg": str(exc),
            "data": None,
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
