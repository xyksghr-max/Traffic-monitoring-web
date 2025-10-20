# 一键启动脚本使用指南

## 📋 概述

本项目提供了一键启动脚本，可以快速启动所有流式处理服务，包括：
- Kafka + Zookeeper
- Redis
- Prometheus + Grafana
- Task Generator（任务生成器）
- LLM Scheduler（LLM 调度器）
- Result Aggregator（结果聚合器）
- Flask 应用（Kafka 流式模式）

---

## 🚀 快速开始

### Linux / macOS

```bash
# 启动所有服务
./scripts/start_all_streaming.sh

# 停止所有服务
./scripts/stop_all_streaming.sh
```

### Windows

```cmd
REM 启动所有服务
scripts\start_all_streaming.bat

REM 停止所有服务
scripts\stop_all_streaming.bat
```

---

## 📊 启动流程说明

### Step 1: 检查 Docker 环境
- 验证 Docker 和 Docker Compose 是否安装
- 确保 Docker 服务正在运行

### Step 2: 启动基础设施
使用 `docker-compose` 启动以下服务：
- **Kafka** (localhost:9092) - 消息队列
- **Zookeeper** (localhost:2181) - Kafka 协调服务
- **Redis** (localhost:6379) - 缓存和状态存储
- **Prometheus** (localhost:9100) - 监控指标收集
- **Grafana** (localhost:3100) - 数据可视化

### Step 3: 初始化 Kafka Topics
自动创建以下 Topics：
- `detection-results` - 检测结果
- `assessment-tasks` - 评估任务
- `risk-assessment-results` - 风险评估结果

### Step 4: 启动流式处理服务
按顺序启动 3 个独立的 Python 服务：

1. **Task Generator** - 消费 `detection-results`，生成 LLM 评估任务
2. **LLM Scheduler** - 消费 `assessment-tasks`，调度 LLM API 调用
3. **Result Aggregator** - 消费 `risk-assessment-results`，聚合结果

### Step 5: 启动 Flask 应用
以 Kafka 流式模式启动 Flask 应用，环境变量：
```bash
ALGO_ENABLE_KAFKA_STREAMING=true
```

### Step 6: 验证服务状态
等待所有服务完全启动（约 5 秒）

---

## 🔍 服务访问地址

启动成功后，可以访问以下地址：

| 服务 | 地址 | 说明 |
|------|------|------|
| **Flask 应用** | http://localhost:5000 | 主应用 WebSocket 接口 |
| **Prometheus 指标** | http://localhost:5000/metrics | 实时监控指标 |
| **Prometheus UI** | http://localhost:9100 | Prometheus 查询界面 |
| **Grafana** | http://localhost:3100 | 可视化仪表板 (admin/admin) |

---

## 📝 日志文件位置

所有服务的日志文件存储在 `logs/streaming/` 目录：

```
logs/streaming/
├── task_generator.log      # 任务生成器日志
├── scheduler.log            # LLM 调度器日志
├── result_aggregator.log    # 结果聚合器日志
└── flask_app.log            # Flask 应用日志
```

### 查看实时日志

**Linux/macOS:**
```bash
# 查看任务生成器日志
tail -f logs/streaming/task_generator.log

# 查看所有日志
tail -f logs/streaming/*.log
```

**Windows:**
```cmd
REM 使用记事本打开
notepad logs\streaming\task_generator.log

REM 或使用 PowerShell 实时查看
Get-Content logs\streaming\task_generator.log -Wait -Tail 50
```

---

## 🔧 进程管理

### Linux/macOS

PID 文件存储在 `logs/pids/` 目录：
```bash
# 查看进程 PID
cat logs/pids/task_generator.pid
cat logs/pids/scheduler.pid
cat logs/pids/result_aggregator.pid
cat logs/pids/flask_app.pid

# 手动停止某个服务
kill $(cat logs/pids/task_generator.pid)

# 查看进程状态
ps aux | grep python
```

### Windows

```cmd
REM 查看所有 Python 进程
tasklist | findstr python

REM 查看端口占用
netstat -ano | findstr :5000

REM 手动停止进程（根据 PID）
taskkill /PID <进程ID> /F
```

---

## 📊 验证服务运行状态

### 1. 检查 Docker 容器

```bash
docker ps
```

应该看到以下容器正在运行：
- kafka
- zookeeper
- redis
- prometheus
- grafana

### 2. 检查 Python 进程

**Linux/macOS:**
```bash
ps aux | grep start_
```

**Windows:**
```cmd
tasklist | findstr "Task Generator\|LLM Scheduler\|Result Aggregator\|Flask App"
```

### 3. 测试 Prometheus 指标

```bash
curl http://localhost:5000/metrics
```

应该看到类似输出：
```
# HELP detection_total Total number of detection frames processed
# TYPE detection_total counter
detection_total{camera_id="1",model_type="yolov8n"} 42.0

# HELP llm_requests_total Total number of LLM API requests
# TYPE llm_requests_total counter
llm_requests_total{model="qwen-vl-plus",api_key_id="key_1",status="success"} 15.0
```

### 4. 测试 Prometheus 查询

访问 http://localhost:9100，在查询框中输入：
```promql
rate(detection_total[1m])
```

如果有数据，说明指标记录正常。

---

## 🐛 故障排查

### 问题 1: Prometheus 指标没有数据

**症状：** 访问 `/metrics` 端点正常，但 Prometheus 查询 `rate(detection_total[1m])` 没有数据

