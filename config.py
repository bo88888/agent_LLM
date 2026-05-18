# 底图 tif 路径：算法对接文档中的 tiff_path。
TIFF_PATH = "data/sample_packet/base_map.tif"

# XML 任务文件路径：用于描述目标类型、载荷类型、经纬度、切片大小等。
REQUIREMENT_XML_PATH = "data/requirement.xml"

# 新代码优先使用 TIFF_PATH 和 REQUIREMENT_XML_PATH。
DATA_PACKET_PATH = "data/sample_packet"
REQUIREMENT_DOC_PATH = REQUIREMENT_XML_PATH

OUTPUT_REPORT_PATH = "outputs/final_report.json"
HTTP_TIMEOUT = 60
QUALITY_THRESHOLD = 0.75

PREPROCESS_URL = "http://127.0.0.1:8001/infer"       # Docker 1: 预处理
DETECTION_URL = "http://127.0.0.1:8001/infer"        # Docker 2: 目标检测 (SAR + 光学)
ELINT_URL = "http://127.0.0.1:8001/infer"            # Docker 3: 电子侦察

TOOL_SERVICE_MAP = {
    # Docker 1
    "sar_denoise_service": PREPROCESS_URL,
    "optical_enhance_service": PREPROCESS_URL,
    "geo_correction_service": PREPROCESS_URL,

    # Docker 2
    "sar_aircraft_service": DETECTION_URL,
    "sar_ship_service": DETECTION_URL,
    "sar_vehicle_service": DETECTION_URL,
    "optical_aircraft_service": DETECTION_URL,
    "optical_ship_service": DETECTION_URL,
    "optical_vehicle_service": DETECTION_URL,

    # Docker 3
    "elint_detection_service": ELINT_URL,
}
