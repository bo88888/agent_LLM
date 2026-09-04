import os
import random
import traceback
import subprocess
from typing import Dict, Any
import cv2
import numpy as np
import rasterio
from rasterio.enums import Resampling
from fastapi import FastAPI
from SAR_pro import process_sar_image
from opt_pro import process_optical_rs_image
from Optical_detection.infer_OPT_SLD import run_optical_detection
from Slice_detection.resnet_infer import run_slice_batch_inference
from SAR_detection.infer_SAR import run_sar_detection

app = FastAPI()

def get_region(payload: Dict[str, Any]) -> Dict[str, Any]:
    input_data = payload.get("input_data", {})
    parsed = input_data.get("parsed_requirement") or input_data.get("xml_config", {})
    return parsed.get("target_region", {"lon": 120.1, "lat": 30.2, "radius_km": 20})

# ==========================================
# 1. 视觉目标检测逻辑
# ==========================================
def _geo_item_matches_payload(item: dict, payload_type: str) -> bool:
    item_payload = str(item.get("payload_type", "")).lower()
    if item_payload:
        return item_payload == payload_type
    original_input = str(item.get("original_input", "")).lower()
    return payload_type in original_input or not original_input


def select_detection_input(tool_name: str, params: dict, input_data: dict):
    """Select geo/preprocessed/raw input according to the adaptive plan.

    Every branch ends with the raw TIFF, so skipped or failed optional stages do
    not block detection.
    """
    payload_type = "sar" if tool_name.startswith("sar_") else "optical"
    preference = str(params.get("input_preference", "geo")).lower()
    previous_results = input_data.get("previous_results", {})
    candidates = {"geo": [], "preprocessed": [], "raw": []}

    for result in previous_results.values():
        for item in result.get("all_corrected_results", []) or []:
            if (
                item.get("quality_accepted", True)
                and _geo_item_matches_payload(item, payload_type)
                and item.get("geo_corrected_path")
            ):
                candidates["geo"].append(item["geo_corrected_path"])

        if result.get("quality_accepted", True) and result.get("geo_corrected_path"):
            candidates["geo"].append(result["geo_corrected_path"])

        preprocess_key = (
            "sar_denoised_path" if payload_type == "sar"
            else "optical_enhanced_path"
        )
        if result.get(preprocess_key):
            candidates["preprocessed"].append(result[preprocess_key])

    raw_path = input_data.get("tiff_path", "")
    if raw_path:
        candidates["raw"].append(raw_path)

    order_map = {
        "raw": ["raw", "preprocessed", "geo"],
        "preprocessed": ["preprocessed", "raw", "geo"],
        "geo": ["geo", "preprocessed", "raw"],
    }
    for source in order_map.get(preference, order_map["geo"]):
        for path in candidates[source]:
            resolved = path if str(path).startswith("/") else os.path.join("/app", path)
            if os.path.exists(resolved):
                return resolved, source
    return "", "none"


def image_sharpness(path: str) -> float:
    """Return a lightweight Laplacian sharpness score for geo quality gating."""
    with rasterio.open(path) as src:
        scale = max(src.width / 1024, src.height / 1024, 1.0)
        image = src.read(
            1,
            out_shape=(max(1, int(src.height / scale)), max(1, int(src.width / scale))),
            resampling=Resampling.nearest,
        ).astype(np.float32)
    values = image[np.isfinite(image)]
    if values.size < 32:
        return 0.0
    p2, p98 = np.percentile(values, [2, 98])
    if p98 <= p2:
        return 0.0
    normalized = np.clip((image - p2) / (p98 - p2) * 255.0, 0, 255).astype(np.uint8)
    return float(cv2.Laplacian(normalized, cv2.CV_32F).var())


