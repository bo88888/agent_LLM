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
    previous_results = payload.get("input_data", {}).get("previous_results", {})
    parameters = payload.get("parameters", {})
    region = get_region(payload)

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

    elif tool_name == "false_alarm_filter_service":
        all_detections = []
        for result in previous_results.values():
            if "detections" in result:
                all_detections.extend(result["detections"])

        filtered = [x for x in all_detections if x.get("score", 0) >= 0.85]
        output = {
            "filtered_detections": filtered,
            "removed_count": len(all_detections) - len(filtered),
            "filter_rules": ["score>=0.85", "inside_target_region"],
        }
        confidence = 0.91

    elif tool_name == "qb_fusion_service":
        filtered = previous_results.get("F1", {}).get("filtered_detections", [])
        fused_targets = []

        for i, det in enumerate(filtered, start=1):
            fused_targets.append(
                {
                    "target_id": f"QB_{i:03d}",
                    "category": det.get("category", "unknown"),
                    "location": det.get("location", [0, 0]),
                    "search_radius_km": det.get("search_radius_km"),
                    "sources": [det.get("source", "unknown")],
                    "fused_confidence": det.get("score", 0.90),
                }
            )

        output = {"fused_targets": fused_targets, "target_count": len(fused_targets)}
        confidence = 0.92

    elif tool_name == "report_service":
        parsed = payload.get("input_data", {}).get("parsed_requirement", {})
        fused = previous_results.get("F2", {}).get("fused_targets", [])
        output = {
            "final_report": {
                "task_info": {
                    "task_id": payload.get("task_id", "UNKNOWN"),
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
                "confidence_assessment": 0.92,
                "disposal_suggestion": [
                    "Keep monitoring the target region.",
                    "Prioritize high-confidence fused targets for follow-up.",
                ],
            }
        }
        confidence = 0.93

    else:
        output = {"message": f"Unknown tool_name: {tool_name}"}
        confidence = 0.0

    return {
        "subtask_id": payload.get("subtask_id", ""),
        "tool_name": tool_name,
        "success": confidence > 0,
        "output": output,
        "confidence": confidence,
        "message": f"{tool_name} finished.",
    }
