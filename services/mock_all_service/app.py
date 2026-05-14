from fastapi import FastAPI
import random

app = FastAPI()

def build_detection(tool_name: str, params: dict) -> dict:
    category = tool_name.replace("_service", "")
    if category.startswith("sar_") or category.startswith("optical_"):
        target_name = category.split("_")[1]
    elif tool_name == "elint_detection_service":
        target_name = "signal"
    else:
        target_name = "unknown"

    center_lon = params.get("lon", 120.11)
    center_lat = params.get("lat", 30.21)

    return {
        "targetName": target_name,
        "center_Lon": center_lon + random.uniform(-0.001, 0.001), # 加一点随机偏移模拟真实坐标
        "center_Lat": center_lat + random.uniform(-0.001, 0.001),
        "score": 0.94,
        "leftTopX": 0.15,
        "leftTopY": 0.15,
        "rightBotX": 0.85,
        "rightBotY": 0.85,
        "fusionSource": tool_name,
        "fusionInfo": "模拟算法初步检测结果",
        "auxInterpretationInfo": "无"
    }

@app.post("/infer")
def infer(payload: dict):
    tool_name = payload.get("tool_name", "")
    params = payload.get("parameters", {})  # 接收调度器传过来的精准切片参数
    mode = params.get("mode", "base_map")

    print(f"\n[Mock Server] 正在处理任务: {tool_name} | 模式: {mode}")

    # 模拟预处理服务（直接返回 OK）
    if "denoise" in tool_name or "enhance" in tool_name or "geo" in tool_name:
        return {
            "subtask_id": payload.get("subtask_id", ""),
            "tool_name": tool_name,
            "success": True,
            "output": {"status": "ok"},
            "confidence": 0.95
        }

    return {
        "subtask_id": payload.get("subtask_id", ""),
        "tool_name": tool_name,
        "success": True,
        "output": {"detections": [build_detection(tool_name, params)]},
        "confidence": 0.92
    }