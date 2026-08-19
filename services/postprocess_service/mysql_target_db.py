import math
import os
from typing import Any, Dict, List

import pymysql
from pymysql.cursors import DictCursor


def calculate_distance_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """
    经纬度距离估算，单位 km。
    """
    dx = (lon1 - lon2) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    dy = (lat1 - lat2) * 111.32
    return math.sqrt(dx * dx + dy * dy)


def get_mysql_config() -> Dict[str, Any]:
    """
    从 docker-compose.yml 的 environment 中读取 MySQL 配置。
    """
    return {
        "host": os.getenv("MYSQL_HOST", "172.17.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "air"),
        "password": os.getenv("MYSQL_PASSWORD", "123"),
        "database": os.getenv("MYSQL_DATABASE", "agent"),
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "connect_timeout": 3,
        "read_timeout": 5,
        "write_timeout": 5,
    }


def query_mysql_prior_targets(
    detection: Dict[str, Any],
    detection_index: int,
    radius_km: float = 0.1,
) -> List[Dict[str, Any]]:
    """
    根据一条算法检测结果，在 MySQL target_prior 表里找附近先验目标。

    注意：
    这里不强制 targetName 相同。
    原因是允许不同类别之间产生 DS 冲突，
    例如当前 SAR 检测为 minchuan，数据库先验为 cruiser。
    """
    target_name = detection.get("targetName")
    center_lon = detection.get("center_Lon")
    center_lat = detection.get("center_Lat")

    if center_lon is None or center_lat is None:
        return []

    try:
        center_lon = float(center_lon)
        center_lat = float(center_lat)
    except (TypeError, ValueError):
        return []

    # 粗筛范围，0.01 度大约 1 km 左右
    lon_delta = 0.01
    lat_delta = 0.01

    sql = """
        SELECT *
        FROM target_prior
        WHERE center_Lon BETWEEN %s AND %s
          AND center_Lat BETWEEN %s AND %s
    """

    try:
        conn = pymysql.connect(**get_mysql_config())
        with conn.cursor() as cursor:
            cursor.execute(
                sql,
                (
                    center_lon - lon_delta,
                    center_lon + lon_delta,
                    center_lat - lat_delta,
                    center_lat + lat_delta,
                ),
            )
            rows = cursor.fetchall()
        conn.close()

    except Exception as exc:
        print(f"[MySQL Prior] 查询 target_prior 失败: {exc}")
        return []

    results: List[Dict[str, Any]] = []

    for row in rows:
        try:
            prior_lon = float(row.get("center_Lon"))
            prior_lat = float(row.get("center_Lat"))
        except (TypeError, ValueError):
            continue

        distance_km = calculate_distance_km(
            center_lon,
            center_lat,
            prior_lon,
            prior_lat,
        )

        if distance_km <= radius_km:
            item = dict(row)

            # 这条证据现在是从 MySQL 查出来的，所以 fusionSource 写 mysql_prior
            item["fusionSource"] = "mysql_prior"
            item["fusionBasis"] = "MySQL本地目标先验数据库"
            item["fusionInfo"] = f"MySQL先验目标，相距 {distance_km * 1000:.1f} m"
            item["auxInterpretationInfo"] = "MySQL目标先验库提供的历史/先验目标证据"

            # 这条数据库记录最早来自哪个算法
            # 例如 optical_ship_service / sar_ship_service / optical_plane_service 等
            item["_prior_source"] = row.get("source", "unknown")

            # 内部临时字段，用于后续判断和输出详细融合信息
            item["_matched_detection_index"] = detection_index
            item["_match_distance_km"] = distance_km
            item["_query_targetName"] = target_name

            results.append(item)

    return results


def query_mysql_evidence_for_detections(
    detections: List[Dict[str, Any]],
    radius_km: float = 0.1,
) -> List[Dict[str, Any]]:
    """
    对所有算法检测结果批量查询 MySQL 先验证据。
    """
    evidence: List[Dict[str, Any]] = []

    for index, det in enumerate(detections):
        evidence.extend(
            query_mysql_prior_targets(
                detection=det,
                detection_index=index,
                radius_km=radius_km,
            )
        )

    return evidence


def insert_mysql_prior_targets(
    detections: List[Dict[str, Any]],
    min_confidence: float = 0.0,
    duplicate_radius_km: float = 0.02,
) -> int:
    """
    将算法检测结果写入 MySQL 先验库。

    重点：
    source 字段不再写死为 mysql_prior，
    而是保存原始算法服务名：

    optical_ship_service
    sar_ship_service
    optical_plane_service
    sar_plane_service
    optical_vehicle_service
    sar_vehicle_service

    这样后续 SAR 检测结果与 MySQL 先验融合时，
    可以知道 MySQL 里的历史目标最早来自光学还是 SAR。
    """
    inserted_count = 0

    try:
        conn = pymysql.connect(**get_mysql_config())
    except Exception as exc:
        print(f"[MySQL Prior] 连接数据库失败，无法写入先验库: {exc}")
        return 0

    try:
        with conn.cursor() as cursor:
            for det in detections:
                target_name = det.get("targetName")
                center_lon = det.get("center_Lon")
                center_lat = det.get("center_Lat")
                confidence = det.get("confidence", det.get("score", 0.0))

                # 这里直接使用检测结果里已有的算法服务名
                # 不再额外判断船、飞机、车辆
                prior_source = (
                    det.get("fusionSource")
                    or det.get("source")
                    or "algorithm_detection"
                )
                # 新增：载荷类型
                payload_type = ( det.get("payloadType") 
                    or det.get("currentPayloadType")
                    )   

                # 新增：获取当前目标的切片路径
                slice_path = (
                    det.get("slicePath")
                    or det.get("currentSlicePath")
                    or det.get("opticalSlicePath")
                    or det.get("sarSlicePath")
                )

                # 新增：检测框宽度和长度
                target_width = det.get("width")
                target_length = det.get("length")
 
                if not target_name or center_lon is None or center_lat is None:
                    continue

                try:
                    center_lon = float(center_lon)
                    center_lat = float(center_lat)
                    confidence = float(confidence)
                except (TypeError, ValueError):
                    continue

                if confidence < min_confidence:
                    continue

                # 查询附近是否已有同类目标，避免重复入库
                cursor.execute(
                    """
                    SELECT id, center_Lon, center_Lat
                    FROM target_prior
                    WHERE targetName = %s
                      AND center_Lon BETWEEN %s AND %s
                      AND center_Lat BETWEEN %s AND %s
                    """,
                    (
                        target_name,
                        center_lon - 0.001,
                        center_lon + 0.001,
                        center_lat - 0.001,
                        center_lat + 0.001,
                    ),
                )

                rows = cursor.fetchall()

                # 保存匹配到的数据库目标ID
                duplicate_id = None

                for row in rows:
                    dist = calculate_distance_km(
                        center_lon,
                        center_lat,
                        float(row["center_Lon"]),
                        float(row["center_Lat"]),
                    )

                    if dist <= duplicate_radius_km:
                        duplicate_id = row["id"]
                        break

                if duplicate_id is not None:
                    # 目标已经存在时，补充原来为空的新字段
                    cursor.execute(
                        """
                        UPDATE target_prior
                        SET payloadType = COALESCE(payloadType, %s),
                            slicePath = COALESCE(NULLIF(slicePath, ''), %s),
                            width = COALESCE(width, %s),
                            length = COALESCE(length, %s)
                        WHERE id = %s
                        """,
                        (
                            payload_type,
                            slice_path,
                            target_width,
                            target_length,
                            duplicate_id,
                        ),
                    )

                    # 更新已有目标后，不再重复插入新目标
                    continue

                cursor.execute(
                    """
                    INSERT INTO target_prior (
                        targetName,
                        center_Lon,
                        center_Lat,
                        confidence,
                        source,
                        payloadType,
                        slicePath,
                        width,
                        length,
                        leftTopX,
                        leftTopY,
                        leftBotX,
                        leftBotY,
                        rightTopX,
                        rightTopY,
                        rightBotX,
                        rightBotY,
                        center_x,
                        center_y,
                        leftTopLon,
                        leftTopLat,
                        leftBotLon,
                        leftBotLat,
                        rightTopLon,
                        rightTopYLat,
                        rightBotXLon,
                        rightBotYLat,
                        angle_deg
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s
                    )
                    """,
                    (
                        target_name,
                        center_lon,
                        center_lat,
                        confidence,
                        str(prior_source),
                        payload_type,
                        slice_path,
                        target_width,
                        target_length,

                        det.get("leftTopX"),
                        det.get("leftTopY"),
                        det.get("leftBotX"),
                        det.get("leftBotY"),
                        det.get("rightTopX"),
                        det.get("rightTopY"),
                        det.get("rightBotX"),
                        det.get("rightBotY"),

                        det.get("center_x"),
                        det.get("center_y"),

                        det.get("leftTopLon"),
                        det.get("leftTopLat"),
                        det.get("leftBotLon"),
                        det.get("leftBotLat"),
                        det.get("rightTopLon"),
                        det.get("rightTopYLat"),
                        det.get("rightBotXLon"),
                        det.get("rightBotYLat"),

                        det.get("angle_deg"),
                    ),
                )

                inserted_count += 1

        conn.commit()

    except Exception as exc:
        conn.rollback()
        print(f"[MySQL Prior] 写入 target_prior 失败: {exc}")

    finally:
        conn.close()

    return inserted_count