def call_specific_algorithm_docker(tool_name: str, target_name: str, params: dict, input_data: dict) -> dict:
    mode = params.get("mode", "base_map")
    tiff_path, input_source = select_detection_input(tool_name, params, input_data)
    if not tiff_path:
        error_msg = f"目标检测阻断：未找到当前载荷({tool_name})可用的原始、预处理或校正影像"
        print(f"[错误] {error_msg}")
        return {
            "code": 500,
            "msg": error_msg,
            "data": {}
        }

    print(f"[智能选路] {tool_name} 使用 {input_source} 影像: {tiff_path}")
    
    # ----------------------------------------------------
    # 2. 真实视觉目标检测接入 (动态适配 SAR/光学 + ship/plane/vehicle)
    # ----------------------------------------------------
    algorithm_config_map = {
        "optical_ship_service": {
            "payload": "optical",
            "type": "ship",
            "weight": "best_ship.pt",
        },
        "optical_plane_service": {
            "payload": "optical",
            "type": "plane",
            "weight": "best_plane.pt",
        },
        "optical_vehicle_service": {
            "payload": "optical",
            "type": "vehicle",
            "weight": "best_vehicle.pt",
        },
        "sar_ship_service": {
            "payload": "sar",
            "type": "ship",
            "weight": "best_sar_ship.pt",
        },
        "sar_plane_service": {
            "payload": "sar",
            "type": "plane",
            "weight": "best_sar_plane.pt",
        },
        "sar_vehicle_service": {
            "payload": "sar",
            "type": "vehicle",
            "weight": "best_sar_vehicle.pt",
        },
    }

    if tool_name in algorithm_config_map and tiff_path and os.path.exists(tiff_path):
        algo_config = algorithm_config_map.get(tool_name)
        if not algo_config:
             return {"code": 500, "msg": f"不支持的视觉检测工具: {tool_name}", "data": {}}
             
        object_type = algo_config["type"]
        payload_type = algo_config["payload"]
        weigh_model = algo_config["weight"]
        if payload_type == "sar":
            model_dir = "/app/SAR_detection"
            inference_func = run_sar_detection
            default_conf = 0.25  # SAR 通常背景噪声较大，可设置稍微不同的默认置信度
        else:
            model_dir = "/app/Optical_detection"
            inference_func = run_optical_detection
            default_conf = 0.20

        model_path = f"{model_dir}/{algo_config['weight']}"

        print(f"[目标检测] ⚡ 启动真实检测 | 载荷: {payload_type} | 算法: {tool_name} | 模型: {weigh_model}| 目标: {object_type} | 图: {tiff_path}")
        
        if not os.path.exists(model_path):
            error_msg = f"未找到模型权重文件: {model_path}，请检查宿主机 Optical_detection 目录下是否有该文件！"
            print(f"[错误] {error_msg}")
            return {"code": 500, "msg": error_msg, "data": {}}
        
        try:
            output_root = os.path.join(os.path.dirname(tiff_path), "detect_results", payload_type, object_type)

            # 执行真实的 YOLO 推理
            raw_result = inference_func(
                image_path=tiff_path,
                model_path=model_path,
                output_root=output_root,
                object_type=object_type,
                payload_type=payload_type, 
                conf=params.get("conf", default_conf)
            )
         
            # 为检测结果补充调度系统需要的业务字段
            detections = raw_result.get("data", [])
            for det in detections:
                raw_slice_path = (
                    det.get("slicePath")
                    or det.get("opticalSlicePath")
                    or det.get("sarSlicePath")
                )
                det.pop("opticalSlicePath", None)
                det.pop("sarSlicePath", None)
                 # 1：单源检测数据
                det["flag"] = 1
                det["payloadType"] = payload_type
                if raw_slice_path:
                    det["slicePath"] = raw_slice_path
                    
                det["fusionSource"] = tool_name
                det["fusionBasis"] = f"{payload_type.upper()}视觉特征识别"    
                det["fusionInfo"] = "单源独立检出"       # 融合信息
                det["auxInterpretationInfo"] = f"YOLO {payload_type.upper()}视觉算法检出 (所属大类: {object_type})"
            
            return {
                "code": 200,
                "msg": f"success (real detection on {os.path.basename(tiff_path)})",
                "data": {
                    "detections": detections,
                    "detection_input_path": tiff_path,
                    "detection_input_source": input_source,
                }
            }
            
        except Exception as e:
            print(f"[ERROR] 真实算法执行异常:\n{traceback.format_exc()}")
            return {"code": 500, "msg": f"Real algorithm failed: {str(e)}", "data": {}}


    # ----------------------------------------------------
    # 3. 真实检测未执行时直接失败
    # ----------------------------------------------------
    if tool_name in algorithm_config_map:
        if not tiff_path:
            error_msg = f"目标检测失败：{tool_name} 未获取到待检测影像路径"
        elif not os.path.exists(tiff_path):
            error_msg = f"目标检测失败：待检测影像不存在: {tiff_path}"
        else:
            error_msg = f"目标检测失败：{tool_name} 未进入真实检测分支"
    else:
        error_msg = f"目标检测失败：不支持的视觉检测工具: {tool_name}"

    print(f"[错误] {error_msg}")
    return {
        "code": 500,
        "msg": error_msg,
        "data": {}
    }

