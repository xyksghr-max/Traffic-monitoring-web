# Windows 平台 Kafka 流式处理模式启动指南

## 📋 前置要求

### 1. 安装 Docker Desktop for Windows

Kafka 和 Redis 需要通过 Docker 运行。

1. 下载并安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)
2. 启动 Docker Desktop
3. 确保 WSL2 已启用（推荐）

验证 Docker 安装：
```powershell
docker --version
docker-compose --version
```

### 2. Python 环境

```powershell
# 确认 Python 版本
python --version  # 应该是 3.10+

# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt
pip install -r requirements-streaming.txt
```

---

## 🚀 完整启动流程

### 步骤 1: 启动基础设施 (Kafka + Redis + Prometheus + Grafana)

```powershell
# 切换到部署目录
cd deployment

# 启动所有基础设施
docker-compose -f docker-compose.infra.yml up -d

# 检查服务状态
docker-compose -f docker-compose.infra.yml ps
```

**预期输出**:
```
NAME                    STATUS          PORTS
traffic-kafka           running         0.0.0.0:9092->9092/tcp
traffic-zookeeper       running         0.0.0.0:2181->2181/tcp
traffic-redis           running         0.0.0.0:6379->6379/tcp
traffic-prometheus      running         0.0.0.0:9100->9090/tcp
traffic-grafana         running         0.0.0.0:3100->3000/tcp
traffic-kafka-ui        running         0.0.0.0:8080->8080/tcp
```

### 步骤 2: 初始化 Kafka Topics

```powershell
# 返回项目根目录
cd ..

# 初始化 Topics
python scripts\init_kafka_topics.py
```

**预期输出**:
```
✓ Topic 'detection-results' created (16 partitions)
✓ Topic 'assessment-tasks' created (16 partitions)
✓ Topic 'risk-assessment-results' created (16 partitions)
```

### 步骤 3: 配置 API Keys

编辑 `config\api_keys.yaml`，添加至少 3 个有效的 API Key：

```yaml
api_keys:
  - id: key-001
    api_key: "sk-xxxxxxxxxxxxxxxx"  # 你的真实 API Key
    priority: 1
    qps_limit: 10
    rpm_limit: 600
    
  - id: key-002
    api_key: "sk-yyyyyyyyyyyyyyyy"
    priority: 1
    qps_limit: 10
    rpm_limit: 600
    
  - id: key-003
    api_key: "sk-zzzzzzzzzzzzzzzz"
    priority: 1
    qps_limit: 10
    rpm_limit: 600
```

验证 API Keys：
```powershell
python scripts\verify_api_keys.py
```

### 步骤 4: 启动流处理服务

#### 方式 1: 使用 PowerShell 脚本（推荐）

```powershell
.\scripts\start_streaming_services.ps1
```

#### 方式 2: 使用批处理脚本

```cmd
scripts\start_streaming_services.bat
```

#### 方式 3: 手动逐个启动（调试用）

**打开 3 个独立的 PowerShell 窗口**:

**窗口 1 - 任务生成器**:
```powershell
.\.venv\Scripts\Activate.ps1
python scripts\start_task_generator.py
```

**窗口 2 - LLM 调度器**:
```powershell
.\.venv\Scripts\Activate.ps1
python scripts\start_scheduler.py
```

**窗口 3 - 结果聚合器**:
```powershell
.\.venv\Scripts\Activate.ps1
python scripts\start_result_aggregator.py
```

### 步骤 5: 启用 Kafka 模式并启动 Flask 应用

**新建 PowerShell 窗口**:

```powershell
# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 设置环境变量启用 Kafka
$env:ALGO_ENABLE_KAFKA_STREAMING="true"
$env:ALGO_KAFKA_BOOTSTRAP_SERVERS="localhost:9092"

# 启动 Flask 应用
python app.py
```

---

## ✅ 验证服务运行

### 1. 检查 Docker 容器

```powershell
docker ps
```

应该看到 6 个容器在运行：
- traffic-kafka
- traffic-zookeeper
- traffic-redis
- traffic-kafka-ui
- traffic-prometheus
- traffic-grafana

### 2. 检查流处理服务

```powershell
# 检查日志
Get-Content logs\streaming\task_generator.log -Tail 10
Get-Content logs\streaming\scheduler.log -Tail 10
Get-Content logs\streaming\aggregator.log -Tail 10
```

### 3. 访问管理界面

- **Kafka UI**: http://localhost:8080
- **Prometheus**: http://localhost:9100
- **Grafana**: http://localhost:3100 (admin/admin)
- **Flask 应用**: http://localhost:5000

### 4. 测试端到端流程

```powershell
python scripts\test_streaming_pipeline.py --mode e2e --duration 30
```

---

## 🔧 常见问题

### Q1: Docker Desktop 启动失败

**症状**: "Docker Desktop is not running"

**解决方案**:
1. 确保已安装 WSL2
   ```powershell
   wsl --install
   wsl --set-default-version 2
   ```
2. 在 Docker Desktop 设置中启用 WSL2 引擎
3. 重启 Docker Desktop

### Q2: 端口被占用

**症状**: "port is already allocated"

