import math
from typing import Any, Dict, List, Tuple

from services.postprocess_service.mysql_target_db import (
    query_mysql_evidence_for_detections,
    query_mysql_situation_tracks,
    insert_mysql_prior_targets,
)


# =========================
# 可调参数
# =========================

# 融合距离阈值，0.1 km = 100 m
DEFAULT_MERGE_THRESHOLD_KM = 0.1

# 测试阶段先不按置信度硬过滤
MIN_ALGO_CONFIDENCE = 0.0
MIN_MYSQL_CONFIDENCE = 0.0
MIN_PRIOR_WRITE_CONFIDENCE = 0.0

# 信源可靠度
OPTICAL_RELIABILITY = 0.92
SAR_RELIABILITY = 0.90
MYSQL_RELIABILITY = 0.85
UNKNOWN_RELIABILITY = 0.80

# DS 中的不确定集合
THETA = "THETA"


def calculate_distance(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """
    经纬度距离估算，单位 km。
    """
    dx = (lon1 - lon2) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    dy = (lat1 - lat2) * 111.32
    return math.sqrt(dx * dx + dy * dy)


def run_false_alarm_filter(tool_results: Dict[str, Any], region: dict) -> List[dict]:
    """
    虚警剔除。

    当前阶段先不做复杂过滤，直接汇总所有算法检测结果。
    """
    all_detections = []

    for result in tool_results.values():
        if result.success and "detections" in result.output:
            all_detections.extend(result.output["detections"])

    return all_detections


def _get_confidence(det: Dict[str, Any]) -> float:
    """
    获取目标置信度。

    优先取 confidence；
    如果没有 confidence，则取 score；
    如果都没有，则为 0。
    """
    value = det.get("confidence", det.get("score", 0.0))

    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.0

    return max(0.0, min(1.0, value))


def _get_source(det: Dict[str, Any]) -> str:
    """
    获取证据来源。
    """
    return str(det.get("fusionSource") or det.get("source") or "unknown")


def _is_mysql_source(det: Dict[str, Any]) -> bool:
    """
    判断是否来自 MySQL 先验库。
    """
    source = _get_source(det).lower()
    return "mysql" in source or "prior" in source or "database" in source


def _source_reliability(det: Dict[str, Any]) -> float:
    """
    根据证据来源返回信源可靠度。
    """
    source = _get_source(det).lower()

    if "mysql" in source or "prior" in source or "database" in source:
        return MYSQL_RELIABILITY

    if "sar" in source:
        return SAR_RELIABILITY

    if "optical" in source or "yolo" in source or "vision" in source:
        return OPTICAL_RELIABILITY

    return UNKNOWN_RELIABILITY


def _valid_for_fusion(det: Dict[str, Any]) -> bool:
    """
    判断一条证据是否允许进入融合。

    当前测试阶段阈值是 0.0，
    也就是不按 confidence 删除目标，
    confidence 只作为 DS 融合权重使用。
    """
    confidence = _get_confidence(det)

    if _is_mysql_source(det):
        return confidence >= MIN_MYSQL_CONFIDENCE

    return confidence >= MIN_ALGO_CONFIDENCE


def _build_mass(det: Dict[str, Any]) -> Dict[str, float]:
    """
    根据一条证据构建 DS mass 函数。

    m(A) = confidence × source_reliability
    m(THETA) = 1 - m(A)
    """
    target_name = str(det.get("targetName", "unknown"))
    confidence = _get_confidence(det)
    reliability = _source_reliability(det)

    support = confidence * reliability
    support = max(0.0, min(0.999999, support))

    return {
        target_name: support,
        THETA: 1.0 - support,
    }


def _combine_two_masses(
    mass_a: Dict[str, float],
    mass_b: Dict[str, float],
) -> Tuple[Dict[str, float], float]:
    """
    Dempster 组合规则。

    targetName 相同：支持同一类别，置信度提升。
    targetName 不同：产生冲突 conflict。
    THETA 表示不确定集合。
    """
    combined: Dict[str, float] = {}
    conflict = 0.0

    for key_a, value_a in mass_a.items():
        for key_b, value_b in mass_b.items():
            product = value_a * value_b

            if key_a == THETA:
                intersection = key_b
            elif key_b == THETA:
                intersection = key_a
            elif key_a == key_b:
                intersection = key_a
            else:
                intersection = None

            if intersection is None:
                conflict += product
            else:
                combined[intersection] = combined.get(intersection, 0.0) + product

    if conflict >= 0.999999:
        return mass_a, conflict

    normalizer = 1.0 - conflict

    for key in list(combined.keys()):
        combined[key] = combined[key] / normalizer

    return combined, conflict


def _combine_masses(masses: List[Dict[str, float]]) -> Tuple[Dict[str, float], float]:
    """
    多条证据的 DS 融合。
    """
    if not masses:
        return {THETA: 1.0}, 0.0

    current = masses[0]
    max_conflict = 0.0

    for mass in masses[1:]:
        current, conflict = _combine_two_masses(current, mass)
        max_conflict = max(max_conflict, conflict)

    return current, max_conflict


def _ds_fusion(cluster: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    对一个目标簇做 DS 决策融合。
    """
    if not cluster:
        return {
            "targetName": "unknown",
            "belief": 0.0,
            "uncertainty": 1.0,
            "conflict": 0.0,
        }

    if len(cluster) == 1:
        target_name = cluster[0].get("targetName", "unknown")
        confidence = _get_confidence(cluster[0])
        return {
            "targetName": target_name,
            "belief": confidence,
            "uncertainty": 1.0 - confidence,
            "conflict": 0.0,
        }

    masses = [_build_mass(det) for det in cluster]
    fused_mass, conflict = _combine_masses(masses)

    class_items = {
        key: value
        for key, value in fused_mass.items()
        if key != THETA
    }

    if not class_items:
        target_name = cluster[0].get("targetName", "unknown")
        belief = _get_confidence(cluster[0])
    else:
        target_name = max(class_items, key=class_items.get)
        belief = class_items[target_name]

    uncertainty = fused_mass.get(THETA, 0.0)

    return {
        "targetName": target_name,
        "belief": max(0.0, min(1.0, belief)),
        "uncertainty": max(0.0, min(1.0, uncertainty)),
        "conflict": max(0.0, min(1.0, conflict)),
    }


def _weighted_average(cluster: List[Dict[str, Any]], key: str):
    """
    对经纬度、框坐标、角度等数值字段做置信度加权平均。
    """
    total_value = 0.0
    total_weight = 0.0

    for det in cluster:
        if key not in det or det.get(key) is None:
            continue

        try:
            value = float(det.get(key))
        except (TypeError, ValueError):
            continue

        weight = max(_get_confidence(det), 0.000001)

        total_value += value * weight
        total_weight += weight

    if total_weight == 0.0:
        return None

    return total_value / total_weight


def _choose_base_detection(cluster: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    选择融合结果基础字段。

    优先使用算法检测结果作为 base，
    不优先用 MySQL 数据库记录。
    """
    for det in cluster:
        if not _is_mysql_source(det):
            return dict(det)

    return dict(cluster[0])


def _remove_internal_fields(target: Dict[str, Any]) -> Dict[str, Any]:
    """
    删除内部临时字段，避免返回给前端。
    """
    cleaned = {}

    for key, value in target.items():
        if key.startswith("_"):
            continue
        if key in {"id", "created_at", "source", "target_id", "score", "slicePath", "sliceTiffPath",}:
            continue
        cleaned[key] = value

    return cleaned


def _get_current_detection_text(cluster: List[Dict[str, Any]]) -> str:
    """
    根据当前算法来源，生成更清晰的融合说明。

    例如：
    sar_ship_service -> SAR舰船检测结果
    optical_plane_service -> 光学飞机检测结果
    optical_vehicle_service -> 光学车辆检测结果
    """
    current_algorithm_sources = [
        _get_source(det)
        for det in cluster
        if not _is_mysql_source(det)
    ]

    current_source_text = ",".join(current_algorithm_sources) if current_algorithm_sources else "algorithm_detection"
    source_lower = current_source_text.lower()

    if "sar" in source_lower:
        payload_text = "SAR"
    elif "optical" in source_lower:
        payload_text = "光学"
    else:
        payload_text = "模型"

    if "plane" in source_lower:
        target_type_text = "飞机"
    elif "ship" in source_lower:
        target_type_text = "舰船"
    elif "vehicle" in source_lower:
        target_type_text = "车辆"
    else:
        target_type_text = "目标"

    return f"{payload_text}{target_type_text}检测结果"


def _build_fused_target(
    cluster: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    根据一个目标簇生成最终融合目标。
    """
    base = _choose_base_detection(cluster)
    ds_result = _ds_fusion(cluster)

    fused_target_name = ds_result["targetName"]
    belief = ds_result["belief"]
    uncertainty = ds_result["uncertainty"]
    conflict = ds_result["conflict"]

    # 更新类别和置信度
    base["targetName"] = fused_target_name
    base["confidence"] = round(belief, 6)
    base.pop("target_id", None)
    base.pop("score", None)
    base.pop("slicePath", None)
    base.pop("payloadType", None)
    base.pop("opticalSlicePath", None)
    base.pop("sarSlicePath", None)
    base.pop("currentSlicePath", None)
    base.pop("priorSlicePath", None)
    base.pop("sliceTiffPath", None)
    base.pop("currentSliceTiffPath", None)
    base.pop("priorSliceTiffPath", None)

    # 汇总当前检测和数据库先验的切片路径
    slice_paths = _collect_fusion_paths(cluster)
    base.pop("slicePath", None)
    base.update(slice_paths)

    sources = []

    for det in cluster:
        source = _get_source(det)
        if source not in sources:
            sources.append(source)

    has_mysql_prior = any(
        "mysql" in source.lower()
        for source in sources
    )
    is_multi_evidence = len(cluster) > 1 and has_mysql_prior

    # 1：仅检测；2：真正完成多源融合
    base["flag"] = 2 if is_multi_evidence else 1
    base["fusionSource"] = ",".join(sources)

    # 数值字段加权平均
    numeric_keys = [
        "leftTopX", "leftTopY",
        "leftBotX", "leftBotY",
        "rightTopX", "rightTopY",
        "rightBotX", "rightBotY",
        "center_x", "center_y",
        "leftTopLon", "leftTopLat",
        "leftBotLon", "leftBotLat",
        "rightTopLon", "rightTopYLat",
        "rightBotXLon", "rightBotYLat",
        "center_Lon", "center_Lat",
        "angle_deg",
    ]

    for key in numeric_keys:
        avg_value = _weighted_average(cluster, key)
        if avg_value is not None:
            base[key] = round(avg_value, 6)
            
    if base.get("angle_deg") is not None:
        base["angleReference"] = (
            "目标旋转检测框长轴相对于图像水平轴的方向角"
        )

    if is_multi_evidence and has_mysql_prior:
        algorithm_infos = []
        mysql_match_infos = []

        for det in cluster:
            if _is_mysql_source(det):
                mysql_id = det.get("id", "unknown")
                mysql_target_name = det.get("targetName", "unknown")
                mysql_confidence = _get_confidence(det)
                mysql_distance_km = det.get("_match_distance_km")
                prior_source = det.get("_prior_source", det.get("source", "unknown"))

                if mysql_distance_km is not None:
                    try:
                        mysql_distance_m = float(mysql_distance_km) * 1000.0
                    except (TypeError, ValueError):
                        mysql_distance_m = None
                else:
                    mysql_distance_m = None

                if mysql_distance_m is not None:
                    mysql_match_infos.append(
                        f"id={mysql_id}，"
                        f"targetName={mysql_target_name}，"
                        f"confidence={mysql_confidence:.4f}，"
                        f"priorSource={prior_source}，"
                        f"distance={mysql_distance_m:.2f}m"
                    )
                else:
                    mysql_match_infos.append(
                        f"id={mysql_id}，"
                        f"targetName={mysql_target_name}，"
                        f"confidence={mysql_confidence:.4f}，"
                        f"priorSource={prior_source}"
                    )

            else:
                algorithm_infos.append(
                    f"targetName={det.get('targetName', 'unknown')}，"
                    f"confidence={_get_confidence(det):.4f}，"
                    f"source={_get_source(det)}"
                )

        algorithm_text = "；".join(algorithm_infos) if algorithm_infos else "无模型检测详情"
        mysql_match_text = "；".join(mysql_match_infos) if mysql_match_infos else "无MySQL匹配详情"
        current_detection_text = _get_current_detection_text(cluster)

        base["fusionBasis"] = (
            f"DS证据理论融合：{current_detection_text} + MySQL本地目标先验数据库；"
            "关联条件：经纬度距离最近匹配"
        )

        base["fusionInfo"] = (
            f"DS融合目标，belief={belief:.4f}，"
            f"uncertainty={uncertainty:.4f}，"
            f"conflict={conflict:.4f}；"
            f"模型检测证据：{algorithm_text}；"
            f"MySQL匹配目标：{mysql_match_text}"
        )

        base["auxInterpretationInfo"] = (
            f"当前{current_detection_text}目标 {fused_target_name} "
            f"与MySQL先验库中的历史目标完成空间关联；"
            f"MySQL匹配信息：{mysql_match_text}；"
            f"经DS证据理论融合后，目标可信度更新为 {belief:.4f}。"
        )

    else:
        base["fusionBasis"] = base.get("fusionBasis", "单源模型检测结果")
        base["fusionInfo"] = base.get("fusionInfo", "单源独立检出")
        base["auxInterpretationInfo"] = base.get(
            "auxInterpretationInfo",
            f"目标 {fused_target_name} 未检索到可融合的MySQL先验证据。",
        )

    return _remove_internal_fields(base)


def _select_best_mysql_matches(
    algorithm_detections: List[Dict[str, Any]],
    mysql_detections: List[Dict[str, Any]],
) -> List[List[Dict[str, Any]]]:
    """
    对每一个算法检测目标：
    1. 找到它对应的 MySQL 候选目标
    2. 按距离从小到大排序
    3. 选择最近且没有被用过的 MySQL 目标
    4. 形成 cluster：[算法检测目标, MySQL最佳匹配目标]
    """
    clusters: List[List[Dict[str, Any]]] = []
    used_mysql_ids = set()

    for index, det in enumerate(algorithm_detections):
        candidates = [
            item for item in mysql_detections
            if item.get("_matched_detection_index") == index
        ]

        candidates = sorted(
            candidates,
            key=lambda item: float(item.get("_match_distance_km", 999999.0)),
        )

        best_mysql = None

        for candidate in candidates:
            mysql_unique_id = candidate.get("id")

            if mysql_unique_id is None:
                mysql_unique_id = (
                    candidate.get("targetName"),
                    candidate.get("center_Lon"),
                    candidate.get("center_Lat"),
                )

            if mysql_unique_id not in used_mysql_ids:
                best_mysql = candidate
                used_mysql_ids.add(mysql_unique_id)
                break

        if best_mysql is not None:
            print(
                "[Fusion Match] "
                f"det_index={index}, "
                f"det_target={det.get('targetName')}, "
                f"det_source={_get_source(det)}, "
                f"mysql_id={best_mysql.get('id')}, "
                f"mysql_target={best_mysql.get('targetName')}, "
                f"prior_source={best_mysql.get('_prior_source')}, "
                f"distance_m={float(best_mysql.get('_match_distance_km', 0)) * 1000:.2f}"
            )
            clusters.append([det, best_mysql])
        else:
            clusters.append([det])

    return clusters
def run_situation_fusion(
    fused_targets: List[Dict[str, Any]],
    merge_threshold_km: float = DEFAULT_MERGE_THRESHOLD_KM,
) -> List[Dict[str, Any]]:
    """
    将当前融合目标与MySQL态势轨迹进行空间关联。

    规则：
    1. 使用每个态势目标的最新轨迹点；
    2. 在距离阈值内选择最近目标；
    3. 检测目标和态势目标一对一匹配；
    4. 返回匹配目标的完整历史轨迹；
    5. 不输出类别一致性或类别冲突判读。
    """
    if not fused_targets:
        return []

    situation_tracks = query_mysql_situation_tracks()

    if not situation_tracks:
        print("[MySQL Situation] 未读取到态势轨迹，跳过态势融合")
        return fused_targets

    candidates = []

    # 构建所有空间距离满足阈值的候选匹配
    for detection_index, detection in enumerate(fused_targets):
        try:
            detection_lng = float(
                detection.get("center_Lon")
            )
            detection_lat = float(
                detection.get("center_Lat")
            )
        except (TypeError, ValueError):
            continue

        for track in situation_tracks:
            try:
                track_lng = float(track.get("lng"))
                track_lat = float(track.get("lat"))
            except (TypeError, ValueError):
                continue

            distance_km = calculate_distance(
                detection_lng,
                detection_lat,
                track_lng,
                track_lat,
            )

            if distance_km <= merge_threshold_km:
                candidates.append(
                    (
                        distance_km,
                        detection_index,
                        track,
                    )
                )

    # 只按照空间距离由近到远排序
    candidates.sort(key=lambda item: item[0])

    used_detection_indexes = set()
    used_situation_ids = set()
    assignments = {}

    # 全局一对一最近匹配
    for distance_km, detection_index, track in candidates:
        situation_id = track.get("target_id")

        if detection_index in used_detection_indexes:
            continue

        if situation_id in used_situation_ids:
            continue

        used_detection_indexes.add(detection_index)
        used_situation_ids.add(situation_id)

        assignments[detection_index] = (
            distance_km,
            track,
        )

    results = []

    for detection_index, detection in enumerate(fused_targets):
        result = dict(detection)

        # 防止旧字段残留
        result.pop("situationFusionJudgement", None)

        assignment = assignments.get(detection_index)

        if assignment is None:
            results.append(result)
            continue

        distance_km, track = assignment
        distance_m = distance_km * 1000.0

        # 增加态势数据来源
        source_text = str(
            result.get("fusionSource", "")
        )

        sources = [
            source.strip()
            for source in source_text.split(",")
            if source.strip()
        ]

        if "mysql_situation" not in sources:
            sources.append("mysql_situation")

        # 匹配到态势信息后属于多源信息融合
        result["flag"] = 2

        # 只保留用户需要的态势字段
        result["matchedSituationInfo"] = {
            "target_id": track.get("target_id"),
            "target_type": track.get("target_type"),
            "lng": track.get("lng"),
            "lat": track.get("lat"),
            "target_time": track.get("target_time"),
            "distance_m": round(distance_m, 2),
            "trajectory": track.get("trajectory", []),
        }
        

        # 判断当前检测载荷类型
        source_lower = ",".join(sources).lower()

        if "optical" in source_lower:
            payload_text = "光学"
        elif "sar" in source_lower:
            payload_text = "SAR"
        else:
            payload_text = "模型"

        target_name = str(
            result.get("targetName", "unknown")
        )

        try:
            fused_confidence = float(
                result.get("confidence", 0.0)
            )
        except (TypeError, ValueError):
            fused_confidence = 0.0

        track_count = len(
            track.get("trajectory", [])
        )

        # 直接重写四个字段，不继续拼接原来的长文本
        result["fusionSource"] = ",".join(sources)

        result["fusionBasis"] = (
            f"{payload_text}检测与MySQL先验采用DS证据融合，"
            "态势轨迹采用经纬度最近邻一对一匹配"
        )

        result["fusionInfo"] = (
            f"融合{payload_text}目标 {target_name}、"
            f"MySQL先验和态势信息，"
            f"置信度 {fused_confidence:.4f}"
        )

        result["auxInterpretationInfo"] = (
            f"匹配态势目标 {track.get('target_id')}，"
            f"类型 {track.get('target_type')}，"
            f"距离 {distance_m:.2f}m，"
            f"包含 {track_count} 个轨迹点"
        )

        print(
            "[Situation Match] "
            f"det_index={detection_index}, "
            f"det_target={result.get('targetName')}, "
            f"situation_id={track.get('target_id')}, "
            f"situation_target={track.get('target_type')}, "
            f"distance_m={distance_m:.2f}"
        )

        results.append(result)

    print(
        f"[MySQL Situation] 成功匹配 "
        f"{len(assignments)} 个态势目标"
    )

    return results

def run_qb_fusion(
    filtered_detections: List[dict],
    merge_threshold_km: float = DEFAULT_MERGE_THRESHOLD_KM,
) -> List[dict]:
    """
    MySQL 先验数据库 + DS 证据理论融合主入口。

    流程：
    1. 整理算法检测结果
    2. 根据每个检测目标查询 MySQL 附近先验目标
    3. 为每个算法目标选择最近的 MySQL 目标
    4. 对 [算法目标, MySQL目标] 做 DS 融合
    5. 融合后，把当前算法检测结果写入 MySQL，作为后续任务先验
    """
    if not filtered_detections:
        return []

    # 1. 整理算法检测结果
    algorithm_detections: List[Dict[str, Any]] = []

    for det in filtered_detections:
        item = dict(det)

        item.setdefault("fusionSource", item.get("source", "algorithm_detection"))
        item.setdefault("fusionBasis", "模型检测证据")
        item.setdefault("fusionInfo", "深度学习模型检测结果")

        if _valid_for_fusion(item):
            algorithm_detections.append(item)

    if not algorithm_detections:
        return []

    # 2. 查询 MySQL 先验目标
    mysql_detections = query_mysql_evidence_for_detections(
        detections=algorithm_detections,
        radius_km=merge_threshold_km,
    )

    valid_mysql_detections: List[Dict[str, Any]] = []

    for det in mysql_detections:
        item = dict(det)

        item.setdefault("fusionSource", "mysql_prior")
        item.setdefault("fusionBasis", "MySQL本地目标先验数据库")
        item.setdefault("fusionInfo", "MySQL数据库先验证据")

        if _valid_for_fusion(item):
            valid_mysql_detections.append(item)

    # 3. 为每个算法目标选择最近的 MySQL BestChoice
    clusters = _select_best_mysql_matches(
        algorithm_detections=algorithm_detections,
        mysql_detections=valid_mysql_detections,
    )

    # 4. 对每个目标簇做 DS 融合
    fused_targets = []

    for index, cluster in enumerate(clusters, start=1):
        fused_targets.append(
            _build_fused_target(
                cluster=cluster,
            )
        )

    # 5. 融合完成后，再把当前算法检测结果写入 MySQL
    # 注意：写入的是 algorithm_detections，不是 fused_targets
    # 这样 source 保存的是 optical_ship_service / sar_ship_service 等原始算法来源
    # 5. 将DS融合结果与MySQL态势轨迹进行空间关联和一致性判读
    fused_targets = run_situation_fusion(
        fused_targets=fused_targets,
        merge_threshold_km=merge_threshold_km,
    )

    # 6. 将当前算法检测结果写入MySQL先验库

    inserted_count = insert_mysql_prior_targets(
        detections=algorithm_detections,
        min_confidence=MIN_PRIOR_WRITE_CONFIDENCE,
        duplicate_radius_km=0.02,
    )

    if inserted_count > 0:
        print(f"[MySQL Prior] 本次新增 {inserted_count} 条目标先验记录")

    return fused_targets


def _get_payload_type(det: Dict[str, Any]) -> str:
    payload_type = str(det.get("payloadType") or "").lower()

    if payload_type in {"optical", "sar"}:
        return payload_type

    source = str(
        det.get("_prior_source")
        or det.get("source")
        or det.get("fusionSource")
        or ""
    ).lower()

    if "optical" in source:
        return "optical"

    if "sar" in source:
        return "sar"

    return "unknown"

def _collect_fusion_paths(
    cluster: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    汇总当前检测结果和数据库先验结果的
    JPG及GeoTIFF切片路径。
    """
    result: Dict[str, Any] = {}

    for det in cluster:
        payload_type = _get_payload_type(det)

        if _is_mysql_source(det):
            result["priorPayloadType"] = payload_type
            result["priorSource"] = str(
                det.get("_prior_source")
                or det.get("source")
                or "unknown"
            )

            prior_path = (
                det.get("slicePath")
                or det.get("priorSlicePath")
            )

            if prior_path:
                result["priorSlicePath"] = prior_path

            prior_tiff_path = (
                det.get("sliceTiffPath")
                or det.get("priorSliceTiffPath")
            )

            if prior_tiff_path:
                result["priorSliceTiffPath"] = (
                    prior_tiff_path
                )

        else:
            result["currentPayloadType"] = payload_type
            result["currentSource"] = _get_source(det)

            current_path = (
                det.get("slicePath")
                or det.get("currentSlicePath")
                or det.get("opticalSlicePath")
                or det.get("sarSlicePath")
            )

            if current_path:
                result["currentSlicePath"] = (
                    current_path
                )

            current_tiff_path = (
                det.get("sliceTiffPath")
                or det.get("currentSliceTiffPath")
            )

            if current_tiff_path:
                result["currentSliceTiffPath"] = (
                    current_tiff_path
                )

    return result

def build_final_report(
    fused_targets: List[dict],
    task_id: str,
    region: dict,
    mode: str,
) -> dict:
    """
    最终报告生成。
    """
    return {
        "code": 200,
        "msg": f"任务执行成功。共发现 {len(fused_targets)} 个融合目标。",
        "data": fused_targets,
    }




# cd /home/air/code_LLM/agent_LLM

# docker exec -i agent_mysql sh -c \
#   'exec mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' \
#   < Situation_fusion.sql


# 4. 验证内网数据库
# docker exec agent_mysql mysql -uair -p123 agent -e "
# SELECT
#     COUNT(*) AS total_points,
#     COUNT(DISTINCT target_id) AS total_targets
# FROM target_situation_track;
# "

# 预期：

# 50    5

# 检查最新轨迹点：

# docker exec agent_mysql mysql -uair -p123 agent -e "
# SELECT
#     t.target_id,
#     t.target_type,
#     t.lng,
#     t.lat,
#     t.target_time
# FROM target_situation_track t
# JOIN (
#     SELECT target_id, MAX(target_time) AS latest_time
#     FROM target_situation_track
#     GROUP BY target_id
# ) latest
# ON t.target_id = latest.target_id
# AND t.target_time = latest.latest_time
# ORDER BY t.target_id;
# "
# 四、内网机配置并重启

# 内网机的 MySQL 是同一 Compose 中的容器，因此 docker-compose.yml 应设置：

# MYSQL_HOST: "mysql"
# MYSQL_PORT: "3306"
# MYSQL_USER: "air"
# MYSQL_PASSWORD: "123"
# MYSQL_DATABASE: "agent"

# SITUATION_MATCH_RADIUS_KM: "0.1"
# SITUATION_MAX_AGE_SECONDS: "2592000"
# SITUATION_DEFAULT_CONFIDENCE: "0.90"

# 重新创建应用容器：

# cd /home/air/code_LLM/agent_LLM

# docker-compose up -d --force-recreate app

# 检查配置是否生效：

# docker exec multi_payload_app env \
#   | grep -E '^MYSQL_|^SITUATION_'

# 检查服务端口：

# docker port multi_payload_app 9000/tcp

# 内网配置通常显示：

# 0.0.0.0:9011


# 五、运行任务验证自动关联

# 使用内网机映射端口，例如 9011：

# curl -X POST "http://127.0.0.1:9011/api/v1/task/submit" \
#   -H "Content-Type: application/json" \
#   -d '{
#     "task_id": "TEST_SITUATION_001",
#     "tiff_path": "http://host.docker.internal:8889/data/sample_packet/taiwansuao_harbor_OPT.tif",
#     "requirement_xml_path": "http://host.docker.internal:8889/data/requirement.xml"
#   }'

# 查看日志：

# docker logs --tail 200 -f multi_payload_app

# 正常关联时应出现：

# [Situation Match]

# 最终结果中应包含：

# "fusionSource": "optical_ship_service,mysql_prior,mysql_situation"