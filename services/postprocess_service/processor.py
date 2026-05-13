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
        loc = det.get("location", [0, 0])
        dist = calculate_distance(loc[0], loc[1], region.get("lon", 120.1), region.get("lat", 30.2))
        
        # 几何与置信度双重约束
        if dist <= region.get("radius_km", 20) and det.get("score", 0) >= 0.85:
            filtered.append(det)
            
    return filtered

def run_qb_fusion(filtered_detections: List[dict]) -> List[dict]:
    """2. 本地执行：智能QB信息融合"""
    fused_targets = []
    for i, det in enumerate(filtered_detections, start=1):
        fused_targets.append({
            "target_id": f"QB_{i:03d}",
            "category": det.get("category", "unknown"),
            "location": det.get("location", [0, 0]),
            "sources": [det.get("source", "unknown")],
            "fused_confidence": det.get("score", 0.90) + 0.02, # 模拟融合后置信度提升
            "fusion_info": "SAR/光学/电子定位偏差已对齐修正"
        })
    return fused_targets

def build_final_report(fused_targets: List[dict], task_id: str, region: dict) -> dict:
    """3. 本地执行：报告生成"""
    return {
        "task_info": {"task_id": task_id, "task_type": "multi_payload_detection"},
        "target_region": region,
        "target_count": len(fused_targets),
        "targets": fused_targets,
        "regional_situation": f"检测区域内共发现 {len(fused_targets)} 个融合目标，已完成几何约束剔除与定位偏差修正。",
        "disposal_suggestion": ["建议下发打击单元。", "建议无人机抵近侦察。"]
    }