from pathlib import Path

from core.schema import ExecutionContext


class InputAgent:
    """输入端智能体：检查底图 tif 和任务 XML 文件，并记录基础元信息。"""

    def run(self, context: ExecutionContext) -> ExecutionContext:
        tiff_path = Path(context.request.tiff_path)
        xml_path = Path(context.request.requirement_xml_path)

        context.metadata["tiff_exists"] = tiff_path.exists()
        context.metadata["requirement_xml_exists"] = xml_path.exists()
        context.metadata["tiff_path"] = str(tiff_path)
        context.metadata["requirement_xml_path"] = str(xml_path)
        context.metadata["input_stage"] = "validated"
        return context