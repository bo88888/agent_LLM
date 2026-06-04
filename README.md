# multi_payload_mcp_scheduler

本项目是一个“多载荷目标检测任务调度中心”示例工程。当前实现采用 **FastAPI 主调度服务 + MCP 风格 JSON 协议 + HTTP 算法服务** 的结构：前端提交任务后，系统读取 XML 需求文件，把总任务拆解为可调度的子任务 DAG，再通过 HTTP 调用算法服务完成预处理、目标检测、电子侦察、切片识别、后处理融合和报告生成。

当前代码没有把 MCP 工具调用改成 stdio/Popen 传输。主调度链路走 HTTP；只有算法服务内部的几何校正会通过 `subprocess.run` 调用本地 C++ 程序 `services/algorithm_service/myprogram`。

## 当前总体架构

```text
前端 / 调用方
  |
  | HTTP
  v
api_main.py
  |
  | 构造 TaskRequest / ExecutionContext
  v
InputAgent
  |
  v
UnderstandingAgent        读取 data/requirement.xml 或请求指定 XML
  |
  v
DecomposeAgent            基于 ToolCapability 动态生成子任务 DAG
  |
  v
PlanningAgent             生成 execution_plan 和可解释并行批次
  |
  v
IntelligentScheduler      按依赖调度、并发执行、重试、失败路由和重规划
  |
  v
InvokerAgent
  |
  v
MCPWrapper                ExecutionContext + SubTask -> MCPRequest
  |
  v
AsyncHTTPClient           MCPRequest -> HTTP JSON POST
  |
  v
services/algorithm_service/app.py
  |
  | 返回 MCPResponse 风格 JSON
  v
IntelligentScheduler      保存 ToolResult 并追加执行轨迹
  |
  v
PostprocessAgent          本地虚警过滤 / QB 融合
  |
  v
ReportAgent               质量评估 + 最终报告
  |
  v
HTTP 响应 + outputs/report_*.json
```

## 服务入口

### 主调度 API：`api_main.py`

`api_main.py` 是当前项目的主入口，定义了 FastAPI 应用：

- `app = FastAPI(title="智能体多载荷调度中心 API")`
- `/api/v1/task/submit`：全域底图识别流水线。
- `/api/v1/task/slice_infer`：切片目标识别流水线。
- `build_registry()`：读取 `config.TOOL_SERVICE_MAP`，把工具名和工具能力注册到 `ToolRegistry`。

### 全域底图识别接口

```http
POST /api/v1/task/submit
```

请求体由 `PipelineRequest` 定义：

```json
{
  "task_id": "TASK_001",
  "tiff_path": "/app/data/sample_packet/base_map.tif",
  "requirement_xml_path": "/workspace/data/requirement.xml",
  "output_requirements": {
    "format": "json"
  }
}
```

处理流程：

1. 构造 `TaskRequest`。
2. 创建 `ExecutionContext`。
3. 创建 `ToolRegistry`。
4. 通过 `OrchestratorAgent` 统一执行输入校验、XML 理解、能力匹配拆解和可解释规划。
5. 通过 `IntelligentScheduler` 调用算法服务执行所有可调度子任务，并记录 trace/replan。
6. 执行 `PostprocessAgent` 和 `ReportAgent`。
7. 将报告写入 `outputs/report_{task_id}.json`。
8. 将最终 JSON 返回给前端。

返回结构：

```json
{
  "code": 200,
  "msg": "Pipeline executed successfully",
  "data": {
    "final_report": {},
    "quality_report": {},
    "orchestration": {
      "plan": [],
      "trace": [],
      "replan_events": [],
      "skipped": []
    }
  }
}
```

### 切片目标识别接口

```http
POST /api/v1/task/slice_infer
```

请求体由 `SliceRequest` 定义：

```json
{
  "pointPath": [
    "/app/data/slice_001.png",
    "/app/data/slice_002.png"
  ]
}
```

处理流程：

