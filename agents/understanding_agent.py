import json
import xml.etree.ElementTree as ET
from core.schema import ExecutionContext


def normalize_target_region(region: dict) -> dict:
    """校验并规范化目标区域。

    输入 region 通常来自 requirement.json，例如：
    {
        "lon": 120.1,
        "lat": 30.2,
        "radius_km": 20
    }
    """
    # 使用默认值可以提高 demo 的容错性：
    # 如果字段缺失，仍然能使用默认目标区域继续运行。
    lon = float(region.get("lon", 120.1))
    lat = float(region.get("lat", 30.2))
    radius_km = float(region.get("radius_km", 20))

    # 经度范围校验。
    if not -180 <= lon <= 180:
        raise ValueError(f"target_region.lon out of range: {lon}")

    # 纬度范围校验。
    if not -90 <= lat <= 90:
        raise ValueError(f"target_region.lat out of range: {lat}")

    # 搜索半径必须为正数。
    if radius_km <= 0:
        raise ValueError(f"target_region.radius_km must be positive: {radius_km}")

    return {"lon": lon, "lat": lat, "radius_km": radius_km}


class UnderstandingAgent:
    """需求理解智能体。

    解析 XML 需求文件
    # 假设 XML 结构如下：
        # <Task>
        #   <PayloadTypes>SAR,OPTICAL</PayloadTypes>
        #   <TargetClasses>aircraft,ship</TargetClasses>
        #   <Region lon="120.1" lat="30.2" radius="20"/>
        #   <SliceSize>1k*1k</SliceSize>
        # </Task>
    写入 context.parsed_requirement。
    """

    def run(self, context: ExecutionContext) -> ExecutionContext:
        xml_path = context.request.requirement_xml_path
        tree = ET.parse(xml_path)
        root = tree.getroot()
        payload_text = root.findtext('PayloadTypes', "")
        target_text = root.findtext('TargetClasses', "")
        region_node = root.find('Region')
        slice_size = root.findtext('SliceSize', "1k*1k")

        context.parsed_requirement = {
            "task_type": doc.get("task_type", "multi_payload_detection"),
            "payload_types": doc.get("payload_types", context.request.payload_types),
            "target_classes": doc.get("target_classes", context.request.target_classes),
            "target_region": normalize_target_region(
                doc.get("target_region", context.request.target_region)
            ),
            "slice_size": slice_size,
            "tiff_path": context.request.tiff_path，
            "output_requirements": doc.get("output_requirements", context.request.output_requirements),
            "constraints": doc.get("constraints", {}),
        }

        return context