**解决方案**:
```powershell
# 检查端口占用
netstat -ano | findstr :9092
netstat -ano | findstr :6379

# 停止占用端口的进程或修改 docker-compose.infra.yml 中的端口映射
```

### Q3: Kafka 连接失败

**症状**: "Failed to connect to Kafka"

**解决方案**:
```powershell
# 检查 Kafka 是否运行
docker logs traffic-kafka

# 重启 Kafka
cd deployment
docker-compose -f docker-compose.infra.yml restart kafka
```

### Q4: 流处理服务启动失败

**症状**: "Failed to initialize Kafka Consumer"

**解决方案**:
```powershell
# 1. 确保 Kafka 已运行
docker ps | findstr kafka

# 2. 确保 Topics 已创建
python scripts\init_kafka_topics.py

# 3. 查看详细错误日志
Get-Content logs\streaming\*.log | Select-String "ERROR"
```

### Q5: API Key 验证失败

**症状**: "API key is invalid"

**解决方案**:
1. 确保 `DASHSCOPE_API_KEY` 环境变量已设置
   ```powershell
   $env:DASHSCOPE_API_KEY="sk-xxxxxxxx"
   ```
2. 或在 `config\api_keys.yaml` 中配置有效的 API Keys

---

## 🛑 停止服务

### 停止流处理服务

```powershell
.\scripts\stop_streaming_services.ps1
```

### 停止 Flask 应用

在运行 `python app.py` 的窗口中按 `Ctrl+C`

### 停止基础设施

```powershell
cd deployment
docker-compose -f docker-compose.infra.yml down
```

**保留数据**（仅停止容器）:
```powershell
docker-compose -f docker-compose.infra.yml stop
```

**清除所有数据**（删除容器和卷）:
```powershell
docker-compose -f docker-compose.infra.yml down -v
```

---

## 📊 监控和日志

### 查看实时日志

```powershell
# 任务生成器
Get-Content logs\streaming\task_generator.log -Tail 50 -Wait

# LLM 调度器
Get-Content logs\streaming\scheduler.log -Tail 50 -Wait

# 结果聚合器
Get-Content logs\streaming\aggregator.log -Tail 50 -Wait
```

### 查看 Docker 日志

```powershell
# Kafka
docker logs traffic-kafka -f

# Redis
docker logs traffic-redis -f

# Prometheus
docker logs traffic-prometheus -f
```

### Prometheus 查询

访问 http://localhost:9100/graph，执行查询：

```promql
# 检测吞吐量
rate(detection_total[1m])

# LLM 延迟
histogram_quantile(0.95, rate(llm_latency_seconds_bucket[5m]))

# API Key 成功率
api_key_success_rate
```

---

## 🎯 性能优化建议

### 1. 增加并发数

编辑 `config\kafka.yaml`:
```yaml
scheduler:
  max_concurrent_tasks: 100  # 默认 50
```

### 2. 调整 Docker 资源

在 Docker Desktop 设置中：
- **Memory**: 至少 8GB
- **CPUs**: 至少 4 核
- **Swap**: 2GB

### 3. 使用 SSD

确保 Docker 数据目录在 SSD 上以提高性能。

---

## 📝 环境变量完整列表

创建 `.env` 文件（可选）:

```env
# Flask 应用
ALGO_SERVER_HOST=0.0.0.0
ALGO_SERVER_PORT=5000

# Kafka 模式
ALGO_ENABLE_KAFKA_STREAMING=true
ALGO_KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# API Key（如果不使用 config/api_keys.yaml）
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx

# 其他配置
ALGO_FRAME_INTERVAL=1.8
ALGO_ALERT_PAUSE_SECONDS=3.0
```

加载 `.env` 文件：
```powershell
# PowerShell
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.+)$') {
        [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
}

# 或使用 python-dotenv
pip install python-dotenv
# 在 app.py 开头添加:
# from dotenv import load_dotenv
# load_dotenv()
```

---

## 🎓 快速命令参考

```powershell
# 一键启动完整流程
cd deployment && docker-compose -f docker-compose.infra.yml up -d && cd ..
python scripts\init_kafka_topics.py
.\scripts\start_streaming_services.ps1
$env:ALGO_ENABLE_KAFKA_STREAMING="true"
python app.py

# 一键停止
.\scripts\stop_streaming_services.ps1
cd deployment && docker-compose -f docker-compose.infra.yml down && cd ..

# 重启服务
.\scripts\stop_streaming_services.ps1
.\scripts\start_streaming_services.ps1

# 查看状态
docker ps
Get-Process | Where-Object {$_.ProcessName -like "*python*"}
```

---

## 📚 相关文档

- [KAFKA_INTEGRATION_GUIDE.md](KAFKA_INTEGRATION_GUIDE.md) - Kafka 集成详细指南
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - 通用部署指南
- [KAFKA_CONFIG_FIX.md](KAFKA_CONFIG_FIX.md) - 常见问题修复
- [PORT_CHANGE_NOTICE.md](PORT_CHANGE_NOTICE.md) - 端口配置说明

---

**祝您使用顺利！** 🚀

如遇问题，请查看日志或提交 Issue。
