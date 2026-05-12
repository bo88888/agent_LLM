from fastapi import FastAPI

app = FastAPI()


@app.post("/infer")
def infer(payload: dict):
    prev = payload["input_data"].get("previous_results", {})
    filtered = prev.get("F1", {}).get("filtered_detections", [])

    fused = []
    for idx, det in enumerate(filtered, start=1):
        fused.append(
            {
                "target_id": f"QB_{idx:03d}",
                "category": det.get("category", "unknown"),
                "location": det.get("location", [0, 0]),
                "search_radius_km": det.get("search_radius_km"),
                "sources": [det.get("source", "unknown")],
                "fused_confidence": round(min(det.get("score", 0.0) + 0.03, 0.99), 2),
                "bias_correction": {
                    "sar_offset_m": 12.0,
                    "optical_offset_m": 8.0,
                    "elint_offset_m": 30.0,
                },
            }
        )

    return {
        "subtask_id": payload["subtask_id"],
        "tool_name": payload["tool_name"],
        "success": True,
        "output": {"fused_targets": fused},
        "confidence": 0.92,
        "message": "QB fusion finished",
    }
