# multi_payload_mcp_scheduler

本项目是一个“多载荷目标检测任务调度器”示例工程。它接收任务需求，将任务拆解成多个子任务，通过 MCP 风格的 HTTP 请求调用工具服务，完成预处理、目标检测、虚警过滤、QB 融合和结构化报告生成。

当前默认使用 `mock_all_service` 跑通 demo：所有工具服务都映射到 `http://127.0.0.1:8101/infer`。如果要调用独立 Docker 服务，需要修改 `config.py` 中的 `TOOL_SERVICE_MAP`。

## 输入

主入口是 `main.py`，输入由两部分组成：

- `TaskRequest`：主程序中构造的任务请求。
- `data/requirement.json`：外部任务需求文件。

### TaskRequest

`main.py` 中会构造如下任务：

```python
TaskRequest(
    task_id="TASK_MULTI_001",
    data_packet_path=DATA_PACKET_PATH,
    requirement_doc_path=REQUIREMENT_DOC_PATH,
    payload_types=["SAR", "OPTICAL", "ELINT"],
    target_classes=["aircraft", "ship", "vehicle"],
    target_region={"lon": 120.10, "lat": 30.20, "radius_km": 20},
    output_requirements={
        "format": "json",
        "need_confidence": True,
        "need_suggestion": True,
    },
)
```

字段说明：

- `task_id`：任务编号。
- `data_packet_path`：数据包目录，默认是 `data/sample_packet`。
- `requirement_doc_path`：需求文件路径，默认是 `data/requirement.json`。
- `payload_types`：载荷类型，例如 `SAR`、`OPTICAL`、`ELINT`。
- `target_classes`：目标类别，例如 `aircraft`、`ship`、`vehicle`。
- `target_region`：目标区域，经纬度和半径。
- `output_requirements`：输出格式、置信度、处置建议等要求。

### requirement.json

示例文件：`data/requirement.json`

```json
{
  "task_type": "multi_payload_detection",
  "payload_types": ["SAR", "OPTICAL", "ELINT"],
  "target_classes": ["aircraft", "ship", "vehicle"],
  "target_region": {
    "lon": 120.1,
    "lat": 30.2,
    "radius_km": 20
  },
  "output_requirements": {
    "format": "json",
    "need_confidence": true,
    "need_suggestion": true
  },
  "constraints": {
    "priority": "high",
    "need_geo_correction": true
  }
}
```

`UnderstandingAgent` 会读取该 JSON，解析任务类型、载荷类型、目标类别、目标区域、输出要求和约束。如果 JSON 中缺少字段，则回退到 `TaskRequest` 中的默认值。

## 输出

最终输出文件：

```text
outputs/final_report.json
```

报告主要字段：

- `task_info`：任务编号和任务类型。
- `target_count`：融合后的目标数量。
- `targets`：融合目标列表。
- `regional_situation`：区域态势描述。
- `confidence_assessment`：整体置信度评估。
- `disposal_suggestion`：处置建议。
- `execution_status`：调度执行状态，包括每个子任务状态、失败原因、阻塞原因和重试次数。

示例结构：

```json
{
  "task_info": {
    "task_id": "TASK_MULTI_001",
    "task_type": "multi_payload_detection"
  },
  "target_count": 7,
  "targets": [
    {
      "target_id": "QB_001",
      "category": "sar_aircraft",
      "location": [120.123, 30.456],
      "sources": ["sar_aircraft_service"],
      "fused_confidence": 0.9
    }
  ],
  "regional_situation": "多载荷目标探测与融合任务已完成。",
  "confidence_assessment": 0.92,
  "disposal_suggestion": [
    "建议对重点区域持续监视。",
    "建议结合后续多时相数据复核。"
  ],
  "execution_status": {
    "pass": true,
    "issues": [],
    "tasks": []
  }
}
```

## 整体算法框架

```text
TaskRequest + requirement.json
        |
        v
InputAgent
        |
        v
UnderstandingAgent
        |
        v
DecomposeAgent
        |
        v
PlanningAgent
        |
        v
SchedulerCenter -> InvokerAgent -> MCP HTTP services
        |
        v
PostprocessAgent
        |
        v
Quality Assessment
        |
        v
ReportAgent
        |
        v
outputs/final_report.json
```

各阶段职责：

