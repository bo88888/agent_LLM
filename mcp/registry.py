from typing import Dict, Iterable, Optional

from core.tool_capabilities import DEFAULT_TOOL_CAPABILITY_MAP, ToolCapability


class ToolRegistry:
    """工具服务注册表。

    作用：
    - 保存 tool_name 到 HTTP 服务地址的映射。
    - InvokerAgent 调用服务前，会根据 subtask.tool_name 在这里查 URL。

    数据来源：
    - api_main.py 中 build_registry() 会读取 config.py 的 TOOL_SERVICE_MAP。
    """

    def __init__(self, capabilities: Optional[Iterable[ToolCapability]] = None):
        self._services = {}
        source = capabilities or DEFAULT_TOOL_CAPABILITY_MAP.values()
        self._capabilities: Dict[str, ToolCapability] = {
            capability.tool_name: capability for capability in source
        }

    def register(
        self,
        tool_name: str,
        service_url: str,
        capability: Optional[ToolCapability] = None,
    ):
        """注册一个工具服务地址。"""
        self._services[tool_name] = service_url
        if capability is not None:
            self._capabilities[tool_name] = capability

    def get(self, tool_name: str) -> str:
        """根据工具服务名获取 HTTP URL。

        如果 router.py 生成了某个 tool_name，
        但 config.py 没有配置它的 URL，这里会抛出 KeyError。
        """
        if tool_name not in self._services:
            raise KeyError(f"Tool service not registered: {tool_name}")
        return self._services[tool_name]

    def has_tool(self, tool_name: str) -> bool:
        """判断工具是否有可调用的 HTTP 服务地址。"""
        return tool_name in self._services

    def get_capability(self, tool_name: str) -> ToolCapability:
        """根据工具服务名获取能力描述。"""
        if tool_name not in self._capabilities:
            raise KeyError(f"Tool capability not registered: {tool_name}")
        return self._capabilities[tool_name]

    def list_capabilities(self) -> Dict[str, ToolCapability]:
        """返回当前全部工具能力描述。"""
        return dict(self._capabilities)

    def list_tools(self):
        """返回当前已经注册的全部工具服务映射。"""
        # 返回一个拷贝，避免外部直接修改内部 _services。
        return dict(self._services)
