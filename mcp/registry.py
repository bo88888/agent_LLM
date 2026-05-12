class ToolRegistry:
    """工具服务注册表。

    作用：
    - 保存 tool_name 到 HTTP 服务地址的映射。
    - InvokerAgent 调用服务前，会根据 subtask.tool_name 在这里查 URL。

    数据来源：
    - main.py 中 build_registry() 会读取 config.py 的 TOOL_SERVICE_MAP。
    """

    def __init__(self):
        # 内部字典结构：
        # {
        #     "sar_denoise_service": "http://127.0.0.1:8101/infer",
        #     "geo_correction_service": "http://127.0.0.1:8103/infer",
        # }
        self._services = {}

    def register(self, tool_name: str, service_url: str):
        """注册一个工具服务地址。"""
        self._services[tool_name] = service_url

    def get(self, tool_name: str) -> str:
        """根据工具服务名获取 HTTP URL。

        如果 router.py 生成了某个 tool_name，
        但 config.py 没有配置它的 URL，这里会抛出 KeyError。
        """
        if tool_name not in self._services:
            raise KeyError(f"Tool service not registered: {tool_name}")
        return self._services[tool_name]

    def list_tools(self):
        """返回当前已经注册的全部工具服务映射。"""
        # 返回一个拷贝，避免外部直接修改内部 _services。
        return dict(self._services)