- `InputAgent`：检查数据包目录和需求文件是否存在。
- `UnderstandingAgent`：读取并解析 `requirement.json`。
- `DecomposeAgent`：根据载荷类型和目标类别生成子任务 DAG。
- `PlanningAgent`：记录执行计划。
- `SchedulerCenter`：根据依赖关系调度子任务，处理并发、重试、失败和阻塞。
- `InvokerAgent`：封装 MCP 请求并调用 HTTP 工具服务。
- `PostprocessAgent`：汇总虚警过滤和融合结果。
- `assess_quality`：检查失败任务、阻塞任务和低置信度结果。
- `ReportAgent`：生成最终报告并附加执行状态。

## 默认子任务 DAG

默认输入为 `SAR + OPTICAL + ELINT` 和 `aircraft + ship + vehicle` 时，生成如下任务图：

```text
P1: sar_denoise_service
P2: optical_enhance_service

P1 + P2
   |
   v
P3: geo_correction_service
   |
   v
D1: sar_aircraft_service
D2: sar_ship_service
D3: sar_vehicle_service
D4: optical_aircraft_service
D5: optical_ship_service
D6: optical_vehicle_service

D7: elint_detection_service

D1 + D2 + D3 + D4 + D5 + D6 + D7
   |
   v
F1: false_alarm_filter_service
   |
   v
F2: qb_fusion_service
   |
   v
R1: report_service
```

说明：

- `P1` 和 `P2` 可以并发执行。
- `P3` 依赖 `P1` 和 `P2`。
- SAR/OPTICAL 检测任务依赖 `P3`。
- `D7` 是 ELINT 检测任务，当前不依赖 `P3`。
- `F1` 依赖所有检测任务。
- `F2` 依赖 `F1`。
- `R1` 依赖 `F2`。

## MCP 请求与响应

`MCPWrapper` 会把上下文和子任务封装成 MCP 风格请求。

请求结构：

```json
{
  "task_id": "TASK_MULTI_001",
  "subtask_id": "D1",
  "tool_name": "sar_aircraft_service",
  "input_data": {
    "data_packet_path": "data/sample_packet",
    "parsed_requirement": {},
    "previous_results": {},
    "metadata": {}
  },
  "parameters": {},
  "output_schema": ["detections"]
}
```

响应结构：

```json
{
  "subtask_id": "D1",
  "tool_name": "sar_aircraft_service",
  "success": true,
  "output": {
    "detections": []
  },
  "confidence": 0.91,
  "message": "finished"
}
```

## 任务状态

状态定义在 `core/enums.py`：

- `PENDING`：等待执行。
- `RUNNING`：正在执行。
- `SUCCESS`：执行成功。
- `FAILED`：执行失败，且重试次数已用完。
- `BLOCKED`：前置依赖失败，当前任务无法执行。

失败处理规则：

- 工具调用抛异常或返回 `success=false` 时，调度器先重试。
- 重试次数由 `SubTask.max_retry` 控制，默认是 `1`。
- 重试后仍失败，任务标记为 `FAILED`。
- 依赖失败任务的下游任务标记为 `BLOCKED`。
- 失败和阻塞信息写入最终报告的 `execution_status`。

## 运行方式

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动 mock 服务

当前 `config.py` 默认使用 mock 模式，所有工具服务都指向 `http://127.0.0.1:8101/infer`：

```bash
python -m uvicorn services.mock_all_service.app:app --host 127.0.0.1 --port 8101
```

### 3. 运行主流程

另开一个终端执行：

```bash
python main.py
```

输出文件：

```text
outputs/final_report.json
```

## Docker 独立服务

`docker-compose.yml` 定义了多个独立服务：

- `sar_denoise_service`：SAR 去噪预处理。
- `optical_enhance_service`：光学增强预处理。
- `geo_correction_service`：几何精校正。
- `sar_aircraft_service`：SAR 飞机检测。
- `sar_ship_service`：SAR 舰船检测。
- `sar_vehicle_service`：SAR 车辆检测。
- `optical_aircraft_service`：光学飞机检测。
- `optical_ship_service`：光学舰船检测。
- `optical_vehicle_service`：光学车辆检测。
- `elint_detection_service`：电子侦察检测。
- `false_alarm_filter_service`：虚警过滤。
- `qb_fusion_service`：QB 信息融合。
- `report_service`：报告生成。

启动方式：

```bash
docker compose up --build
```

注意：如果要调用这些独立 Docker 服务，需要把 `config.py` 中的 `TOOL_SERVICE_MAP` 改成各自端口：

