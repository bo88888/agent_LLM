import xml.etree.ElementTree as ET
from core.schema import ExecutionContext

def normalize_target_region(region: dict) -> dict:
    lon = float(region.get("lon") or 120.1)
    lat = float(region.get("lat") or 30.2)
    radius_km = float(region.get("radius_km") or 20)
    return {"lon": lon, "lat": lat, "radius_km": radius_km}


def parse_optional_bool(value):
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    return None

class UnderstandingAgent:

    def run(self, context: ExecutionContext) -> ExecutionContext:
        tree = ET.parse(context.request.requirement_xml_path)
        root = tree.getroot()

        # 1. 提取列表类型的参数 (注意这里就是 payload_types 和 target_classes)
        payload_types = [t.text for t in root.findall('payload_types/type')]
        target_classes = [c.text for c in root.findall('target_classes/class')]

        legacy_need_geo = parse_optional_bool(
            root.findtext('constraints/need_geo_correction')
        )
        preprocess_mode = (
            root.findtext('constraints/preprocess_mode') or 'auto'
        ).strip().lower()
        explicit_geo_mode = root.findtext('constraints/geo_correction_mode')
        geo_mode = (explicit_geo_mode or 'auto').strip().lower()
        if legacy_need_geo is not None and explicit_geo_mode is None:
            geo_mode = "force" if legacy_need_geo else "skip"

        context.parsed_requirement = {
            "task_type": root.findtext('task_type', "multi_payload_detection"),
            
            # 直接使用 XML 里读取的载荷类型
            "payload_types": payload_types,
            "target_classes": target_classes,
            
            # 直接使用 API 前端传来的单张图片路径
            "tiff_path": context.request.tiff_path,
            
            # "target_region": normalize_target_region({
            #     "lon": root.findtext('target_region/lon'),
            #     "lat": root.findtext('target_region/lat'),
            #     "radius_km": root.findtext('target_region/radius_km')
            # }),
            
            # "slice_size": context.request.slice_size,
            "output_requirements": context.request.output_requirements,
            "constraints": {
                "need_geo_correction": legacy_need_geo,
                "preprocess_mode": preprocess_mode,
                "geo_correction_mode": geo_mode,
            },
            "execution_policy": {
                "preprocess": preprocess_mode,
                "geo_correction": geo_mode,
            },
        }

        return context
