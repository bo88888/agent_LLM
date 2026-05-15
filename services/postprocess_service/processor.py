import math
from typing import List, Dict, Any

def calculate_distance(lon1, lat1, lon2, lat2):
    """简单的经纬度距离计算估算（单位：公里）"""
    dx = (lon1 - lon2) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    dy = (lat1 - lat2) * 111.32
    return math.sqrt(dx * dx + dy * dy)

def run_false_alarm_filter(tool_results: Dict[str, Any], region: dict) -> List[dict]:
    """1. 本地执行：虚警剔除（几何约束）"""
    all_detections = []
    # 从调度器跑完的 tool_results 中提取所有检测目标
    for result in tool_results.values():
        if result.success and "detections" in result.output:
            all_detections.extend(result.output["detections"])

    filtered = []
    for det in all_detections:
        lon = det.get("center_Lon", 0.0)
        lat = det.get("center_Lat", 0.0)
        
        dist = calculate_distance(lon, lat, region.get("lon", 120.1), region.get("lat", 30.2))
        # 几何与置信度双重约束
        if dist <= region.get("radius_km", 20) and det.get("score", 0) >= 0.85:
            filtered.append(det)
            
    return filtered

def run_qb_fusion(filtered_detections: List[dict], merge_threshold_km: float = 0.1) -> List[dict]:
    """2. 本地执行：真实的智能QB信息融合（基于距离聚合）"""
    fused_targets = []
    
    for det in filtered_detections:
        lon1 = det.get("center_Lon", 0.0)
        lat1 = det.get("center_Lat", 0.0)
        target_name = det.get("targetName", "unknown")
        source = det.get("fusionSource", "unknown")
        
        # 寻找是否已经有距离相近的、同类的融合目标
        merged = False
        for ft in fused_targets:
            lon2 = ft.get("center_Lon", 0.0)
            lat2 = ft.get("center_Lat", 0.0)
            
            # 计算当前检测目标与已有融合目标的距离
            dist = calculate_distance(lon1, lat1, lon2, lat2)
            
            # 如果距离小于阈值（默认100米），且目标类型一致，认为是同一个目标进行合并
            if dist <= merge_threshold_km and ft.get("targetName") == target_name:
                # 把新的信源加进去
                if source not in ft["_sources_list"]:
                    ft["_sources_list"].append(source)
                
                # 置信度取最大值
                ft["score"] = max(ft.get("score", 0), det.get("score", 0))
                # 将信源拼接成文档要求的字符串，例如: "sar_aircraft_service,optical_aircraft_service"
                ft["fusionSource"] = ",".join(ft["_sources_list"])
                ft["fusionInfo"] = f"多源融合 ({len(ft['_sources_list'])} 个独立信源)"
                merged = True
                break
                
        # 如果没有相近的目标，就当做一个新目标加进去
        if not merged:
            # 直接复制当前检测到的完整字典（保留所有的 leftTopX 等字段）
            new_target = det.copy()
            new_target["target_id"] = f"QB_{len(fused_targets) + 1:03d}"
            new_target["_sources_list"] = [source] # 内部辅助列表，用于记录信源
            new_target["fusionInfo"] = "单一信源"
            fused_targets.append(new_target)
            
    for ft in fused_targets:
        if "_sources_list" in ft:
            del ft["_sources_list"]
            
    return fused_targets

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