1. 构造一个内部 `TaskRequest`。
2. 读取默认 XML：`/workspace/data/requirement.xml`。
3. 强制设置 `context.parsed_requirement["detection_mode"] = "slice"`。
4. 把前端传入的切片路径挂载到 `slice_inputs.pointPathList`。
5. `DecomposeAgent` 生成 `SLICE_01` 子任务。
6. `IntelligentScheduler` 调用 `slice_detection_service`，实际请求 `http://127.0.0.1:8888/slice_infer`。
7. 本地后处理后返回目标列表，并写入 `outputs/report_slice.json`。

## 核心数据结构

核心数据结构定义在 `core/schema.py`。

### `TaskRequest`

表示一次总任务请求，主要字段包括：

- `task_id`：任务编号。
- `tiff_path`：底图路径。
- `requirement_xml_path`：XML 需求文件路径。
- `payload_types`：载荷类型，例如 `SAR`、`OPTICAL`、`ELINT`。
- `target_classes`：目标类别，例如 `plane`、`ship`、`vehicle`。
- `target_region`：目标区域。
- `output_requirements`：输出格式和置信度要求。

在 `/api/v1/task/submit` 中，`payload_types`、`target_classes`、`target_region` 通常先置空，再由 `UnderstandingAgent` 从 XML 中解析。

### `SubTask`

表示一个可调度子任务，主要字段包括：

- `subtask_id`：子任务编号，例如 `P1`、`P2`、`P3`、`D1`。
- `name`：人类可读名称。
- `tool_name`：要调用的工具服务名，例如 `geo_correction_service`。
- `dependencies`：依赖的前置子任务 ID。
- `parameters`：调用工具时附加的参数。
- `status`：任务状态，默认 `PENDING`。
- `retry_count`：当前重试次数。
- `max_retry`：最大重试次数，默认 `1`。

### `ToolResult`

表示一次工具调用的结果，由 `InvokerAgent` 根据 `MCPResponse` 转换而来：

- `subtask_id`
- `tool_name`
- `success`
- `output`
- `message`

说明：任务级 `confidence` 不是必填字段。当前预处理、几何校正和普通工具响应不会强制返回它；检测框自己的 `score` 或算法内部 `confidence` 保留在 `output.detections` 内。

### `ExecutionContext`

贯穿整条流水线的共享上下文。各个 Agent 不直接传一堆参数，而是读写同一个 `ExecutionContext`：

- `request`：原始 `TaskRequest`。
- `parsed_requirement`：XML 解析结果。
- `subtasks`：`DecomposeAgent` 生成的子任务列表。
- `execution_plan`：`PlanningAgent` 记录的执行计划。
- `plan_rationale`：按依赖层生成的可解释计划。
- `execution_trace`：调度器记录的结构化执行轨迹。
- `replan_events`：失败后的 retry/fallback/skip/fail 决策记录。
- `skipped_tools`：需求声明但未生成或被重规划跳过的工具。
- `tool_results`：所有工具调用结果，key 是 `subtask_id`。
- `final_report`：最终报告。
- `quality_report`：质量评估结果。
- `metadata`：输入校验、调度错误、重试、阻塞等辅助信息。

## Agent 流水线

### `agents/input_agent.py`

`InputAgent` 是输入校验阶段。它检查：

- `context.request.tiff_path` 是否存在。
- `context.request.requirement_xml_path` 是否存在。

检查结果写入 `context.metadata`：

- `tiff_exists`
- `requirement_xml_exists`
- `tiff_path`
- `requirement_xml_path`
- `input_stage = "validated"`

注意：当前实现是记录校验结果，不会因为文件不存在立即抛错；真正的算法服务调用阶段仍可能因为文件不存在返回失败。

### `agents/understanding_agent.py`

`UnderstandingAgent` 是需求理解阶段。它使用 `xml.etree.ElementTree` 解析 XML，并写入 `context.parsed_requirement`。

当前解析字段包括：

- `detection_mode`：识别模式，默认 `base_map`，切片模式为 `slice`。
- `slice_inputs`：切片模式参数。
- `input_files`：`SAR` 和 `OPTICAL` 输入文件路径。
- `task_type`
- `payload_types`
- `target_classes`
- `target_region`
- `slice_size`
- `tiff_path`
- `output_requirements`
- `constraints`

