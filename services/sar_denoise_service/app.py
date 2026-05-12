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
            "sar_denoised_path": f"{tiff_path}/sar_denoised.tif",
            "method": "speckle_denoise",
        },
        "confidence": 0.95,
        "message": "SAR denoise finished",
    }
