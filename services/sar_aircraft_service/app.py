from fastapi import FastAPI

app = FastAPI()


def get_region(payload: dict) -> dict:
    return payload["input_data"].get("xml_config", {}).get("target_region", {})

@app.post("/infer")
def infer(payload: dict):
    region = get_region(payload)
    input_data = payload.get("input_data", {})
    prev_results = input_data.get("previous_results", {})
    p3_output = prev_results.get("P3", {})
    working_image_path = p3_output.get("geo_corrected_path")
    # 【强制拦截】：如果没有拿到 P3 的校正图，直接返回失败
    if not working_image_path:
        return {
            "subtask_id": payload.get("subtask_id"),
            "tool_name": payload.get("tool_name"),
            "success": False,  # 标记任务失败
            "output": {},
            "confidence": 0.0,
            "message": "错误：缺少前置任务 P3 (几何精校正) 的输出图像，检测中止！",
        }

    detection = {
        "id": "sar_aircraft_001",
        "category": "aircraft",
        "source": "SAR_AIRCRAFT",
        "location": [region.get("lon", 120.1), region.get("lat", 30.2)],
        "search_radius_km": region.get("radius_km", 20),
        "score": 0.91,
        "mode": "sar",
    }
    return {
        "subtask_id": payload["subtask_id"],
        "tool_name": payload["tool_name"],
        "success": True,
        "output": {"detections": [detection]},
        "confidence": 0.91,
        "message": "SAR aircraft detection finished",
    }
