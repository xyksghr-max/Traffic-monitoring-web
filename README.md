# Traffic Monitoring Algorithm Service

基于 Flask + YOLO + 多模态 LLM 的智慧交通监控算法服务，提供实时视频流检测、危险驾驶分析和 WebSocket 通信功能。

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1+-green.svg)](https://flask.palletsprojects.com/)
[![YOLO](https://img.shields.io/badge/YOLO-v8+-orange.svg)](https://ultralytics.com/)
[![License](https://img.shields.io/badge/License-MIT-red.svg)](LICENSE)

## 📖 项目概述

本项目是智慧交通监控系统的算法服务端，负责处理视频流的实时目标检测、交通行为分析和危险驾驶识别。通过 WebSocket 与前端进行实时通信，支持多路摄像头并发处理。

### 🚀 核心功能

- **实时目标检测**: 基于 YOLOv8 模型检测车辆、行人、交通标识等目标
- **多目标跟踪**: 支持 ByteTrack 等跟踪算法，提供目标 ID 和轨迹信息
- **群组分析**: 检测交通密集区域和车辆聚集情况
- **危险驾驶分析**: 集成阿里云通义千问 VL 模型进行语义分析
- **实时通信**: WebSocket 双向通信，支持摄像头状态监控和结果推送
- **健康监测**: HTTP 接口提供服务状态检查和系统监控

### 🛠 技术栈

- **后端框架**: Flask 3.1+ + Flask-Sock + Flask-CORS
- **AI 模型**: Ultralytics YOLOv8 + 阿里云通义千问 VL
- **图像处理**: OpenCV + NumPy + Pillow
- **异步处理**: 多线程 + WebSocket
- **配置管理**: Pydantic Settings + YAML
- **日志系统**: Loguru
- **部署工具**: Gunicorn + Uvicorn

## 📁 项目结构

```
Traffic-monitoring-web/
├── app.py                      # Flask 应用入口文件
├── config.py                   # 应用配置和环境变量管理
├── main.py                     # 主程序启动入口
├── model_config.yaml           # YOLO 模型和推理参数配置
├── pyproject.toml              # 项目依赖和构建配置
├── requirements.txt            # Python 依赖清单 (uv 生成)
├── yolov8n.pt                 # YOLO v8 nano 模型权重文件
│
├── algo/                       # 核心算法模块
│   ├── llm/                   # 大语言模型相关
│   │   ├── dangerous_driving_detector.py  # 危险驾驶检测器
│   │   └── prompts.py         # LLM 提示词模板
│   └── rtsp_detect/           # 视频流检测模块
│       ├── group_analyzer.py  # 交通群组分析
│       ├── pipeline.py        # 检测流水线
│       ├── session_manager.py # 会话管理
│       ├── video_stream.py    # 视频流处理
│       └── yolo_detector.py   # YOLO 目标检测
│
├── routes/                     # API 路由模块
│   ├── health.py              # 健康检查接口
│   └── ws.py                  # WebSocket 路由
│
├── utils/                      # 工具模块
│   ├── image.py               # 图像处理工具
│   ├── logger.py              # 日志配置
│   └── response.py            # 响应格式化
│
├── clients/                    # 外部服务客户端
│
└── test_*.py                  # 测试文件
```

## ⚡ 快速开始

### 系统要求

- Python 3.10 或更高版本
- 8GB+ 内存推荐
- CUDA 支持 (可选，用于 GPU 加速)

### 1. 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd Traffic-monitoring-web

# 创建虚拟环境 (推荐使用 uv)
pip install uv
uv venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# 安装依赖
uv pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件或设置系统环境变量：

```bash
# 阿里云通义千问 API Key (必需)
DASHSCOPE_API_KEY=your-dashscope-api-key

# 可选配置
ALGO_SERVER_HOST=0.0.0.0
ALGO_SERVER_PORT=5000
ALGO_FRAME_INTERVAL=1.8
ALGO_BACKEND_BASE_URL=http://localhost:9090/api
```

### 3. 启动服务

```bash
# 开发模式启动
python main.py

# 或使用 Flask 开发服务器
python app.py

# 生产环境部署
gunicorn -w 4 -b 0.0.0.0:5000 --worker-class gevent app:app
```

服务启动后：
- HTTP API: `http://localhost:5000/api`
- WebSocket: `ws://localhost:5000/ws`

### 4. 验证服务

运行测试脚本验证服务状态：

```bash
python test_endpoints.py
```

## 📋 配置说明

### 模型配置 (model_config.yaml)

```yaml
model:
  name: yolov8n.pt           # 模型文件名
  device: cpu                # 设备: cpu/cuda/mps
  confidence_threshold: 0.35 # 置信度阈值
  iou_threshold: 0.50       # NMS IoU 阈值
  
tracking:
  enabled: true             # 启用目标跟踪
  tracker: bytetrack        # 跟踪算法
  
llm:
  enabled: true             # 启用 LLM 分析
  risk_threshold:
    low: 0.45              # 低风险阈值
    medium: 0.65           # 中风险阈值
    high: 0.80             # 高风险阈值
```

### 应用配置 (config.py)

主要配置项通过环境变量控制：

- `ALGO_SERVER_HOST`: 服务绑定主机 (默认: 0.0.0.0)
- `ALGO_SERVER_PORT`: 服务端口 (默认: 5000)
- `ALGO_FRAME_INTERVAL`: 检测间隔秒数 (默认: 1.8)
- `ALGO_ALERT_PAUSE_SECONDS`: 高风险检测后暂停时间 (默认: 3.0)

## 🔌 API 接口

### HTTP 接口

所有 HTTP 接口遵循统一的响应格式：

```json
{
  "code": 200,
  "msg": "success", 
  "data": { ... }
}
```

#### GET /api/health/health_check

健康检查接口，返回服务状态信息。

**响应示例:**
```json
{
  "code": 200,
  "msg": "OK",
  "data": {
    "status": "UP",
    "service": "algo",
    "version": "1.0.0"
  }
}
```

### WebSocket 接口

WebSocket 连接地址: `ws://localhost:5000/ws`

#### 客户端发送消息格式

| 消息类型 | 描述 | 数据字段 |
|---------|------|----------|
| `start_stream` | 启动视频流检测 | `cameraId`, `rtspUrl`, `cameraName` |
| `stop_stream` | 停止视频流检测 | `cameraId` |
| `check_camera` | 检查摄像头状态 | `cameraId`, `rtspUrl` |
| `ping` | 心跳检测 | 无 |

**示例:**
```json
{
  "type": "start_stream",
  "data": {
    "cameraId": 1,
    "rtspUrl": "rtsp://example.com/stream",
    "cameraName": "主干道摄像头"
  }
}
```

#### 服务端推送消息格式

| 消息类型 | 描述 | 关键字段 |
|---------|------|----------|
| `camera_status` | 摄像头状态更新 | `cameraId`, `status`, `message` |
| `detection_result` | 检测结果 | `cameraId`, `frame`, `detectedObjects` |
| `stream_stopped` | 流停止通知 | `cameraId`, `reason` |
| `error` | 错误消息 | `cameraId`, `message` |
| `pong` | 心跳响应 | 无 |

**检测结果示例:**
```json
{
  "type": "detection_result",
  "data": {
    "cameraId": 1,
    "frame": "data:image/jpeg;base64,...",
    "imageWidth": 1920,
    "imageHeight": 1080,
    "detectedObjects": [
      {
        "class": "car",
        "confidence": 0.94,
        "bbox": [120, 220, 360, 540],
        "trackId": 1,
        "level": 1
      }
    ],
    "trafficGroups": [...],
    "dangerousDrivingResults": [
      {
        "type": "逆行",
        "riskLevel": "high", 
        "confidence": 0.92,
        "description": "检测到蓝色车辆逆行"
      }
    ],
    "hasDangerousDriving": true,
    "maxRiskLevel": "high",
    "processTime": 0.38
  }
}
```

#### 风险等级定义

- `none`: 未检测到异常
- `low`: 轻微异常，建议观察  
- `medium`: 存在可疑行为，建议预警
- `high`: 危险驾驶或重大事件，触发警报

## 🧪 开发指南

### 本地开发

1. **启动开发服务器**:
   ```bash
   python main.py
   ```

2. **运行测试**:
   ```bash
   # 基础接口测试
   python test_endpoints.py
   
   # YOLO 模型测试
   python test_stream_detection.py
   
   # 大模型接口测试  
   python test_qwen_vl_plus.py
   ```

3. **代码热重载**:
   ```bash
   # 使用 Flask 开发模式
   export FLASK_ENV=development
   python app.py
   ```

### 添加新功能

1. **添加新的检测算法**:
   - 在 `algo/rtsp_detect/` 下创建新模块
   - 实现检测接口，返回标准格式结果
   - 在 `pipeline.py` 中集成新算法

2. **扩展 WebSocket 消息类型**:
   - 在 `routes/ws.py` 中添加消息处理函数
   - 更新消息路由表
   - 添加相应的测试用例

3. **添加新的 HTTP 接口**:
   - 在 `routes/` 下创建新的蓝图
   - 在 `app.py` 中注册蓝图
   - 遵循统一的响应格式

### 调试技巧

1. **日志查看**:
   ```bash
   # 启用详细日志
   export ALGO_LOG_LEVEL=DEBUG
   python main.py
   ```

2. **模型性能调优**:
   - 调整 `model_config.yaml` 中的阈值参数
   - 使用不同的 YOLO 模型规格 (n/s/m/l/x)
   - 启用 GPU 加速 (设置 `device: cuda`)

3. **内存监控**:
   ```bash
   # 监控资源使用
   pip install memory-profiler
   python -m memory_profiler main.py
   ```

## 🚀 部署

### Docker 部署 (推荐)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
```

### 系统服务部署

1. **创建系统服务文件**:
   ```ini
   [Unit]
   Description=Traffic Monitoring Algorithm Service
   After=network.target

   [Service]
   Type=simple
   User=www-data
   WorkingDirectory=/path/to/app
   Environment=PATH=/path/to/venv/bin
   ExecStart=/path/to/venv/bin/gunicorn -w 4 -b 0.0.0.0:5000 app:app
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

2. **启动服务**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable traffic-algo
   sudo systemctl start traffic-algo
   ```

### Nginx 反向代理

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 📊 性能优化

### 模型优化

1. **使用量化模型**:
   ```yaml
   model:
     half_precision: true  # 启用 FP16
   ```

2. **批处理推理**:
   ```python
   # 在 yolo_detector.py 中实现批量推理
   results = model(frames, batch_size=4)
   ```

3. **模型缓存**:
   ```python
   # 预加载模型到内存
   model.warmup(imgsz=(1, 3, 640, 640))
   ```

### 系统优化

1. **多进程部署**:
   ```bash
   gunicorn -w 4 --worker-class gevent app:app
   ```

2. **内存池管理**:
   ```python
   # 使用对象池减少内存分配
   from multiprocessing import Pool
   ```

3. **异步处理**:
   ```python
   # 异步处理视频帧
   import asyncio
   import concurrent.futures
   ```

## 🔧 故障排除

### 常见问题

1. **模型加载失败**:
   ```bash
   # 检查模型文件是否存在
   ls -la yolov8n.pt
   
   # 重新下载模型
   python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
   ```

2. **CUDA 不可用**:
   ```bash
   # 检查 CUDA 安装
   nvidia-smi
   
   # 安装 PyTorch CUDA 版本
   pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
   ```

3. **WebSocket 连接失败**:
   ```bash
   # 检查端口占用
   netstat -an | grep :5000
   
   # 检查防火墙设置
   sudo ufw allow 5000
   ```

### 日志分析

```bash
# 查看应用日志
tail -f /var/log/traffic-algo.log

# 检查系统资源
htop
nvidia-smi

# 网络连接状态
ss -tulpn | grep :5000
```

## 🤝 贡献指南

1. **Fork 项目并创建分支**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **遵循代码规范**:
   ```bash
   # 安装开发依赖
   pip install black flake8 pytest
   
   # 代码格式化
   black .
   
   # 代码检查
   flake8 .
   ```

3. **编写测试**:
   ```bash
   # 运行测试
   pytest tests/
   
   # 覆盖率报告
   pytest --cov=. tests/
   ```

4. **提交变更**:
   ```bash
   git add .
   git commit -m "feat: add new feature"
   git push origin feature/your-feature-name
   ```

## 📝 更新日志

### v1.0.0 (2024-12-28)
- ✨ 初始版本发布
- 🚀 集成 YOLOv8 目标检测
- 🧠 集成通义千问 VL 多模态分析
- 🔌 WebSocket 实时通信
- 📊 健康检查和监控接口

## 📄 许可证

本项目基于 MIT 许可证开源 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 📞 联系方式

如有问题或建议，请通过以下方式联系：

- 🐛 问题反馈: [GitHub Issues](https://github.com/xyksghr-max/Traffic-monitoring-web/issues)
- 📧 邮件联系: your-email@example.com
- 📖 文档Wiki: [项目文档](https://github.com/xyksghr-max/Traffic-monitoring-web/wiki)

---

⭐ 如果这个项目对你有帮助，请给个 Star 支持一下！