from fastapi import FastAPI

app = FastAPI()

@app.post("/infer")
def infer(payload: dict):
    tool_name = payload.get("tool_name", "")
    subtask_id = payload.get("subtask_id", "")
    input_data = payload.get("input_data", {})
    
    if tool_name == "sar_denoise_service":
        tiff_path = input_data.get("tiff_path", "")
        return {
            "subtask_id": subtask_id,
            "tool_name": tool_name,
            "success": True,
            "output": {
                "sar_denoised_path": f"{tiff_path}/sar_denoised.tif",
                "method": "speckle_denoise",
            },
            "confidence": 0.95,
            "message": "SAR denoise finished",
        }

    elif tool_name == "optical_enhance_service":
        tiff_path = input_data.get("tiff_path", "")
        return {
            "subtask_id": subtask_id,
            "tool_name": tool_name,
            "success": True,
            "output": {
                "optical_enhanced_path": f"{tiff_path}/optical_enhanced.tif",
                "method": "contrast_stretch",
            },
            "confidence": 0.94,
            "message": "Optical enhancement finished",
        }

    elif tool_name == "geo_correction_service":
        params = payload.get("parameters", {})
        return {
            "subtask_id": subtask_id,
            "tool_name": tool_name,
            "success": True,
            "output": {
                "geo_corrected_path": "/workspace/geo_corrected_product",
                "source_resolution": params.get("source_resolution", "200m"),
                "target_resolution": params.get("target_resolution", "2m"),
            },
            "confidence": 0.93,
            "message": "Geo correction finished",
        }
    
    return {"success": False, "message": f"Unknown tool_name: {tool_name}"}