import math
from typing import List, Dict, Any

def calculate_distance(lon1, lat1, lon2, lat2):
    """简单的经纬度距离计算估算（单位：公里）"""
    dx = (lon1 - lon2) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    dy = (lat1 - lat2) * 111.32
    return math.sqrt(dx * dx + dy * dy)

def run_false_alarm_filter(tool_results: Dict[str, Any], region: dict) -> List[dict]:
    """1. 虚警剔除（当前阶段：直接放行所有底层算法检出的目标）"""
    all_detections = []
    
    for result in tool_results.values():
        if result.success and "detections" in result.output:
            all_detections.extend(result.output["detections"])

    return all_detections


def run_qb_fusion(filtered_detections: List[dict], merge_threshold_km: float = 0.1) -> List[dict]:
    
    return filtered_detections


# def run_false_alarm_filter(tool_results: Dict[str, Any], region: dict) -> List[dict]:
#     """1. 本地执行：虚警剔除（几何约束）"""
#     all_detections = []

#     for result in tool_results.values():
#         if result.success and "detections" in result.output:
#             all_detections.extend(result.output["detections"])

#     filtered = []
#     for det in all_detections:
#         lon = det.get("center_Lon", 0.0)
#         lat = det.get("center_Lat", 0.0)
        
#         dist = calculate_distance(lon, lat, region.get("lon", 120.1), region.get("lat", 30.2))
#         # 几何与置信度双重约束
#         if dist <= region.get("radius_km", 20) and det.get("score", 0) >= 0.85:
#             filtered.append(det)
            
#     return filtered

# def run_qb_fusion(filtered_detections: List[dict], merge_threshold_km: float = 0.1) -> List[dict]:
#     """2. 本地执行：真实的智能QB信息融合（基于距离聚合）"""
#     fused_targets = []
    
#     for det in filtered_detections:
#         lon1 = det.get("center_Lon", 0.0)
#         lat1 = det.get("center_Lat", 0.0)
#         target_name = det.get("targetName", "unknown")
#         source = det.get("fusionSource", "unknown")
#         merged = False
#         for ft in fused_targets:
#             lon2 = ft.get("center_Lon", 0.0)
#             lat2 = ft.get("center_Lat", 0.0)
#             dist = calculate_distance(lon1, lat1, lon2, lat2)

#             # 如果距离小于阈值且目标类型一致，进行融合
#             if dist <= merge_threshold_km and ft.get("targetName") == target_name:
#                 if source not in ft["_sources_list"]:
#                     ft["_sources_list"].append(source)
                
#                 # 置信度取最大值
#                 ft["score"] = max(ft.get("score", 0), det.get("score", 0))
                
#                 # 更新多信源融合字段
#                 ft["fusionSource"] = ",".join(ft["_sources_list"])
#                 ft["fusionBasis"] = f"空间邻近同类准则(相距 {dist:.3f} km)"
#                 ft["fusionInfo"] = f"多源智能融合 ({len(ft['_sources_list'])}个独立信源)"
#                 ft["auxInterpretationInfo"] = f"经多源交叉验证，目标置信度可靠。多源位置覆盖区中心: [{ft['center_Lon']:.4f}, {ft['center_Lat']:.4f}]"
#                 merged = True
#                 break

#         if not merged:
#             # 单一信源逻辑
#             new_target = det.copy()
#             new_target["target_id"] = f"QB_{len(fused_targets) + 1:03d}"
#             new_target["_sources_list"] = [source]
            
#             new_target["fusionSource"] = source
#             new_target["fusionBasis"] = "单信源几何约束过滤"
#             new_target["fusionInfo"] = "单一信源"
#             new_target["auxInterpretationInfo"] = det.get("auxInterpretationInfo", "无异常辅助判读信息")
       
#             fused_targets.append(new_target)
            
#     for ft in fused_targets:
#         if "_sources_list" in ft:
#             del ft["_sources_list"]
            
#     return fused_targets

def build_final_report(fused_targets: List[dict], task_id: str, region: dict, mode: str) -> dict:
    """3. 本地执行：报告生成"""
    mode_text = "切片目标识别" if mode == "slice" else "全域底图目标识别"
    return {
        "code": 200,
        "msg": f"任务执行成功。共发现 {len(fused_targets)} 个融合目标。",
        "data": fused_targets,
        
        # 将原有的系统元信息包装到一个附属字段中，避免破坏主结构
        "_system_info": {
            "task_id": task_id,
            "detection_mode": mode,
            "task_type": "multi_payload_detection",
            "target_region": region,
            "disposal_suggestion": ["建议下发打击单元。", "建议无人机抵近侦察。"]
        }
    }