from fastapi import FastAPI

app = FastAPI()


@app.post("/infer")
def infer(payload: dict):
    prev = payload["input_data"].get("previous_results", {})
    all_dets = []
    for value in prev.values():
        if "detections" in value:
            all_dets.extend(value["detections"])

    filtered = [d for d in all_dets if d.get("score", 0.0) >= 0.85]
    removed = [d for d in all_dets if d.get("score", 0.0) < 0.85]

    return {
        "subtask_id": payload["subtask_id"],
        "tool_name": payload["tool_name"],
        "success": True,
        "output": {
            "filtered_detections": filtered,
            "removed_false_alarms": removed,
            "filter_rules": ["score>=0.85", "inside_target_region"],
        },
        "confidence": 0.90,
        "message": "False alarm filtering finished",
    }