# ==========================================
# 2. 预处理逻辑 
# ==========================================
def run_local_preprocess_model(tool_name: str, tiff_path: str, params: dict, input_data: dict) -> dict:
    if tool_name in {"sar_denoise_service", "optical_enhance_service"}:
        if not tiff_path or not os.path.exists(tiff_path):
            return {"code": 404, "msg": "文件不存在", "data": {}}
        
    base_dir = os.path.dirname(tiff_path) if tiff_path else ""
    base_name = os.path.basename(tiff_path) if tiff_path else ""
    name_only, ext = os.path.splitext(base_name) if base_name else ("", "")

    try:
        if tool_name == "sar_denoise_service":
            output_sar = os.path.join(base_dir, f"{name_only}_sar_denoised{ext}")
            
            # 获取算法参数
            kernel_size = params.get("kernel_size", 3)
            clip_quant = params.get("clip_quant", 2)
            n_std = params.get("n_std", 2)

            print(f"[预处理] P1 执行 SAR 去噪 | 输入: {tiff_path} ")
            
            # 调用真实算法
            process_sar_image(tiff_path, output_sar, kernel_size, clip_quant, n_std)
            
            return {
                "code": 200,
                "msg": "SAR denoise finished (Real)",
                "data": {"sar_denoised_path": output_sar}
            }
            
        elif tool_name == "optical_enhance_service":
            output_opt = os.path.join(base_dir, f"{name_only}_optical_enhanced{ext}")
            
            # 获取算法参数
            median_ksize = params.get("median_ksize", 3)
            clip_percent = params.get("clip_percent", 2)
            
            print(f"[预处理] P2 执行 光学增强 | 输入: {tiff_path}")
            
            # 调用真实算法
            process_optical_rs_image(tiff_path, output_opt, median_ksize, clip_percent)
            
            return {
                "code": 200,
                "msg": "Optical enhancement finished (Real)",
                "data": {"optical_enhanced_path": output_opt}
            }
        
        elif tool_name == "geo_correction_service":
            print(f"[预处理] P3 执行几何精矫正，input_data: {input_data.keys()}")
            target_class = params.get("target_class")
            previous_results = input_data.get("previous_results", {})
            payload_type = params.get("payload_type")
            if not payload_type:
                for res_content in previous_results.values():
                    if res_content.get("sar_denoised_path"):
                        payload_type = "sar"
                        break
                    elif res_content.get("optical_enhanced_path"):
                        payload_type = "optical"
                        break

            GEOMETRIC_BASE_MAP_MAP = {}
            if payload_type == "sar":
                GEOMETRIC_BASE_MAP_MAP = {
                    "ship": "/app/data/sample_packet/taiwansuao_harbor_ref.tif",
                    "plane": "/app/data/sample_packet/OPT_ref.tif",     
                    "vehicle": "/app/data/sample_packet/20220109-sarcar_wgs84_ref.tif"   
                }
            elif payload_type == "optical":
                GEOMETRIC_BASE_MAP_MAP = {
                    "ship": "/app/data/sample_packet/taiwansuao_harbor_ref.tif",
                    "plane": "/app/data/sample_packet/OPT_ref.tif",
                    "vehicle": "/app/data/sample_packet/vehicle_ref.tif"
                }

            base_map_path = GEOMETRIC_BASE_MAP_MAP.get(target_class)

            if not base_map_path or not os.path.exists(base_map_path):
                return {
                    "code": 500,
                    "msg": f"未找到{payload_type}/{target_class}对应的几何校正参考图",
                    "data": {},
                }


            images_to_correct = []

            for res_content in previous_results.values():
                if payload_type == "sar":
                    path = res_content.get("sar_denoised_path")
                else:
                    path = res_content.get("optical_enhanced_path")
                    
                if path: images_to_correct.append(path)

            # 预处理被智能体跳过或失败时，允许直接校正原始 TIFF。
            if not images_to_correct and tiff_path:
                images_to_correct.append(tiff_path)

            if not images_to_correct:
                return {"code": 500, "msg": "未找到待校正图片", "data": {}}

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
                print(f"✅ P3 几何精校正完成 | 目标: {target_class} | 输出: {final_geo_path}")

                if result.returncode != 0:
                    error_detail = (result.stderr or result.stdout or f"exit code {result.returncode}").strip()
                    return {"code": 500, "msg": f"C++ failed: {error_detail[:100]}", "data": {}}
                
                if os.path.exists(cpp_default_output):
                    os.rename(cpp_default_output, final_geo_path)
                else:
                    return {"code": 500, "msg": "C++运行成功但未找到默认输出文件", "data": {}}

                source_sharpness = image_sharpness(source_image_path)
                corrected_sharpness = image_sharpness(final_geo_path)
                sharpness_ratio = (
                    corrected_sharpness / source_sharpness
                    if source_sharpness > 0 else 1.0
                )
                min_ratio = float(os.getenv("GEO_MIN_SHARPNESS_RATIO", "0.55"))
                quality_accepted = sharpness_ratio >= min_ratio

                if not quality_accepted:
                    print(
                        "[几何质量门控] 校正结果清晰度下降明显，"
                        f"ratio={sharpness_ratio:.4f} < {min_ratio:.2f}，"
                        "检测阶段将回退到上游影像"
                    )

                corrected_results.append({
                    "original_input": source_image_path,
                    "geo_corrected_path": final_geo_path,
                    "payload_type": payload_type,
                    "source_sharpness": round(source_sharpness, 4),
                    "corrected_sharpness": round(corrected_sharpness, 4),
                    "sharpness_ratio": round(sharpness_ratio, 4),
                    "quality_accepted": quality_accepted,
                })
            
            return {
                "code": 200,
                "msg": "Geo correction finished",
                "data": {
                    "geo_corrected_path": corrected_results[-1]["geo_corrected_path"],
                    "all_corrected_results": corrected_results,
                    "target_resolution": params.get("target_resolution", "2m"),
                    "quality_accepted": corrected_results[-1]["quality_accepted"],
                    "quality_reason": (
                        "几何校正结果通过清晰度门控"
                        if corrected_results[-1]["quality_accepted"]
                        else "几何校正导致清晰度明显下降，检测回退到上游影像"
                    ),
                }
            }
    except Exception as e:
        print("[ERROR] 预处理执行异常")
        traceback.print_exc()
        return {"code": 500, "msg": f"Algorithm execution failed: {str(e)}", "data": {}}

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
        "data": {"detections": [target_data]}
    }

