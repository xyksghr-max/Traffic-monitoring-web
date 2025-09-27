# 智慧交通监控算法服务（web-flask）

面向交通监控项目的算法端服务，负责从摄像头视频流中执行目标检测、危险驾驶分析，并通过 WebSocket/HTTP 接口把结果同步给前端与后端。本 README 总结模块定位、技术栈、接口约定以及搭建流程，便于后续完整实现。

## 核心职责
- 接收前端通过 WebSocket 发起的摄像头流请求，拉取 RTSP/本地视频并进行实时推理。
- 基于 YOLO 系列模型完成车辆、行人、交通设施等目标检测，并输出跟踪、群组聚类、风险等级等结构化数据。
- 将检测到的关键帧编码为 Base64，连同检测结果通过 `detection_result` 消息推送至前端，供前端落库、展示与预警。
- 对接多模态大模型（Qwen-VL）进行语义分析，判断危险驾驶类型，给出文字描述和置信度。
- 定期向前端推送摄像头状态消息（`camera_status`），并在异常情况下返回 `stream_stopped`/`error` 提示。
- 提供 `/api/health/health_check` 等基础 HTTP 接口，供运维与前端心跳检测。

## 目标技术栈
- **Runtime**: Python 3.11+，Flask 3.x（或基于 Quart/FastAPI 的 ASGI 版本，视性能需求可替换）。
- **视频处理**: OpenCV、ffmpeg-python、aiortc（可选，用于更优的流媒体处理）。
- **检测模型**: Ultralytics YOLO (v8/v11/v12)，可通过 `model_config.yaml` 切换模型、置信度阈值、NMS 参数。
- **多模态分析**: DashScope SDK 调用 Qwen-VL-Plus / Qwen-VL-Max，返回危险驾驶描述与风险等级。
- **工具链**: NumPy、Pillow、pydantic、uvicorn/gunicorn、Redis（可选，用作流状态缓存或任务队列）。

## 目录规划
初次克隆时目录为空，推荐按照下列结构实现，方便模块化开发：

```
web-flask/
├── app.py                      # Flask 入口，注册蓝图 / WebSocket 服务
├── config.py                   # 基础配置（端口、模型路径、阈值、FRAME_INTERVAL 等）
├── requirements.txt            # Python 依赖清单
├── model_config.yaml           # YOLO 模型与阈值配置
├── algo/
│   ├── rtsp_detect/
│   │   ├── video_stream.py     # 拉流、重连、帧缓存
│   │   ├── yolo_detector.py    # YOLO 推理封装
│   │   ├── tracker.py          # 多目标跟踪/ID 分配（可选）
│   │   ├── group_analyzer.py   # 交通群组识别、密度评估
│   │   └── websocket_util.py   # WebSocket 广播、消息格式
│   └── llm/
│       ├── dangerous_driving_detector.py # 调用 Qwen-VL 的封装
│       └── prompts.py          # 提示词模版
├── routes/
│   ├── health.py               # /api/health/health_check
│   ├── stream.py               # 若需要 HTTP 拉流/测试接口
│   └── ws.py                   # WebSocket 路由/事件处理
├── clients/
│   ├── backend_client.py       # 与 Spring Boot 后端交互（获取摄像头、上报结果等）
│   └── file_client.py          # 若需向文件服务上传截图
├── utils/
│   ├── logger.py               # 统一日志
│   ├── scheduler.py            # 定时任务、健康检测
│   └── response.py             # 返回体包装（code/msg/data）
├── weights/                    # YOLO 模型权重目录（.pt/.onnx）
├── temp/                       # 临时帧、缓存文件
└── README.md                   # 当前文档
```

可根据实际实现增减模块，但建议保持「推理 / 通信 / 配置」分层清晰。