目标区域会经过 `normalize_target_region()` 校验，经度范围为 `[-180, 180]`，纬度范围为 `[-90, 90]`。

### `agents/decompose_agent.py`

`DecomposeAgent` 是任务拆解阶段。它读取 `ToolRegistry` 中的工具能力表，按 `payload_types`、`target_classes`、`detection_mode` 和输入文件动态生成子任务：

- 预处理能力：SAR 去噪、光学增强。
- 几何能力：几何精校正。
- 检测能力：SAR/OPTICAL 目标检测、ELINT 检测、切片检测。
- 缺少输入文件或能力不可用时，会写入 `context.skipped_tools`。

当前实现中，`context.subtasks` 包含预处理、几何校正和检测任务。后处理、融合和报告目前不是通过调度器中的 `F1/F2/R1` 子任务执行，而是在算法调用完成后由 `PostprocessAgent` 和 `ReportAgent` 本地执行。

### `agents/planning_agent.py`

`PlanningAgent` 当前是可解释规划阶段：

- 把所有 `SubTask.subtask_id` 写入 `context.execution_plan`。
- 按依赖关系生成可并行批次，写入 `context.plan_rationale`。
- 在 `context.metadata["planning_stage"]` 中记录 `dependency_graph_ready`。

当前它不调用大模型，也不做成本优化；真正的执行反馈、失败重试和重规划由 `IntelligentScheduler` 完成。

### `agents/invoker_agent.py`

`InvokerAgent` 是工具调用智能体，负责把子任务真正发给算法服务。

主要职责：

- 调用 `MCPWrapper.build_request()` 生成 `MCPRequest`。
- 从 `ToolRegistry` 查询 `subtask.tool_name` 对应的 HTTP URL。
- 使用 `AsyncHTTPClient.post_mcp()` 发起异步 HTTP 请求。
- 将 `MCPResponse` 转成 `ToolResult`。
- `invoke_many()` 支持并发执行多个 ready 子任务。

`output_schema()` 根据工具名返回期望输出字段，例如：

- `sar_denoise_service -> ["sar_denoised_path"]`
- `optical_enhance_service -> ["optical_enhanced_path"]`
- `geo_correction_service -> ["geo_corrected_path", "target_resolution"]`
- 检测类服务 -> `["detections"]`

### `agents/postprocess_agent.py`

`PostprocessAgent` 是本地后处理阶段：

- 从 `context.tool_results` 中汇总检测结果。
- 调用 `run_false_alarm_filter()` 做虚警过滤。
- 调用 `run_qb_fusion()` 做 QB 融合。
- 将结果写入 `context.metadata["fused_targets"]`。
- 将统计摘要写入 `context.metadata["postprocess_summary"]`。

当前 `services/postprocess_service/processor.py` 中的虚警过滤和 QB 融合实现比较轻量，主要用于打通流程。

### `agents/report_agent.py`

`ReportAgent` 是最终报告阶段：

- 调用 `build_final_report()` 生成最终业务报告。
- 调用 `_assess_quality()` 检查任务失败、阻塞、低置信度等问题。
- 把质量评估写入 `context.quality_report`。
- 把执行状态写入 `context.final_report["execution_status"]`。

`execution_status.tasks` 会列出每个子任务的状态、依赖、重试次数和错误信息。

## 智能调度中心

调度逻辑在 `scheduler/scheduler_center.py`。

### 调度规则

`IntelligentScheduler.run_async()` 循环执行：

1. 找出所有 `PENDING` 任务。
2. 通过 `_ready_tasks()` 找出依赖已经成功的任务。
3. 将 ready 任务标记为 `RUNNING`。
4. 调用 `InvokerAgent.invoke_many()` 并发执行。
5. 成功则标记为 `SUCCESS`。
6. 失败则调用 `ReplanDecisionAgent`，决定 retry、fallback、skip 或 fail。
7. 如果没有 ready 任务，则检查是否有依赖失败导致的 blocked 任务。
8. 若依赖失败，则通过 `_mark_blocked_tasks()` 标记 `BLOCKED`。
9. 若既没有 ready 也没有 blocked，则写入 `context.metadata["scheduler_error"]`。

