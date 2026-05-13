from fastapi import FastAPI

app = FastAPI()

def get_region(payload: dict) -> dict:
    parsed = payload.get("input_data", {}).get("parsed_requirement", {})
    return parsed.get("target_region", {"lon": 120.1, "lat": 30.2, "radius_km": 20})

@app.post("/infer")
def infer(payload: dict):
    tool_name = payload.get("tool_name", "")
    subtask_id = payload.get("subtask_id", "")
    
    if tool_name == "elint_detection_service":
        region = get_region(payload)
        detection = {
            "id": "elint_001",
            "category": "signal",
            "source": "ELINT",
            "location": [region.get("lon"), region.get("lat")],
            "search_radius_km": region.get("radius_km"),
            "score": 0.84,
            "mode": "elint",
        }
        return {
            "subtask_id": subtask_id,
            "tool_name": tool_name,
            "success": True,
            "output": {"detections": [detection]},
            "confidence": 0.84,
            "message": "ELINT detection finished"
        }
    
    return {"success": False, "message": "Unknown tool in ELINT Docker"}