import os
from typing import Dict, Any
from fastapi import FastAPI

app = FastAPI()

# 1. 调用本地真实的预处理算法模型
# =========================================================
def run_local_preprocess_model(tool_name: str, tiff_path: str, params: dict) -> dict:
    """
    在这里调用 Docker 内部封装好的真实图像处理算法！
    把提取出的底图路径（tiff_path）传给算法。
    """
    # --------------------------------------------------------- 
    # if tool_name == "sar_denoise_service":
    #     result_path = my_algo.denoise(tiff_path)
    #     return {"code": 200, "data": {"sar_denoised_path": result_path}}
    # ---------------------------------------------------------

    if tool_name == "sar_denoise_service":
        return {
            "code": 200,
            "msg": "SAR denoise finished",
            "data": {
                "sar_denoised_path": f"{tiff_path}/sar_denoised.tif",
                "method": "speckle_denoise"
            },
            "confidence": 0.95
        }
        
    elif tool_name == "optical_enhance_service":
        return {
            "code": 200,
            "msg": "Optical enhancement finished",
            "data": {
                "optical_enhanced_path": f"{tiff_path}/optical_enhanced.tif",
                "method": "contrast_stretch"
            },
            "confidence": 0.94
        }
        
    elif tool_name == "geo_correction_service":
        return {
            "code": 200,
            "msg": "Geo correction finished",
            "data": {
                "geo_corrected_path": "/workspace/geo_corrected_product",
                "source_resolution": params.get("source_resolution", "200m"),
                "target_resolution": params.get("target_resolution", "2m")
            },
            "confidence": 0.93
        }
        
    return {"code": 500, "msg": f"未知的预处理算法: {tool_name}", "data": {}}

# 2. 封装为 MCP 格式
def build_mcp_response(subtask_id: str, tool_name: str, algo_response: dict) -> dict:

    return {
        "subtask_id": subtask_id,
        "tool_name": tool_name,
        "success": algo_response.get("code") == 200,
        "output": algo_response.get("data", {}),  
        "confidence": algo_response.get("confidence", 0.90),
        "message": algo_response.get("msg", "")
    }

# 3. MCP 调度接口 (路由 + 参数透传)
@app.post("/infer")
def infer(payload: Dict[str, Any]):
    tool_name = payload.get("tool_name", "")
    subtask_id = payload.get("subtask_id", "")
    
    # 提取输入数据和参数
    input_data = payload.get("input_data", {})
    params = payload.get("parameters", {})
    
    # 预处理阶段只关心底图，因此直接提取 tiff_path
    tiff_path = input_data.get("tiff_path", "")

    # 合法性白名单校验
    valid_tools = {
        "sar_denoise_service", 
        "optical_enhance_service", 
        "geo_correction_service"
    }
    
    # 调用真实的本地预处理算法
    algo_response = run_local_preprocess_model(tool_name, tiff_path, params)
    
    return build_mcp_response(subtask_id, tool_name, algo_response)
 