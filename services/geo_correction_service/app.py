from fastapi import FastAPI

app = FastAPI()


@app.post("/infer")
def infer(payload: dict):
    params = payload.get("parameters", {})
    return {
        "subtask_id": payload["subtask_id"],
        "tool_name": payload["tool_name"],
        "success": True,
        "output": {
            "geo_corrected_path": "/workspace/geo_corrected_product",
            "source_resolution": params.get("source_resolution", "200m"),
            "target_resolution": params.get("target_resolution", "2m"),
        },
        "confidence": 0.93,
        "message": "Geo correction finished",
    }