## 环境准备
1. 安装 Python 3.11 及以上。
2. 创建虚拟环境并安装依赖：
   ```bash
   cd web-flask
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. 下载所需 YOLO 权重（例如 `yolov8n.pt`、`yolo11n.pt`），放入 `weights/`，并在 `model_config.yaml` 中配置。
4. 准备多模态模型调用所需的 API Key：
   - 系统变量 `DASHSCOPE_API_KEY`（已在当前机器配置）；
   - 如需走代理或不同区域，可在 `config.py` 中扩展。

## 配置说明
`config.py` 建议包含下列字段，供算法端灵活调整：
- `SERVER_HOST` / `SERVER_PORT`：默认 `0.0.0.0:5000`。
- `FRAME_INTERVAL`：推理间隔（单位：秒），项目需求默认 1.8 秒；检测到高风险时可通过 `ALERT_PAUSE_SECONDS` 延迟下一帧（默认 3 秒）。
- `MAX_CONCURRENT_STREAMS`：并发摄像头上限。
- `BACKEND_BASE_URL`：Spring Boot 服务地址（如 `http://localhost:9090/api`），用于获取摄像头列表、上报统计信息。
- `JWT_SECRET` / `JWT_HEADER`：若需要调用后端需要鉴权的接口，可复用前端登录后下发的 Token。
- `YOLO_MODEL_NAME`、`YOLO_CONFIDENCE`、`YOLO_IOU`、`TRACKER_TYPE` 等模型参数。
- `LLM_MODEL`、`LLM_TIMEOUT`、`LLM_MAX_RETRY`：多模态大模型调用设置。
- `WS_HEARTBEAT_SECONDS`：WebSocket 心跳/健康检测间隔。
- `SAVE_RAW_FRAMES`：是否落盘原始帧，用于离线复盘调试。

所有敏感配置（API Key/密钥）应通过环境变量加载，避免硬编码。

## 启动方式
开发阶段可直接运行 Flask 内置服务器：
```bash
python app.py
```
或使用生产部署方案：
```bash
# 例如基于 Hypercorn
hypercorn app:app --bind 0.0.0.0:5000
```
启动后默认暴露：
- HTTP: `http://localhost:5000/api/...`
- WebSocket: `ws://localhost:5000/ws`

前端 `.env` 已指向上述端口，保持一致即可。

## HTTP 接口约定
所有接口返回结构需与前端 Axios 拦截器一致：
```json
{
  "code": 200,
  "msg": "success",
  "data": { ... }
}
```
当前必须实现：
- `GET /api/health/health_check`
  - **响应**：`{"code":200,"msg":"OK","data":{"status":"UP","service":"algo","version":"1.0.0"}}`
  - 前端启动时会轮询，用于提示“算法服务正常/异常”。

可扩展的辅助接口（视需求实现）：
- `POST /api/test/single-detect`：上传单张图片返回检测结果，便于离线调试。
- `GET /api/streams`：查看当前运行的摄像头流状态。

## WebSocket 通信协议
前端与算法端的双向消息约定如下：

### 前端 → 算法端
| type            | 描述                     | data 字段示例 |
|-----------------|--------------------------|---------------|
| `start_stream`  | 请求启动摄像头推理       | `{ "cameraId": 1, "rtspUrl": "rtsp://...", "cameraName": "城市主干道" }` |
| `stop_stream`   | 停止某摄像头推理         | `{ "cameraId": 1 }` |
| `check_camera`  | 仅检测摄像头在线状态     | `{ "cameraId": 1, "rtspUrl": "rtsp://..." }` |
| `ping`          | 心跳包（由前端定时发送） | `{}` |

