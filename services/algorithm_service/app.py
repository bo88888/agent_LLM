import random
from typing import Dict, Any
from fastapi import FastAPI

app = FastAPI()

def get_region(payload: Dict[str, Any]) -> Dict[str, Any]:
    input_data = payload.get("input_data", {})
    parsed = input_data.get("parsed_requirement") or input_data.get("xml_config", {})
    return parsed.get("target_region", {"lon": 120.1, "lat": 30.2, "radius_km": 20})

# ==========================================
# 1. 视觉目标检测逻辑 (SAR 与 光学)
# ==========================================
def call_specific_algorithm_docker(tool_name: str, target_name: str, params: dict) -> dict:
    mode = params.get("mode", "base_map")
    lon = float(params.get("lon", 120.1))
    lat = float(params.get("lat", 30.2))
    score = round(random.uniform(0.88, 0.98), 2)
    
    target_data = {
        "targetName": target_name,
        "leftTopX": 0.15, "leftTopY": 0.15,
        "rightBotX": 0.85, "rightBotY": 0.85,
        "center_Lon": lon + random.uniform(-0.005, 0.005), 
        "center_Lat": lat + random.uniform(-0.005, 0.005),
        "algorithmSource": tool_name,
        "score": score
    }
    
    return {
        "code": 200,
        "msg": f"success (processed in {mode} mode)",
        "data": {"detections": [target_data]},
        "confidence": score  
    }

# ==========================================
# 2. 预处理逻辑 
# ==========================================
def run_local_preprocess_model(tool_name: str, tiff_path: str, params: dict) -> dict:
    tool_configs = {
        "sar_denoise_service": {
            "msg": "SAR denoise finished",
            "data": {"sar_denoised_path": f"{tiff_path}/sar_denoised.tif"},
            "confidence": 0.95
        },
        "optical_enhance_service": {
            "msg": "Optical enhancement finished",
            "data": {"optical_enhanced_path": f"{tiff_path}/optical_enhanced.tif"},
            "confidence": 0.94
        },
        "geo_correction_service": {
            "msg": "Geo correction finished",
            "data": {
                "geo_corrected_path": "/workspace/geo_corrected",
                "target_resolution": params.get("target_resolution", "2m")
            },
            "confidence": 0.93
        }
    }

    config = tool_configs[tool_name]
    return {
        "code": 200,
        "msg": config["msg"],
        "data": config["data"],
        "confidence": config["confidence"]
    }

# ==========================================
# 3. 电子侦察逻辑 (ELINT)
# ==========================================
def run_elint_detection(region: dict) -> dict:
    target_data = {
        "id": "elint_001", 
        "targetName": "signal", 
        "algorithmSource": "ELINT",
        "center_Lon": region.get("lon", 120.1), 
        "center_Lat": region.get("lat", 30.2), 
        "score": 0.84
    }
    
    return {
        "code": 200, 
        "msg": "ELINT detection finished", 
        "data": {"detections": [target_data]},s
        "confidence": 0.84
    }

# ==========================================
# 4. 极简的 MCP 格式封装 
# ==========================================
def build_mcp_response(subtask_id: str, tool_name: str, algo_response: dict) -> dict:

    return {
        "subtask_id": subtask_id,
        "tool_name": tool_name,
        "success": algo_response.get("code") == 200,
        "output": algo_response.get("data", {}),         
        "confidence": algo_response.get("confidence", 0.0), 
        "message": algo_response.get("msg") or f"{tool_name} 处理完成"
    }

# ==========================================
# 5. 统一路由入口
# ==========================================
@app.post("/infer")
def infer(payload: Dict[str, Any]):
    tool_name = payload.get("tool_name", "")
    subtask_id = payload.get("subtask_id", "")
    params = payload.get("parameters", {})
    
    # --- 1. 预处理模块 ---
    if tool_name in {"sar_denoise_service", "optical_enhance_service", "geo_correction_service"}:
        tiff_path = payload.get("input_data", {}).get("tiff_path", "")
        algo_response = run_local_preprocess_model(tool_name, tiff_path, params)
        
    # --- 2. 视觉目标检测模块 ---
    elif tool_name in {
        "sar_aircraft_service", "sar_ship_service", "sar_vehicle_service",
        "optical_aircraft_service", "optical_ship_service", "optical_vehicle_service"
    }:
        target_name = tool_name.split("_")[1]
        algo_response = call_specific_algorithm_docker(tool_name, target_name, params)
        
    # --- 3. 电子侦察模块 ---
    elif tool_name == "elint_detection_service":
        region = get_region(payload)
        algo_response = run_elint_detection(region)
        
    # --- 4. 容错拦截 ---
    else:
        algo_response = {
            "code": 404, 
            "msg": "Tool not found in inference service", 
            "data": {}, 
            "confidence": 0.0
        }
    
    # 最后统一包装返回给调度器
    return build_mcp_response(subtask_id, tool_name, algo_response)