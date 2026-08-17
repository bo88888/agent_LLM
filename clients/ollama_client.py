import json
from typing import Any, Dict, List, Type

import httpx
from pydantic import BaseModel

from config import (
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT,
)


class OllamaClient:
    """
    Ollama HTTP API 客户端。

    只负责：
    1. Ollama 连通性检查
    2. 调用 /api/chat
    3. 获取结构化 JSON
    """

    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = OLLAMA_MODEL,
        timeout: int = OLLAMA_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def health_check(self) -> Dict[str, Any]:
        """
        检查 Ollama 服务以及当前模型是否存在。
        """

        url = f"{self.base_url}/api/tags"

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _model_schema(schema_model: Type[BaseModel]) -> Dict[str, Any]:
        """
        同时兼容 Pydantic v1 / v2。
        """

        if hasattr(schema_model, "model_json_schema"):
            return schema_model.model_json_schema()

        return schema_model.schema()

    @staticmethod
    def _validate_model(
        schema_model: Type[BaseModel],
        data: Dict[str, Any],
    ) -> BaseModel:
        """
        同时兼容 Pydantic v1 / v2。
        """

        if hasattr(schema_model, "model_validate"):
            return schema_model.model_validate(data)

        return schema_model.parse_obj(data)

    async def chat_json(
        self,
        messages: List[Dict[str, str]],
        schema_model: Type[BaseModel],
    ) -> BaseModel:
        """
        要求 Ollama 根据指定 Pydantic Schema 返回结构化 JSON。
        """

        schema = self._model_schema(schema_model)

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,

            # Ollama structured output
            "format": schema,

            # 调度决策希望尽量稳定
            "options": {
                "temperature": 0
            },
        }

        url = f"{self.base_url}/api/chat"

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:

                response = await client.post(
                    url,
                    json=payload,
                )

                response.raise_for_status()

        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"Ollama request timeout after "
                f"{self.timeout}s: {url}"
            ) from exc

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Ollama HTTP error "
                f"{exc.response.status_code}: "
                f"{exc.response.text[:500]}"
            ) from exc

        except httpx.RequestError as exc:
            raise RuntimeError(
                f"Cannot connect to Ollama at "
                f"{self.base_url}: {exc}"
            ) from exc

        response_data = response.json()

        try:
            content = response_data["message"]["content"]
        except KeyError as exc:
            raise RuntimeError(
                f"Invalid Ollama response: {response_data}"
            ) from exc

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Ollama returned invalid JSON: {content}"
            ) from exc

        return self._validate_model(
            schema_model,
            parsed,
        )