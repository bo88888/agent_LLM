from fastapi import FastAPI

app = FastAPI()

def get_region(payload: dict) -> dict:
    parsed = payload.get("input_data", {}).get("parsed_requirement", {})
    return parsed.get("target_region", {"lon": 120.1, "lat": 30.2, "radius_km": 20})

def build_detection(tool_name: str, region: dict) -> dict:
    category = tool_name.replace("_service", "")
    if category.startswith("sar_"):
        target_class = category.replace("sar_", "")
        mode = "sar"
    elif category.startswith("optical_"):
        target_class = category.replace("optical_", "")
        mode = "optical"
    elif tool_name == "elint_detection_service":
        target_class = "signal"
        mode = "elint"
    else:
        target_class = category
        mode = "unknown"

    return {
        "id": f"{tool_name}_001",
        "source": tool_name,
        "category": target_class,
        "location": [region.get("lon", 120.1), region.get("lat", 30.2)],
        "search_radius_km": region.get("radius_km", 20),
        "score": 0.90,
        "mode": mode,
    }

@app.post("/infer")
def infer(payload: dict):
    tool_name = payload.get("tool_name", "")
    parameters = payload.get("parameters", {})
    region = get_region(payload)

    # 1. 模拟预处理服务
    if tool_name == "sar_denoise_service":
        output = {
            "sar_denoised_path": "data/sample_packet/sar_denoised.tif",
            "method": "speckle_denoise",
        }
        confidence = 0.95

    elif tool_name == "optical_enhance_service":
        output = {
            "optical_enhanced_path": "data/sample_packet/optical_enhanced.tif",
            "method": "contrast_stretch",
        }
        confidence = 0.94

    elif tool_name == "geo_correction_service":
        output = {
            "geo_corrected_path": "data/sample_packet/geo_corrected.tif",
            "target_resolution": parameters.get("target_resolution", "2m"),
        }
        confidence = 0.93

    # 2. 模拟检测服务
    elif tool_name in [
        "sar_aircraft_service",
        "sar_ship_service",
        "sar_vehicle_service",
        "optical_aircraft_service",
        "optical_ship_service",
        "optical_vehicle_service",
        "elint_detection_service",
    ]:
        output = {"detections": [build_detection(tool_name, region)]}
        confidence = 0.90


    else:
        output = {"message": f"Unknown tool_name: {tool_name}"}
        confidence = 0.0

    return {
        "subtask_id": payload.get("subtask_id", ""),
        "tool_name": tool_name,
        "success": confidence > 0,
        "output": output,
        "confidence": confidence,
        "message": f"{tool_name} mock finished.",
    }