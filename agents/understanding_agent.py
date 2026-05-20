import xml.etree.ElementTree as ET
from core.schema import ExecutionContext

def normalize_target_region(region: dict) -> dict:
    """校验并规范化目标区域。"""
    lon = float(region.get("lon") or 120.1)
    lat = float(region.get("lat") or 30.2)
    radius_km = float(region.get("radius_km") or 20)

    if not -180 <= lon <= 180:
        raise ValueError(f"target_region.lon out of range: {lon}")
    if not -90 <= lat <= 90:
        raise ValueError(f"target_region.lat out of range: {lat}")

    return {"lon": lon, "lat": lat, "radius_km": radius_km}

class UnderstandingAgent:
    """需求理解智能体。
    解析 XML 需求文件并写入 context.parsed_requirement。
    """
    def run(self, context: ExecutionContext) -> ExecutionContext:
        tree = ET.parse(context.request.requirement_xml_path)
        root = tree.getroot()

        # 1. 提取列表类型的参数 (注意这里就是 payload_types 和 target_classes)
        payload_types = [t.text for t in root.findall('payload_types/type')]
        target_classes = [c.text for c in root.findall('target_classes/class')]

        # 2. 提取识别模式与切片专属参数
        mode = root.findtext('detection_mode', 'base_map') 
        slice_inputs = {}
        if mode == 'slice':
            slice_inputs = {
                "basePath": root.findtext('slice_inputs/basePath'),
                "pointPath": root.findtext('slice_inputs/pointPath'),
                "lon": float(root.findtext('slice_inputs/lon') or 0.0),
                "lat": float(root.findtext('slice_inputs/lat') or 0.0),
                "height": int(root.findtext('slice_inputs/height') or 512),
                "width": int(root.findtext('slice_inputs/width') or 512),
            }
        input_files = {
            "SAR": root.findtext('input_files/SAR', ''),
            "OPTICAL": root.findtext('input_files/OPTICAL', '')
        }


        # 3. 组装字典
        context.parsed_requirement = {
            "detection_mode": mode,         
            "slice_inputs": slice_inputs,   
            "input_files": input_files,

            "task_type": root.findtext('task_type', "multi_payload_detection"),
            "payload_types": payload_types or context.request.payload_types,
            "target_classes": target_classes or context.request.target_classes,
            
            "target_region": normalize_target_region({
                "lon": root.findtext('target_region/lon'),
                "lat": root.findtext('target_region/lat'),
                "radius_km": root.findtext('target_region/radius_km')
            }),
            
            "slice_size": root.findtext('tile_size', "1k*1k"),
            "tiff_path": context.request.tiff_path,
            
            "output_requirements": {
                "format": root.findtext('output_requirements/format', 'json'),
                "need_confidence": root.findtext('output_requirements/need_confidence', 'true') == 'true',
                "need_suggestion": root.findtext('output_requirements/need_suggestion', 'true') == 'true'
            },
            
            "constraints": {
                "priority": root.findtext('constraints/priority', 'normal'),
                "need_geo_correction": root.findtext('constraints/need_geo_correction', 'true') == 'true'
            },
        }

        return context