### 状态定义

状态定义在 `core/enums.py` 的 `TaskStatus`：

- `PENDING`：等待执行。
- `RUNNING`：正在执行。
- `SUCCESS`：执行成功。
- `FAILED`：执行失败，且重试次数已用完。
- `BLOCKED`：依赖失败，当前任务无法继续执行。
- `SKIPPED`：可选任务失败后被规则型重规划跳过。

### 失败处理和重规划

当前失败处理是确定性的：

- 工具调用抛异常或返回 `success=False` 时，先重试。
- `SubTask.max_retry` 默认为 `1`，表示失败后最多再试一次。
- 重试仍失败后，如果存在已注册 fallback 工具，则切换工具并继续执行。
- 可选任务失败且无 fallback 时，标记为 `SKIPPED`，不阻塞整体流程。
- 必选任务失败且无 fallback 时，标记为 `FAILED`。
- 依赖失败的下游任务标记为 `BLOCKED`。
- ready、started、succeeded、retry、failed、skipped、blocked 会写入 `context.execution_trace` 和 `context.replan_events`。

## 任务拆解规则

当前主要拆解规则由 `agents/decompose_agent.py` 基于 `core/tool_capabilities.py` 的能力表完成。`core/router.py` 仍保留旧版规则函数作为参考，但主 API 链路不再依赖它生成任务。

### 预处理任务

预处理阶段根据 `payload_types`、`input_files`、`detection_mode` 匹配工具能力。

切片模式：

- 如果 `detection_mode == "slice"`，直接返回空列表，不生成预处理任务。

底图模式：

- 如果包含 `SAR` 且 XML 中提供了有效 `input_files.SAR`，生成：
  - `P1: sar_denoise_service`
- 如果包含 `OPTICAL` 且 XML 中提供了有效 `input_files.OPTICAL`，生成：
  - `P2: optical_enhance_service`
- 如果存在任意有效预处理任务，生成：
  - `P3: geo_correction_service`
  - `P3.dependencies = ["P1", "P2"]` 中实际存在的任务

### 检测任务

检测阶段根据识别模式、载荷类型和目标类型匹配工具能力。

切片模式：

```text
SLICE_01: slice_detection_service
```

底图模式：

- `SAR + plane -> D1: sar_plane_service`
- `SAR + ship -> D2: sar_ship_service`
- `SAR + vehicle -> D3: sar_vehicle_service`
- `OPTICAL + plane -> D4: optical_plane_service`
- `OPTICAL + ship -> D5: optical_ship_service`
- `OPTICAL + vehicle -> D6: optical_vehicle_service`
- `ELINT -> D7: elint_detection_service`

如果包含 `SAR` 或 `OPTICAL`，视觉检测任务依赖 `P3`；`ELINT` 当前不依赖几何校正，可以与预处理并行执行。

### 预留后处理任务

`build_postprocess_tasks()` 当前存在于 `core/router.py`，但 `DecomposeAgent` 没有使用它。后处理、融合、报告现在走本地 Agent：

```text
PostprocessAgent -> ReportAgent
```

因此当前调度器不会生成 `F1/F2/R1` 子任务。

## 当前默认 DAG 示例

当 XML 中包含：

```text
payload_types = SAR + OPTICAL + ELINT
target_classes = plane + ship + vehicle
detection_mode = base_map
```

并且 `input_files.SAR`、`input_files.OPTICAL` 都有效时，当前会生成：

```text
P1: sar_denoise_service
P2: optical_enhance_service
D7: elint_detection_service

P1 + P2
   |
   v
P3: geo_correction_service
   |
   v
D1: sar_plane_service
D2: sar_ship_service
D3: sar_vehicle_service
D4: optical_plane_service
D5: optical_ship_service
D6: optical_vehicle_service
```

