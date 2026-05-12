from fastapi import FastAPI

app = FastAPI()


def get_region(payload: dict) -> dict:
    return payload["input_data"]["parsed_requirement"].get("target_region", {})


@app.post("/infer")
def infer(payload: dict):
    region = get_region(payload)
    detection = {
        "id": "elint_001",
        "category": "signal",
        "source": "ELINT",
        "location": [region.get("lon", 120.1), region.get("lat", 30.2)],
        "search_radius_km": region.get("radius_km", 20),
        "score": 0.84,
        "mode": "elint",
    }
    return {
        "subtask_id": payload["subtask_id"],
        "tool_name": payload["tool_name"],
        "success": True,
        "output": {"detections": [detection]},
        "confidence": 0.84,
        "message": "ELINT detection finished",
    }