**原因：** 没有推流或 `pipeline.py` 未调用 `record_detection()`

**解决方案：**
1. ✅ 已修复：`pipeline.py` 已添加 Prometheus 指标记录
2. 确保有摄像头推流：
   ```bash
   # 使用 WebSocket 启动检测
   # 前端发送 start_stream 消息
   ```
3. 检查日志：
   ```bash
   tail -f logs/streaming/flask_app.log | grep "record_detection"
   ```

### 问题 2: Kafka 启动失败

**症状：** `docker ps` 看不到 kafka 容器

**解决方案：**
```bash
# 查看 Docker 日志
docker logs kafka

# 重启基础设施
cd deployment
docker-compose -f docker-compose.infra.yml down
docker-compose -f docker-compose.infra.yml up -d
```

### 问题 3: Python 服务启动失败

**症状：** 脚本执行完成，但服务未运行

**解决方案：**
```bash
# 查看日志文件
tail -f logs/streaming/task_generator.log

# 手动启动测试
python scripts/start_task_generator.py
```

### 问题 4: 端口冲突

**症状：** `Address already in use` 错误

**解决方案：**
```bash
# Linux/macOS: 查找占用端口的进程
lsof -i :5000
kill -9 <PID>

# Windows: 查找并结束进程
netstat -ano | findstr :5000
taskkill /PID <PID> /F
```

---

## 🎯 使用示例

### 完整启动流程

```bash
# 1. 启动所有服务
./scripts/start_all_streaming.sh

# 2. 等待服务完全启动（约 15 秒）

# 3. 访问 Flask 应用
open http://localhost:5000

# 4. 连接 WebSocket 并推流
# （前端操作或使用测试脚本）

# 5. 查看实时指标
open http://localhost:5000/metrics

# 6. 在 Prometheus 中查询
open http://localhost:9100
# 查询: rate(detection_total[1m])
# 查询: llm_requests_total

# 7. 在 Grafana 中可视化
open http://localhost:3100
# 登录: admin/admin
```

### 测试流式管道

```bash
# 使用测试脚本发送模拟数据
python scripts/test_streaming_pipeline.py --mode e2e --duration 60

# 查看 Kafka 消息流
python scripts/test_streaming_pipeline.py --mode consumer --topic detection-results
```

---

## 📦 依赖要求

### 系统依赖
- **Docker** >= 20.10
- **Docker Compose** >= 1.29
- **Python** >= 3.8

### Python 依赖
```bash
# 安装流式处理依赖
pip install -r requirements-streaming.txt

# 或使用 uv（更快）
uv pip install -r requirements-streaming.txt
```

主要包含：
- `confluent-kafka` - Kafka Python 客户端
- `redis` - Redis Python 客户端
- `prometheus-client` - Prometheus 指标导出

---

## 🔄 更新和维护

### 更新依赖

```bash
# 拉取最新代码
git pull

# 更新 Python 依赖
pip install -r requirements-streaming.txt --upgrade

# 重启服务
./scripts/stop_all_streaming.sh
./scripts/start_all_streaming.sh
```

### 清理日志

```bash
# 清理所有日志文件
rm -rf logs/streaming/*.log

# 清理 PID 文件
rm -rf logs/pids/*.pid
```

### 重置 Kafka 数据

```bash
# 停止服务
./scripts/stop_all_streaming.sh

# 清理 Kafka 数据卷
docker volume rm deployment_kafka-data
docker volume rm deployment_zookeeper-data

# 重新启动
./scripts/start_all_streaming.sh
```

---

## 💡 最佳实践

### 1. 生产环境部署

- 使用独立的配置文件（非 localhost）
- 配置持久化存储卷
- 设置资源限制（CPU、内存）
- 配置日志轮转（logrotate）
- 使用进程管理器（systemd、supervisor）

### 2. 性能优化

```yaml
# config/kafka.yaml
kafka:
  producer:
    batch_size: 16384
    linger_ms: 10
    compression_type: 'lz4'
  
  consumer:
    fetch_min_bytes: 1024
    fetch_max_wait_ms: 500
```

### 3. 监控告警

在 Prometheus 中配置告警规则：

```yaml
# prometheus/alerts.yml
groups:
  - name: streaming_alerts
    rules:
      - alert: HighDetectionLatency
        expr: detection_latency_seconds > 2.0
        for: 5m
        annotations:
          summary: "检测延迟过高"
      
      - alert: KafkaConsumerLag
        expr: kafka_consumer_lag > 1000
        for: 5m
        annotations:
          summary: "Kafka 消费延迟过高"
```

---

## 📞 获取帮助

### 查看详细文档
- **Kafka 集成**: `KAFKA_INIT_ERROR_FIX.md`
- **Prometheus 指标**: `PROMETHEUS_NO_DATA_FIX.md`
- **全面检查报告**: `COMPREHENSIVE_CHECK_REPORT.md`

### 常见问题
- 所有已知问题和解决方案请参考 `docs/` 目录
- 查看 GitHub Issues 获取社区支持

---

## ✅ 总结

使用一键启动脚本，您可以：
- ✅ **快速启动** - 一条命令启动所有服务
- ✅ **自动配置** - 自动初始化 Kafka Topics
- ✅ **完整监控** - Prometheus + Grafana 开箱即用
- ✅ **生产就绪** - 包含日志管理和进程监控
- ✅ **跨平台** - 支持 Linux、macOS、Windows

**现在就开始使用吧！** 🎉

```bash
./scripts/start_all_streaming.sh
```
