from fastapi import FastAPI

app = FastAPI()


@app.post("/infer")
def infer(payload: dict):
    tiff_path = payload["input_data"]["tiff_path"]
    return {
        "subtask_id": payload["subtask_id"],
        "tool_name": payload["tool_name"],
        "success": True,
        "output": {
            "optical_enhanced_path": f"{tiff_path}/optical_enhanced.tif",
            "method": "contrast_stretch",
        },
        "confidence": 0.94,
        "message": "Optical enhancement finished",
    }