调度执行特点：

- `P1`、`P2`、`D7` 可以并发执行。
- `P3` 等待 `P1` 和 `P2` 成功。
- `D1-D6` 等待 `P3` 成功。
- 所有算法任务完成后，`PostprocessAgent` 本地汇总和融合。
- 最后 `ReportAgent` 生成最终报告和质量评估。

## MCP 风格协议

本项目中的 MCP 是一套内部工具调用数据协议，定义在 `mcp/protocol.py`。它不等同于 stdio 进程通信；当前传输层是 HTTP。

### `MCPRequest`

调度器发给算法服务的请求结构：

```json
{
  "task_id": "TASK_001",
  "subtask_id": "D5",
  "tool_name": "optical_ship_service",
  "input_data": {
    "tiff_path": "/app/data/sample_packet/base_map.tif",
    "xml_config": {},
    "previous_results": {
      "P3": {
        "geo_corrected_path": "/app/data/sample_packet/geo_correction_xxx.tif"
      }
    },
    "metadata": {}
  },
  "parameters": {
    "mode": "base_map",
    "tiff_path": "/app/data/sample_packet/base_map.tif"
  },
  "output_schema": ["detections"]
}
```

### `MCPResponse`

算法服务返回给调度器的响应结构：

```json
{
  "subtask_id": "D5",
  "tool_name": "optical_ship_service",
  "success": true,
  "output": {
    "detections": []
  },
  "message": "success"
}
```

### 相关文件

- `mcp/protocol.py`：定义 `MCPRequest`、`MCPResponse`。
- `mcp/wrapper.py`：把 `ExecutionContext + SubTask` 转成 `MCPRequest`。
- `mcp/registry.py`：维护 `tool_name -> service_url` 映射。
- `clients/async_http_client.py`：把 `MCPRequest` 转成 HTTP JSON POST，并把响应解析成 `MCPResponse`。
- `clients/base_http_client.py`：同步 HTTP 客户端，当前主链路使用异步版本。

## 算法服务

算法服务入口是 `services/algorithm_service/app.py`，它也是一个 FastAPI 应用。

### `/infer`

统一处理底图识别相关工具：

- `sar_denoise_service`
- `optical_enhance_service`
- `geo_correction_service`
- `sar_plane_service`
- `sar_ship_service`
- `sar_vehicle_service`
- `optical_plane_service`
- `optical_ship_service`
- `optical_vehicle_service`
- `elint_detection_service`

处理逻辑：

- 预处理类工具调用 `run_local_preprocess_model()`。
- 视觉检测类工具调用 `call_specific_algorithm_docker()`。
- `elint_detection_service` 调用 `run_elint_detection()`。
- 最后通过 `build_mcp_response()` 统一封装成 MCPResponse 风格 JSON。

### `/slice_infer`

处理切片识别任务：

- 读取 `parameters.pointPathList`。
- 为每张切片生成检测结果。
- 返回 `detections`。

### 算法实现文件

- `services/algorithm_service/SAR_pro.py`：SAR 图像预处理算法，被 `sar_denoise_service` 使用。
- `services/algorithm_service/opt_pro.py`：光学图像增强算法，被 `optical_enhance_service` 使用。
- `services/algorithm_service/Optical_detection/infer_OPT_SLD.py`：光学目标检测入口，被光学检测工具调用。
- `services/algorithm_service/myprogram`：几何精校正 C++ 可执行程序，由 `geo_correction_service` 通过 `subprocess.run()` 调用。

## 配置

配置集中在 `config.py`。

主要配置：

- `TIFF_PATH`：默认底图路径。
- `REQUIREMENT_XML_PATH`：默认 XML 需求文件路径。
- `OUTPUT_REPORT_PATH`：默认报告路径。
- `HTTP_TIMEOUT`：HTTP 调用超时时间。
- `QUALITY_THRESHOLD`：质量评估置信度阈值。
- `ALGORITHM_URL`：底图算法服务地址，默认 `http://127.0.0.1:8888/infer`。
- `SLICE_ALGORITHM_URL`：切片算法服务地址，默认 `http://127.0.0.1:8888/slice_infer`。
- `TOOL_SERVICE_MAP`：工具名到算法服务 URL 的映射。

