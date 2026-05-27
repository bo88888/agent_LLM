import os
import random
import traceback
import subprocess
from typing import Dict, Any
from fastapi import FastAPI
from SAR_pro import process_sar_image
from opt_pro import process_optical_rs_image

app = FastAPI()

def get_region(payload: Dict[str, Any]) -> Dict[str, Any]:
    input_data = payload.get("input_data", {})
    parsed = input_data.get("parsed_requirement") or input_data.get("xml_config", {})
    return parsed.get("target_region", {"lon": 120.1, "lat": 30.2, "radius_km": 20})

# ==========================================
# 1. 视觉目标检测逻辑 (SAR 与 光学)
# ==========================================
def call_specific_algorithm_docker(tool_name: str, target_name: str, params: dict) -> dict:
    mode = params.get("mode", "base_map")
    lon = float(params.get("lon", 120.1))
    lat = float(params.get("lat", 30.2))
    score = round(random.uniform(0.88, 0.98), 2)
    
    # 模拟真实的目标框大小(经纬度跨度)和中心点偏移
    hw_lon = 0.005
    hh_lat = 0.005
    center_lon = lon + random.uniform(-0.01, 0.01)
    center_lat = lat + random.uniform(-0.01, 0.01)
    
    target_data = {
        "targetName": target_name,
        
        # --- 像素百分比坐标 ---
        "leftTopX": 0.15, "leftTopY": 0.15,
        "leftBotX": 0.15, "leftBotY": 0.85,
        "rightTopX": 0.85, "rightTopY": 0.15,
        "rightBotX": 0.85, "rightBotY": 0.85,
        "center_x": 0.50, "center_y": 0.50,
        
        # --- 真实地理坐标 (严格照应文档24字段) ---
        "leftTopLon": round(center_lon - hw_lon, 6),
        "leftTopLat": round(center_lat + hh_lat, 6),
        "leftBotLon": round(center_lon - hw_lon, 6),
        "leftBotLat": round(center_lat - hh_lat, 6),
        "rightTopLon": round(center_lon + hw_lon, 6),
        "rightTopYLat": round(center_lat + hh_lat, 6),
        "rightBotXLon": round(center_lon + hw_lon, 6),
        "rightBotYLat": round(center_lat - hh_lat, 6),
        "center_Lon": round(center_lon, 6),
        "center_Lat": round(center_lat, 6),
        
        # --- 业务属性 ---
        "score": score,
        "fusionSource": tool_name,  
        "auxInterpretationInfo": "光学目标检测算法原始检出"
    }
    
    return {
        "code": 200,
        "msg": f"success (processed in {mode} mode)",
        "data": {"detections": [target_data]},
        "confidence": score  
    }

# ==========================================
# 2. 预处理逻辑 
# ==========================================
def run_local_preprocess_model(tool_name: str, tiff_path: str, params: dict, input_data: dict) -> dict:
    if tool_name in {"sar_denoise_service", "optical_enhance_service"}:
        if not tiff_path or not os.path.exists(tiff_path):
            return {"code": 404, "msg": "文件不存在", "data": {}, "confidence": 0.0}
        
    base_dir = os.path.dirname(tiff_path) if tiff_path else ""
    base_name = os.path.basename(tiff_path) if tiff_path else ""
    name_only, ext = os.path.splitext(base_name) if base_name else ("", "")

    try:
        if tool_name == "sar_denoise_service":
            # 动态生成输出路径
            output_sar = os.path.join(base_dir, f"{name_only}_sar_denoised{ext}")
            
            # 获取算法参数
            kernel_size = params.get("kernel_size", 3)
            clip_quant = params.get("clip_quant", 2)
            n_std = params.get("n_std", 2)
            
            print(f"[预处理] 执行 SAR 去噪 | 输入: {tiff_path} | 输出: {output_sar}")
            
            # 调用真实算法
            process_sar_image(tiff_path, output_sar, kernel_size, clip_quant, n_std)
            
            return {
                "code": 200,
                "msg": "SAR denoise finished (Real)",
                "data": {"sar_denoised_path": output_sar},
                "confidence": 0.95
            }
            
        elif tool_name == "optical_enhance_service":
            # 动态生成输出路径
            output_opt = os.path.join(base_dir, f"{name_only}_optical_enhanced{ext}")
            
            # 获取算法参数
            median_ksize = params.get("median_ksize", 3)
            clip_percent = params.get("clip_percent", 2)
            
            print(f"[预处理] 执行 光学增强 | 输入: {tiff_path} | 输出: {output_opt}")
            
            # 调用真实算法
            process_optical_rs_image(tiff_path, output_opt, median_ksize, clip_percent)
            
            return {
                "code": 200,
                "msg": "Optical enhancement finished (Real)",
                "data": {"optical_enhanced_path": output_opt},
                "confidence": 0.94
            }
        elif tool_name == "geo_correction_service":
            print(f"[调试] P3 已进入 geo_correction_service，input_data: {input_data.keys()}")
            
            base_map_path = "/app/data/sample_packet/Suaogang_optical_enhanced_reference_1band.tif"
            previous_results = input_data.get("previous_results", {})
            images_to_correct = []
            for res_content in previous_results.values():
                path = res_content.get("optical_enhanced_path") or res_content.get("sar_denoised_path")
                if path: images_to_correct.append(path)
            
            if not images_to_correct:
                return {"code": 500, "msg": "未找到待校正图片", "data": {}, "confidence": 0.0}

            exe_path = "/app/myprogram"
            corrected_results = []
            
            for source_image_path in images_to_correct:
                src_dir = os.path.dirname(source_image_path) or "."
                src_base = os.path.basename(source_image_path)
                
                cpp_default_output = os.path.join(src_dir, "image_geo_correct.tif")
                final_geo_path = os.path.join(src_dir, f"geo_correction_{src_base}")
                
                cmd = [exe_path, base_map_path, source_image_path, src_dir]
                print(f"[执行] 命令: {' '.join(cmd)}")
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=int(params.get("timeout", 300)),
                )
                
                if result.returncode != 0:
                    error_detail = (result.stderr or result.stdout or f"exit code {result.returncode}").strip()
                    return {"code": 500, "msg": f"C++ failed: {error_detail[:100]}", "data": {}, "confidence": 0.0}
                
                if os.path.exists(cpp_default_output):
                    os.rename(cpp_default_output, final_geo_path)
                else:
                    return {"code": 500, "msg": "C++运行成功但未找到默认输出文件", "data": {}, "confidence": 0.0}

                corrected_results.append({
                    "original_input": source_image_path,
                    "geo_corrected_path": final_geo_path
                })
            
            return {
                "code": 200,
                "msg": "Geo correction finished",
                "data": {
                    "geo_corrected_path": corrected_results[-1]["geo_corrected_path"],
                    "all_corrected_results": corrected_results,
                    "target_resolution": params.get("target_resolution", "2m")
                },
                "confidence": 0.96
            }
    except Exception as e:
        print("[ERROR] 预处理执行异常", exc_info=True)
        return {"code": 500, "msg": f"Algorithm execution failed: {str(e)}", "data": {}, "confidence": 0.0}

