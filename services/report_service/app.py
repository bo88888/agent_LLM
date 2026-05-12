from fastapi import FastAPI

app = FastAPI()


@app.post("/infer")
def infer(payload: dict):
    prev = payload["input_data"].get("previous_results", {})
    fused = prev.get("F2", {}).get("fused_targets", [])
    parsed = payload["input_data"]["parsed_requirement"]
    region = parsed.get("target_region", {})

    report = {
        "task_info": {
            "task_id": payload["task_id"],
            "task_type": parsed.get("task_type", "multi_payload_detection"),
        },
        "target_region": region,
        "target_count": len(fused),
        "targets": fused,
        "regional_situation": (
            f"Detected {len(fused)} fused target(s) near "
            f"lon={region.get('lon')}, lat={region.get('lat')} "
            f"within {region.get('radius_km')} km."
        ),
        "confidence_assessment": 0.91,
        "disposal_suggestion": [
            "Keep monitoring the target region.",
            "Prioritize high-confidence fused targets for follow-up.",
        ],
    }

    return {
        "subtask_id": payload["subtask_id"],
        "tool_name": payload["tool_name"],
        "success": True,
        "output": {"final_report": report},
        "confidence": 0.91,
        "message": "Report generation finished",
    }