# ==========================================
# 4. MCP 格式封装 
# ==========================================

def build_mcp_response(subtask_id: str, tool_name: str, algo_response: dict) -> dict:
    response = {
        "subtask_id": subtask_id,
        "tool_name": tool_name,
        "success": algo_response.get("code") == 200,
        "output": algo_response.get("data", {}),         
        "message": algo_response.get("msg") or f"{tool_name} 处理完成",
    }
    return response

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
        print(f"[调试] infer 收到预处理请求: {tool_name}, tiff_path: {tiff_path}")
        algo_response = run_local_preprocess_model(tool_name, tiff_path, params, input_data)


    # --- 2. 目标检测模块 ---
    elif tool_name in {
        "sar_plane_service", "sar_ship_service", "sar_vehicle_service",
        "optical_plane_service", "optical_ship_service", "optical_vehicle_service"
    }:
        target_name = tool_name.split("_")[1]
        algo_response = call_specific_algorithm_docker(tool_name, target_name, params, input_data)
        
    # --- 3. 电子侦察模块 ---
    elif tool_name == "elint_detection_service":
        region = get_region(payload)
        algo_response = run_elint_detection(region)
        
    # --- 4. 容错拦截 ---
    else:
        algo_response = {
            "code": 404, 
            "msg": "Tool not found in inference service", 
            "data": {}
        }
    
    # 最后统一包装返回给调度器
    return build_mcp_response(subtask_id, tool_name, algo_response)

@app.post("/slice_infer")
def slice_infer_endpoint(payload: Dict[str, Any]):
    tool_name = payload.get("tool_name", "")
    subtask_id = payload.get("subtask_id", "")
    params = payload.get("parameters", {})

    slice_paths = params.get("pointPath", [])

    # 从调度器传入的参数中读取载荷类型和目标类别
    payload_type = params.get("payloadType", "")
    target_class = params.get("targetClass", "")
    # 打印调试信息，确保参数顺利到达底层
    print(f"\n[调试] 准备执行切片推理 | 工具: {tool_name}")
    print(f"[调试] 提取到的参数 -> PayloadType: {payload_type}, TargetClass: {target_class}, 路径数量: {len(slice_paths)}\n")
    algo_response = run_slice_batch_inference(
        slice_paths=slice_paths,
        tool_name=tool_name,
        payload_type=payload_type,
        target_class=target_class
    )

    return build_mcp_response(subtask_id, tool_name, algo_response)