```python
TOOL_SERVICE_MAP = {
    "sar_denoise_service": "http://127.0.0.1:8101/infer",
    "optical_enhance_service": "http://127.0.0.1:8102/infer",
    "geo_correction_service": "http://127.0.0.1:8103/infer",
    "sar_aircraft_service": "http://127.0.0.1:8201/infer",
    "sar_ship_service": "http://127.0.0.1:8202/infer",
    "sar_vehicle_service": "http://127.0.0.1:8203/infer",
    "optical_aircraft_service": "http://127.0.0.1:8301/infer",
    "optical_ship_service": "http://127.0.0.1:8302/infer",
    "optical_vehicle_service": "http://127.0.0.1:8303/infer",
    "elint_detection_service": "http://127.0.0.1:8401/infer",
    "false_alarm_filter_service": "http://127.0.0.1:8501/infer",
    "qb_fusion_service": "http://127.0.0.1:8601/infer",
    "report_service": "http://127.0.0.1:8701/infer",
}
```

## 完整项目结构

下面列的是源码和运行相关文件；`__pycache__/` 是 Python 自动生成的缓存目录，不需要关注。

```text
multi_payload_mcp_scheduler/
  README.md                                # 项目说明文档
  requirements.txt                         # 主程序依赖
  docker-compose.yml                       # 独立工具服务 Docker 编排
  main.py                                  # 主入口，串联完整调度流程
  config.py                                # 输入路径、输出路径、服务映射、阈值

  core/                                    # 核心数据结构与任务路由
    __init__.py
    schema.py                              # TaskRequest/SubTask/ToolResult/ExecutionContext
    enums.py                               # PayloadType/TargetClass/TaskStatus
    router.py                              # 根据需求生成子任务 DAG

  agents/                                  # 各阶段 agent
    __init__.py
    input_agent.py                         # 输入校验
    understanding_agent.py                 # 需求解析
    decompose_agent.py                     # 任务拆解
    planning_agent.py                      # 执行计划记录
    invoker_agent.py                       # 工具调用封装
    postprocess_agent.py                   # 后处理摘要
    report_agent.py                        # 最终报告封装

  scheduler/                               # 调度模块
    __init__.py
    scheduler_center.py                    # 依赖调度、并发执行、重试、失败和阻塞处理

  mcp/                                     # MCP 风格协议封装
    __init__.py
    protocol.py                            # MCPRequest/MCPResponse
    wrapper.py                             # 将上下文和子任务封装为 MCP 请求
    registry.py                            # 工具名到服务 URL 的注册表

  clients/                                 # HTTP 客户端
    __init__.py
    base_http_client.py                    # 同步 HTTP 客户端
    async_http_client.py                   # 异步 HTTP 客户端

  data/                                    # 输入数据
    requirement.json                       # 示例任务需求
    sample_packet/
      placeholder.txt                      # 示例数据包占位文件

  outputs/                                 # 输出目录
    final_report.json                      # 最近一次运行生成的最终报告

  services/                                # 工具服务集合
    mock_all_service/
      app.py                               # demo 用统一模拟服务，一个服务模拟所有工具

    sar_denoise_service/
      __init__.py
      app.py                               # SAR 去噪服务
      Dockerfile
      requirements.txt

    optical_enhance_service/
      __init__.py
      app.py                               # 光学增强服务
      Dockerfile
      requirements.txt

    geo_correction_service/
      __init__.py
      app.py                               # 几何精校正服务
      Dockerfile
      requirements.txt

    sar_aircraft_service/
      __init__.py
      app.py                               # SAR 飞机检测服务
      Dockerfile
      requirements.txt

    sar_ship_service/
      __init__.py
      app.py                               # SAR 舰船检测服务
      Dockerfile
      requirements.txt

    sar_vehicle_service/
      __init__.py
      app.py                               # SAR 车辆检测服务
      Dockerfile
      requirements.txt

    optical_aircraft_service/
      __init__.py
      app.py                               # 光学飞机检测服务
      Dockerfile
      requirements.txt

    optical_ship_service/
      __init__.py
      app.py                               # 光学舰船检测服务
      Dockerfile
      requirements.txt

    optical_vehicle_service/
      __init__.py
      app.py                               # 光学车辆检测服务
      Dockerfile
      requirements.txt

    elint_detection_service/
      __init__.py
      app.py                               # 电子侦察检测服务
      Dockerfile
      requirements.txt

    false_alarm_filter_service/
      __init__.py
      app.py                               # 虚警过滤服务
      Dockerfile
      requirements.txt

    qb_fusion_service/
      __init__.py
      app.py                               # QB 信息融合服务
      Dockerfile
      requirements.txt

    report_service/
      __init__.py
      app.py                               # 结构化报告生成服务
      Dockerfile
      requirements.txt
```