当前配置把大多数工具都映射到同一个算法服务 `/infer`，由算法服务内部根据 `tool_name` 分发到具体算法函数。

## 需求 XML

示例需求文件是 `data/requirement.xml`。当前 `UnderstandingAgent` 会读取如下结构：

```xml
<requirement>
  <task_type>multi_payload_detection</task_type>

  <payload_types>
    <type>SAR</type>
    <type>OPTICAL</type>
    <type>ELINT</type>
  </payload_types>

  <target_classes>
    <class>plane</class>
    <class>ship</class>
    <class>vehicle</class>
  </target_classes>

  <target_region>
    <lon>120.1</lon>
    <lat>30.2</lat>
    <radius_km>20</radius_km>
  </target_region>

  <input_files>
    <SAR>/app/data/sample_packet/input_sar.tif</SAR>
    <OPTICAL>/app/data/sample_packet/input_optical.tif</OPTICAL>
  </input_files>

  <output_requirements>
    <format>json</format>
    <need_suggestion>true</need_suggestion>
  </output_requirements>

  <constraints>
    <priority>normal</priority>
    <need_geo_correction>true</need_geo_correction>
  </constraints>
</requirement>
```

字段说明：

- `payload_types/type`：决定生成哪些载荷相关任务。
- `target_classes/class`：决定生成哪些目标检测任务。
- `input_files/SAR`：SAR 预处理输入。
- `input_files/OPTICAL`：光学增强输入。
- `detection_mode`：可选，默认 `base_map`，切片模式为 `slice`。
- `target_region`：用于电子侦察模拟和报告区域信息。

## 后处理与报告

后处理代码位于 `services/postprocess_service/processor.py`。

当前包含：

- `run_false_alarm_filter()`：从 `tool_results` 中提取所有 `detections`，当前默认直接放行。
- `run_qb_fusion()`：QB 融合，当前默认直接返回过滤后的检测结果。
- `build_final_report()`：生成最终报告结构。

`ReportAgent` 会在报告中追加 `execution_status`：

```json
{
  "execution_status": {
    "pass": true,
    "issues": [],
    "tasks": [
      {
        "subtask_id": "P1",
        "name": "SAR denoise",
        "tool_name": "sar_denoise_service",
        "status": "SUCCESS",
        "retry_count": 0,
        "dependencies": [],
        "message": ""
      }
    ]
  }
}
```

## 运行方式

### Docker Compose 推荐方式

当前 `docker-compose.yml` 启动一个容器 `multi_payload_app`，容器内会同时启动：

- 算法服务：`services/algorithm_service/app.py`，端口 `8888`。
- 主调度 API：`api_main.py`，容器端口 `9000`，宿主机映射为 `9011`。

启动：

```bash
docker compose up --build
```

访问：

```text
主调度 API: http://127.0.0.1:9011
算法服务:   http://127.0.0.1:8888
API 文档:   http://127.0.0.1:9011/docs
```

### 本地手动启动方式

安装依赖：

```bash
pip install -r requirements.txt
```

启动算法服务：

```bash
cd services/algorithm_service
python -m uvicorn app:app --host 0.0.0.0 --port 8888 --reload
```

另开终端，在项目根目录启动主调度 API：

```bash
python -m uvicorn api_main:app --host 0.0.0.0 --port 9000 --reload
```

此时主调度 API 地址为：

```text
http://127.0.0.1:9000
```

## 当前项目结构与文件作用