### 算法端 → 前端
| type                | 描述 | data 关键字段 |
|---------------------|------|---------------|
| `camera_status`     | 摄像头状态变更通知。`status`: 1-在线, 0-离线, 2-故障。 | `{ "cameraId":1, "status":1, "message":"拉流成功", "latencyMs":120 }` |
| `detection_result`  | 推理结果帧。 | `{ "cameraId":1, "frame":"data:image/jpeg;base64,...", "imageWidth":1920, "imageHeight":1080, "detectedObjects":[{"class":"car","confidence":0.94,"bbox":[120,220,360,540],"level":1}], "trafficGroups":[...], "dangerousDrivingResults":[{"type":"逆行","riskLevel":"high","confidence":0.92,"description":"检测到蓝色车辆逆行"}], "hasDangerousDriving":true, "maxRiskLevel":"high", "classColors":{"car":"#00FF6A"}, "trackingEnabled":true, "serverDrawEnabled":false, "processTime":0.38 }` |
| `stream_stopped`    | 推理任务结束/异常。 | `{ "cameraId":1, "reason":"RTSP reconnect failed" }` |
| `error`             | 其他错误提示。 | `{ "cameraId":1, "message":"模型加载失败" }` |
| `pong`              | 对心跳的响应。 | `{}` |

> **注意**：`frame` 字段需满足前端校验，可直接提供完整的 `data:image/jpeg;base64,...` 字符串。若算法端已在服务端绘制框体，可将图片写入 `frame` 并设置 `serverDrawEnabled=true`，前端便不会重复描框。

### 风险等级定义
- `none`：未检测到异常；
- `low`：轻微异常，建议观察；
- `medium`：存在可疑行为，建议预警；
- `high`：危险驾驶或重大事件，触发弹窗及短信模拟。

算法端应根据 YOLO + LLM 结果给出 `maxRiskLevel`、`dangerousDrivingResults`（数组，可包含 `type`、`description`、`riskLevel`、`confidence`、`evidence`），并在检测到高风险时暂停 `FRAME_INTERVAL` 指定时长后再继续推理。

## 与后端的交互
- **摄像头信息**：算法端可通过 Spring Boot 提供的 `/camera/{id}`、`/camera/page` 接口读取元数据，也可直接使用前端在 WebSocket 消息中携带的 `rtspUrl` 等信息。
- **状态回写**：前端在收到 `camera_status` 后会调用后端 `PUT /api/camera/{id}/status` 更新数据库，无需算法端直接调用。
- **检测记录**：前端在 `detection_result` 中检测到高风险时，会调用后端 `/api/detection/record` 保存记录。算法端只需确保消息体字段齐全、图像可用。
- **文件存储**：当前项目由后端本地存储 (`data/uploads`) 承担；若算法端需要上传原图，可复用 `LocalStorageService` 对应的 `/api/file/upload` 接口或自建 client。

## 开发建议
- **多进程/多线程**：YOLO 推理可使用独立线程池或异步队列，避免 WebSocket 事件阻塞。可结合 `asyncio` + `queue.Queue` + `ThreadPoolExecutor` 或 Celery/RQ。
- **重连机制**：对 RTSP 流实现指数退避重连；超过最大重试次数时发出 `camera_status` offline + `stream_stopped`。
- **资源监控**：建议在 `health_check` 中附带 GPU/CPU/内存占用、当前活跃流数量，用于前端仪表盘展示。
- **单元测试**：可使用假视频或图像片段编写回归测试，验证 YOLO 检测与 LLM 解析逻辑。

## TODO 列表
- [ ] 整理 `requirements.txt` 与基础脚手架（Flask App、蓝图、WebSocket Server）。
- [ ] 实现 RTSP 拉流与帧队列，支持 CPU/GPU 两种运行模式。
- [ ] 集成 YOLO 推理、交通目标过滤、群组检测算法（并查集/密度聚类）。
- [ ] 封装 Qwen-VL 请求与结果解析，支持多重重试与超时控制。
- [ ] 完成 WebSocket 消息分发、任务生命周期管理、日志记录。
- [ ] 提供单帧调试接口与示例脚本，便于模型验证。
- [ ] 撰写更多文档（接口示例、性能调优、部署流程）。

完成上述工作后，即可把算法端与现有前端/后端串联，实现“视觉检测 + 语义理解 + 实时预警”的完整闭环。
