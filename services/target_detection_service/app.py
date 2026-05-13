from typing import Dict, Any
from fastapi import FastAPI

app = FastAPI()

def get_region(payload: Dict[str, Any]) -> Dict[str, Any]:
    """提取目标区域参数，兼容多种输入格式。"""
    input_data = payload.get("input_data", {})
    
    # 兼容处理：优先取 parsed_requirement，其次取 xml_config
    parsed = input_data.get("parsed_requirement")
    if not parsed:
        parsed = input_data.get("xml_config", {})
        
    return parsed.get(
        "target_region", 
        {"lon": 120.1, "lat": 30.2, "radius_km": 20}
    )

@app.post("/infer")
def infer(payload: Dict[str, Any]):
    tool_name = payload.get("tool_name", "")
    subtask_id = payload.get("subtask_id", "")
    
    # 提取区域共有字段
    region = get_region(payload)
    lon = region.get("lon")
    lat = region.get("lat")
    radius = region.get("radius_km")

    # ==========================================
    # 1. SAR 目标检测服务
    # ==========================================
    if tool_name == "sar_aircraft_service":
        # 检查前置任务 P3 (几何校正) 结果
        p3_output = payload.get("input_data", {}).get("previous_results", {}).get("P3", {})
        if not p3_output.get("geo_corrected_path"):
            return {
                "subtask_id": subtask_id,
                "tool_name": tool_name,
                "success": False,
                "output": {},
                "confidence": 0.0,
                "message": "错误：缺少前置任务 P3 图像！"
            }
            
        detection = {
            "id": "sar_air_001",
            "category": "aircraft",
            "source": "SAR_AIRCRAFT",
            "location": [lon, lat],
            "search_radius_km": radius,
            "score": 0.91,
            "mode": "sar"
        }
        return {
            "subtask_id": subtask_id,
            "tool_name": tool_name,
            "success": True,
            "output": {"detections": [detection]},
            "confidence": 0.91,
            "message": "SAR 飞机检测完成"
        }

    elif tool_name == "sar_ship_service":
        detection = {
            "id": "sar_ship_001",
            "category": "ship",
            "source": "SAR_SHIP",
            "location": [lon, lat],
            "search_radius_km": radius,
            "score": 0.92,
            "mode": "sar"
        }
        return {
            "subtask_id": subtask_id,
            "tool_name": tool_name,
            "success": True,
            "output": {"detections": [detection]},
            "confidence": 0.92,
            "message": "SAR 舰船检测完成"
        }

    elif tool_name == "sar_vehicle_service":
        detection = {
            "id": "sar_veh_001",
            "category": "vehicle",
            "source": "SAR_VEHICLE",
            "location": [lon, lat],
            "search_radius_km": radius,
            "score": 0.89,
            "mode": "sar"
        }
        return {
            "subtask_id": subtask_id,
            "tool_name": tool_name,
            "success": True,
            "output": {"detections": [detection]},
            "confidence": 0.89,
            "message": "SAR 车辆检测完成"
        }

    # ==========================================
    # 2. 光学 目标检测服务
    # ==========================================
    elif tool_name == "optical_aircraft_service":
        detection = {
            "id": "opt_air_001",
            "category": "aircraft",
            "source": "OPTICAL_AIRCRAFT",
            "location": [lon, lat],
            "search_radius_km": radius,
            "score": 0.90,
            "mode": "optical"
        }
        return {
            "subtask_id": subtask_id,
            "tool_name": tool_name,
            "success": True,
            "output": {"detections": [detection]},
            "confidence": 0.90,
            "message": "光学飞机检测完成"
        }

    elif tool_name == "optical_ship_service":
        detection = {
            "id": "opt_ship_001",
            "category": "ship",
            "source": "OPTICAL_SHIP",
            "location": [lon, lat],
            "search_radius_km": radius,
            "score": 0.90,
            "mode": "optical"
        }
        return {
            "subtask_id": subtask_id,
            "tool_name": tool_name,
            "success": True,
            "output": {"detections": [detection]},
            "confidence": 0.90,
            "message": "光学舰船检测完成"
        }

    elif tool_name == "optical_vehicle_service":
        detection = {
            "id": "opt_veh_001",
            "category": "vehicle",
            "source": "OPTICAL_VEHICLE",
            "location": [lon, lat],
            "search_radius_km": radius,
            "score": 0.88,
            "mode": "optical"
        }
        return {
            "subtask_id": subtask_id,
            "tool_name": tool_name,
            "success": True,
            "output": {"detections": [detection]},
            "confidence": 0.88,
            "message": "光学车辆检测完成"
        }

    # ==========================================
    # 3. 异常兜底
    # ==========================================
    return {
        "success": False, 
        "message": f"Unknown tool_name: {tool_name}"
    }