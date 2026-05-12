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

MOCK_URL = "http://127.0.0.1:8101/infer"

TOOL_SERVICE_MAP = {
    "sar_denoise_service": MOCK_URL,
    "optical_enhance_service": MOCK_URL,
    "geo_correction_service": MOCK_URL,

    "sar_aircraft_service": MOCK_URL,
    "sar_ship_service": MOCK_URL,
    "sar_vehicle_service": MOCK_URL,

    "optical_aircraft_service": MOCK_URL,
    "optical_ship_service": MOCK_URL,
    "optical_vehicle_service": MOCK_URL,

    "elint_detection_service": MOCK_URL,

    "false_alarm_filter_service": MOCK_URL,
    "qb_fusion_service": MOCK_URL,
    "report_service": MOCK_URL,
}