# ==========================================
# 3. 电子侦察逻辑 (ELINT)
# ==========================================
def run_elint_detection(region: dict) -> dict:
    base_lon = float(region.get("lon", 120.1))
    base_lat = float(region.get("lat", 30.2))
    score = 0.84
    
    # ELINT的散布范围通常更大，所以宽高设大一点
    hw_lon = 0.015
    hh_lat = 0.015
    center_lon = base_lon + random.uniform(-0.02, 0.02)
    center_lat = base_lat + random.uniform(-0.02, 0.02)

    target_data = {
        "targetName": "signal", 
        
        # --- 像素百分比坐标 (默认全覆盖) ---
        "leftTopX": 0.10, "leftTopY": 0.10,
        "leftBotX": 0.10, "leftBotY": 0.90,
        "rightTopX": 0.90, "rightTopY": 0.10,
        "rightBotX": 0.90, "rightBotY": 0.90,
        "center_x": 0.50, "center_y": 0.50,
        
        # --- 真实地理坐标 ---
        "leftTopLon": round(center_lon - hw_lon, 6),
        "leftTopLat": round(center_lat + hh_lat, 6),
        "leftBotLon": round(center_lon - hw_lon, 6),
        "leftBotLat": round(center_lat - hh_lat, 6),
        "rightTopLon": round(center_lon + hw_lon, 6),
        "rightTopYLat": round(center_lat + hh_lat, 6),
        "rightBotXLon": round(center_lon + hw_lon, 6),
        "rightBotYLat": round(center_lat - hh_lat, 6),
        "center_Lon": round(center_lon, 6),
        "center_Lat": round(center_lat, 6),
        
        # --- 业务属性 ---
        "score": score,
        "fusionSource": "elint_detection_service", # ★ 已修正为 fusionSource
        "auxInterpretationInfo": "电子侦察原始检出"
    }
    
    return {
        "code": 200, 
        "msg": "ELINT detection finished", 
        "data": {"detections": [target_data]}, 
        "confidence": score
    }

# ==========================================
# 4. MCP 格式封装 
# ==========================================
def build_mcp_response(subtask_id: str, tool_name: str, algo_response: dict) -> dict:

    return {
        "subtask_id": subtask_id,
        "tool_name": tool_name,
        "success": algo_response.get("code") == 200,
        "output": algo_response.get("data", {}),         
        "confidence": algo_response.get("confidence", 0.0), 
        "message": algo_response.get("msg") or f"{tool_name} 处理完成"
    }

# ==========================================
# 5. 统一路由入口
# ==========================================
@app.post("/infer")
def infer(payload: Dict[str, Any]):
    tool_name = payload.get("tool_name", "")
    subtask_id = payload.get("subtask_id", "")
    input_data = payload.get("input_data", {})
    params = payload.get("parameters", {})
    
    # --- 1. 预处理模块 ---
    if tool_name in {"sar_denoise_service", "optical_enhance_service", "geo_correction_service"}:
        tiff_path = params.get("tiff_path") or input_data.get("tiff_path", "")
        
        # 强制打印调试日志：看看发进来的到底是什么
        print(f"[调试] infer 收到预处理请求: {tool_name}, tiff_path: {tiff_path}")
        
        algo_response = run_local_preprocess_model(tool_name, tiff_path, params, input_data)

        
    # --- 2. 目标检测模块 ---
    elif tool_name in {
        "sar_aircraft_service", "sar_ship_service", "sar_vehicle_service",
        "optical_aircraft_service", "optical_ship_service", "optical_vehicle_service"
    }:
        target_name = tool_name.split("_")[1]
        algo_response = call_specific_algorithm_docker(tool_name, target_name, params)
        
    # --- 3. 电子侦察模块 ---
    elif tool_name == "elint_detection_service":
        region = get_region(payload)
        algo_response = run_elint_detection(region)
        
    # --- 4. 容错拦截 ---
    else:
        algo_response = {
            "code": 404, 
            "msg": "Tool not found in inference service", 
            "data": {}, 
            "confidence": 0.0
        }
    
    # 最后统一包装返回给调度器
    return build_mcp_response(subtask_id, tool_name, algo_response)
