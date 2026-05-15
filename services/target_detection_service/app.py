import random
from typing import Dict, Any
from fastapi import FastAPI

app = FastAPI()

def get_region(payload: Dict[str, Any]) -> Dict[str, Any]:
    """提取目标区域参数，兼容多种输入格式。"""
    input_data = payload.get("input_data", {})
    parsed = input_data.get("parsed_requirement")
    if not parsed:
        parsed = input_data.get("xml_config", {})
        
    return parsed.get(
        "target_region", 
        {"lon": 120.1, "lat": 30.2, "radius_km": 20}
    )

def call_specific_algorithm_docker(tool_name: str, target_name: str, params: dict) -> dict:
    """
    在这里调用你 Docker 内部封装好的真实 AI 模型！
    把提取出的切片/底图路径传给模型进行推理。
    """
    mode = params.get("mode", "base_map")
    
    # ---------------------------------------------------------
    # 
    # if mode == "slice":
    #     base_img = params.get("basePath")
    #     slice_img = params.get("pointPath")
    #     # 调用本地模型预测切片
    #     result = my_pytorch_model.predict_slice(base_img, slice_img, target=target_name)
    # else:
    #     full_img = params.get("tiff_path")
    #     # 调用本地模型预测全图
    #     result = my_pytorch_model.predict_full(full_img, target=target_name)
    # 
    # return result # 直接返回算法算出来的标准大字典
    # ---------------------------------------------------------

    # 下面是模拟模型根据 params 算出的结果：
    lon = float(params.get("lon", 120.1))
    lat = float(params.get("lat", 30.2))
    
    offset_lon = random.uniform(-0.005, 0.005)
    offset_lat = random.uniform(-0.005, 0.005)
    center_lon = lon + offset_lon
    center_lat = lat + offset_lat
    
    return {
        "code": 200,
        "msg": f"success (processed in {mode} mode)",
        "data": [
            {
                "targetName": target_name,
                
                # 像素坐标百分比
                "leftTopX": 0.15, "leftTopY": 0.15,
                "leftBotX": 0.15, "leftBotY": 0.85,
                "rightTopX": 0.85, "rightTopY": 0.15,
                "rightBotX": 0.85, "rightBotY": 0.85,
                "center_x": 0.5, "center_y": 0.5,
                
                # 地理经纬度信息
                "leftTopLon": center_lon - 0.001, "leftTopLat": center_lat + 0.001,
                "leftBotLon": center_lon - 0.001, "leftBotLat": center_lat - 0.001,
                "rightTopLon": center_lon + 0.001, "rightTopYLat": center_lat + 0.001,
                "rightBotXLon": center_lon + 0.001, "rightBotYLat": center_lat - 0.001,
                "center_Lon": center_lon, "center_Lat": center_lat,
                
                "algorithmSource": tool_name,
                "score": round(random.uniform(0.88, 0.98), 2)
            }
        ]
    }


def build_mcp_response(subtask_id: str, tool_name: str, algo_response: dict) -> dict:
    # 直接提取目标列表，如果没有则默认为空列表
    detections = algo_response.get("data", [])
    return {
        "subtask_id": subtask_id,
        "tool_name": tool_name,
        "success": algo_response.get("code") == 200,
        "output": {"detections": detections}, 
        "confidence": detections[0].get("score", 0.90) if detections else 0.90,
        "message": algo_response.get("msg") or f"{tool_name} 处理完成"
    }


@app.post("/infer")
def infer(payload: Dict[str, Any]):
    tool_name = payload.get("tool_name", "")
    subtask_id = payload.get("subtask_id", "")
    params = payload.get("parameters", {})

    valid_tools = {
        "sar_aircraft_service", "sar_ship_service", "sar_vehicle_service",
        "optical_aircraft_service", "optical_ship_service", "optical_vehicle_service"
    }
    target_name = tool_name.split("_")[1]
    
    algo_response = call_specific_algorithm_docker(tool_name, target_name, params)
    
    return build_mcp_response(subtask_id, tool_name, algo_response)