```text
multi_payload_mcp_scheduler/
  api_main.py
    FastAPI 主调度入口，定义任务提交接口和切片识别接口。

  config.py
    全局配置，包含默认路径、HTTP 超时、质量阈值、工具服务 URL 映射。

  requirements.txt
    Python 依赖。

  Dockerfile
    构建容器镜像时使用的基础 Dockerfile。

  docker-compose.yml
    当前推荐运行方式。一个容器内同时启动算法服务和主调度 API。

  README.md
    当前说明文档。

  core/
    __init__.py
      Python 包标记文件。

    schema.py
      定义 TaskRequest、SubTask、ToolResult、ExecutionContext。

    enums.py
      定义 PayloadType、TargetClass、TaskStatus 等枚举。

    tool_capabilities.py
      定义 ToolCapability 和默认工具能力表，供智能拆解和规划使用。

    router.py
      旧版规则路由函数，当前保留作兼容和参考。

  agents/
    __init__.py
      Python 包标记文件。

    input_agent.py
      输入校验 Agent，记录底图和 XML 是否存在。

    orchestrator_agent.py
      规则型编排 Agent，统一驱动输入校验、需求理解、能力拆解和规划。

    understanding_agent.py
      需求理解 Agent，解析 XML 并生成 parsed_requirement。

    decompose_agent.py
      任务拆解 Agent，基于工具能力表生成 SubTask 列表。

    planning_agent.py
      规划 Agent，当前记录 execution_plan 和 planning_stage。

    invoker_agent.py
      调用 Agent，将 SubTask 封装为 MCP 请求并调用 HTTP 工具服务。

    replan_agent.py
      规则型重规划 Agent，根据失败、重试、fallback、optional 生成决策。

    postprocess_agent.py
      后处理 Agent，执行本地虚警过滤和 QB 融合。

    report_agent.py
      报告 Agent，生成最终报告并追加质量评估和执行状态。

  scheduler/
    __init__.py
      Python 包标记文件。

    scheduler_center.py
      IntelligentScheduler，负责依赖检查、并发执行、轨迹记录、重试和重规划。

  mcp/
    __init__.py
      Python 包标记文件。

    protocol.py
      定义 MCPRequest 和 MCPResponse 数据结构。

    wrapper.py
      将 ExecutionContext 和 SubTask 转换为 MCPRequest。

    registry.py
      工具注册表，保存 tool_name 到 HTTP URL 的映射。

  clients/
    __init__.py
      Python 包标记文件。

    async_http_client.py
      异步 HTTP 客户端，当前主链路使用它调用算法服务。

    base_http_client.py
      同步 HTTP 客户端，保留给同步调用场景。

  services/
    algorithm_service/
      __init__.py
        Python 包标记文件。

      app.py
        算法服务 FastAPI 入口，提供 /infer 和 /slice_infer。

      SAR_pro.py
        SAR 去噪/预处理算法实现。

      opt_pro.py
        光学增强算法实现。

      myprogram
        几何精校正本地可执行程序。

      Optical_detection/infer_OPT_SLD.py
        光学目标检测算法入口。

    mock_all_service/
      app.py
        统一模拟工具服务，可用于调试 MCP 请求与响应协议。

    postprocess_service/
      __init__.py
        Python 包标记文件。

      processor.py
        本地后处理、QB 融合、最终报告构造函数。

  data/
    requirement.xml
      XML 任务需求示例。

    算法对接文档.md
      外部算法接口说明文档。

    sample_packet/
      示例数据、切片图片、检测结果样例。

  outputs/
    运行时输出目录，保存 report_{task_id}.json 和 report_slice.json。
```

## 当前实现边界

- 当前调度是基于 `ToolCapability` 的规则型智能编排，不调用大模型 API。
- 当前 MCP 是项目内部的请求/响应数据协议，传输层是 HTTP。
- 当前 `PlanningAgent` 生成可解释并行批次，但不做成本优化。
- 当前失败处理支持重试、可选任务跳过、阻塞和已注册 fallback 切换。
- 当前后处理没有作为 MCP 工具服务调度，而是在主流程本地执行。
- 当前 `mock_all_service` 存在，但默认 `config.py` 指向 `services/algorithm_service/app.py`。

这些边界也正是后续可继续增强的方向：成本感知规划、更多备用工具、后处理服务化、以及在不影响稳定性的前提下引入可选自然语言解释层。
