import json
from typing import Any, Dict

from clients.ollama_client import OllamaClient
from core.llm_schema import RequirementSpec


class LLMUnderstandingAgent:
    """
    LLM 需求理解智能体。

    输入：
        用户自然语言
        XML解析结果
        任务上下文

    输出：
        RequirementSpec
    """

    def __init__(self, llm_client=None):
        self.llm = llm_client or OllamaClient()

    async def run(
        self,
        user_instruction: str,
        xml_context: Dict[str, Any] | None = None,
        task_context: Dict[str, Any] | None = None,
    ) -> RequirementSpec:

        xml_context = xml_context or {}
        task_context = task_context or {}

        schema = OllamaClient._model_schema(
            RequirementSpec
        )

        system_prompt = f"""
你是一个智能任务需求理解智能体。

你的任务是将用户自然语言任务转换为严格结构化的任务需求。

必须遵守以下规则：

1. payload_types 只能使用：
   SAR、OPTICAL、ELINT。

2. target_classes 只能使用：
   plane、ship、vehicle。

3. 用户说“光学”“可见光”“光学影像”时，
   统一映射为 OPTICAL。

4. 用户说“飞机”“飞行器”时，
   统一映射为 plane。

5. 用户说“舰船”“船舶”时，
   统一映射为 ship。

6. 用户说“车辆”“汽车”时，
   统一映射为 vehicle。

7. 不允许虚构用户没有提出的硬性时间限制。

8. required_capabilities 可以使用：
   preprocess
   geometry
   detect

9. execution_policy 中 preprocess 和 geo_correction 只能为：
   auto、force、skip。
   用户明确说“不做/跳过”时返回 skip；明确说“必须执行”时返回 force；
   未明确说明时返回 auto，不要擅自固定为 force。

10. 如果信息不明确，不要编造具体数值。

11. payload_types 和 target_classes 只允许根据【用户指令】进行提取。

12. XML任务上下文仅作为背景信息提供给你，
不得因为XML中存在某个payload_types或target_classes，
就把用户指令中没有明确表达的内容复制到输出。

13. 如果用户指令没有明确说明 SAR、OPTICAL 或 ELINT，
payload_types 必须返回空列表 []。

14. 如果用户指令没有明确说明飞机、舰船或车辆目标，
target_classes 必须返回空列表 []。

15. 不允许根据目标类别推测载荷类型。
例如用户只说“识别舰船”，不能自行推断为SAR，
因为舰船可能来自SAR影像，也可能来自光学影像。

16. XML中的payload_types和target_classes由后续程序负责
与用户指令进行一致性检查，你只负责提取用户明确表达的需求。

必须严格符合下面 JSON Schema：

{json.dumps(schema, ensure_ascii=False)}
"""

        user_prompt = f"""
【用户指令】
{user_instruction}

【XML任务上下文】
{json.dumps(
    xml_context,
    ensure_ascii=False,
    indent=2
)}

【当前任务上下文】
{json.dumps(
    task_context,
    ensure_ascii=False,
    indent=2
)}

请生成结构化任务需求。
"""

        result = await self.llm.chat_json(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            schema_model=RequirementSpec,
        )

        return result
