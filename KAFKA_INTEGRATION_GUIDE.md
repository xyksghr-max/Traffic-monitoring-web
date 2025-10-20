# Kafka 流式处理集成指南

## 概述

本指南说明如何启用 Kafka 流式处理模式，实现检测和 LLM 分析的异步解耦。

---

## 🎯 核心改进

### 原有架构
```
摄像头 → YOLO检测 → BX聚类 → [同步调用LLM] → WebSocket推送
                                   ⬆
                              阻塞主线程 (3-5秒)
```

### 新架构（Kafka 模式）
```
摄像头 → YOLO检测 → BX聚类 ──┬─→ WebSocket推送（实时）
                            │
                            └─→ Kafka Producer ──→ Kafka ──→ Task Generator
                                                                    ↓
                                            Result Aggregator ←── LLM Scheduler
                                                    ↓
                                            Redis缓存 + WebSocket推送
```

**优势**：
- ✅ 检测和 LLM 分析解耦，检测结果实时返回
- ✅ LLM 分析异步处理，不阻塞主线程
- ✅ 支持 50+ 路摄像头并发处理
- ✅ API Key 池化，突破单 Key QPS 限制

---

## 🚀 启用 Kafka 流式处理

### 方法 1: 环境变量（推荐生产环境）

```bash
# .env 文件
ALGO_ENABLE_KAFKA_STREAMING=true
ALGO_KAFKA_BOOTSTRAP_SERVERS=localhost:9092
```

### 方法 2: 直接修改代码

编辑 `config.py`:

```python
enable_kafka_streaming: bool = Field(True, description="Enable Kafka streaming for async LLM processing")
kafka_bootstrap_servers: str = Field("kafka-broker:9092", description="Kafka broker addresses")
```

---

## 📋 部署步骤

### 1. 启动基础设施

```bash
# Linux/macOS
cd deployment
docker-compose -f docker-compose.infra.yml up -d

# 检查服务状态
docker-compose -f docker-compose.infra.yml ps
```

**验证**:
- Kafka: http://localhost:9092
- Kafka UI: http://localhost:8080
- Redis: localhost:6379
- Prometheus: http://localhost:9100
- Grafana: http://localhost:3100

### 2. 初始化 Kafka Topics

```bash
python scripts/init_kafka_topics.py
```

输出示例:
```
✓ Topic 'detection-results' created (16 partitions)
✓ Topic 'assessment-tasks' created (16 partitions)
✓ Topic 'risk-assessment-results' created (16 partitions)
```

### 3. 验证 API Keys

```bash
python scripts/verify_api_keys.py
```

确保 `config/api_keys.yaml` 中至少配置了 3 个可用的 API Key。

### 4. 启动流处理服务

#### Linux/macOS
```bash
chmod +x scripts/start_streaming_services.sh
./scripts/start_streaming_services.sh
```

#### Windows (命令提示符)
```cmd
scripts\start_streaming_services.bat
```

#### Windows (PowerShell)
```powershell
.\scripts\start_streaming_services.ps1
```

**服务说明**:
1. **Task Generator** - 消费检测结果，生成评估任务
2. **LLM Scheduler** - 并发调用 LLM API（最多 50 个任务）
3. **Result Aggregator** - 聚合结果，缓存到 Redis，推送 WebSocket

### 5. 启动检测服务

```bash
# 启用 Kafka 模式
export ALGO_ENABLE_KAFKA_STREAMING=true
python app.py
```

---

## 📊 监控和观测

### 查看日志

#### Linux/macOS
```bash
# 实时查看所有日志
tail -f logs/streaming/*.log

# 查看特定服务日志
tail -f logs/streaming/scheduler.log
```

#### Windows (PowerShell)
```powershell
Get-Content logs\streaming\scheduler.log -Tail 50 -Wait
```

### Prometheus 指标

访问 http://localhost:9100/graph 查看指标：

```promql
# 检测吞吐量
rate(detection_total[1m])

# LLM 延迟 (P95)
histogram_quantile(0.95, rate(llm_latency_seconds_bucket[5m]))

# API Key 成功率
api_key_success_rate

# Kafka 消费延迟
kafka_consumer_lag
```

### Grafana 仪表盘

1. 访问 http://localhost:3100
2. 默认账号: `admin` / `admin`
3. 导入仪表盘配置（待创建）

---

## 🔧 运行模式对比

### 模式 1: 传统同步模式（默认）

```python
# config.py
enable_kafka_streaming: bool = Field(False, ...)
```

**特点**:
- LLM 分析在主线程中同步执行
- 每次检测等待 LLM 完成（3-5 秒）
- 适合 1-5 路摄像头
- 无需额外基础设施

**优势**: 部署简单，无依赖  
**劣势**: 吞吐量低，延迟高

---

### 模式 2: Kafka 异步流式处理

```python
# config.py
enable_kafka_streaming: bool = Field(True, ...)
```

**特点**:
- 检测结果立即返回（<1 秒）
- LLM 分析异步处理
- 结果通过 Redis + WebSocket 推送
- 支持 50+ 路摄像头并发

**优势**: 高吞吐量，低延迟，高可用  
**劣势**: 需要 Kafka、Redis 等基础设施

---

## 🧪 测试验证

### 端到端测试

```bash
# 运行完整测试（60 秒）
python scripts/test_streaming_pipeline.py --mode e2e --duration 60

# 仅测试生产者
python scripts/test_streaming_pipeline.py --mode producer --count 10

# 仅测试消费者
python scripts/test_streaming_pipeline.py --mode consumer --timeout 30
```

### 性能基准测试

```bash
# 模拟 50 路摄像头，每路 2 FPS
# 预期 LLM 吞吐量: 50-100 QPS
# 预期端到端延迟: <2 秒 (P95)
```

---

## 🛠️ 故障排查

### Kafka 连接失败

**现象**: `Failed to connect to Kafka`

**解决方案**:
```bash
# 检查 Kafka 是否运行
docker ps | grep kafka

# 检查端口是否开放
nc -zv localhost 9092

# 查看 Kafka 日志
docker logs kafka
```

### API Key 冷却频繁

**现象**: `All API keys are cooling down or disabled`

**解决方案**:
1. 检查 API Key 是否有效: `python scripts/verify_api_keys.py`
2. 增加 API Key 数量（至少 10 个）
3. 调整冷却策略:
   ```yaml
   # config/api_keys.yaml
   cooling:
     min_cooldown: 5
     max_cooldown: 60
   ```

### Redis 连接失败

**现象**: `Failed to connect to Redis`

**解决方案**:
```bash
# 检查 Redis 是否运行
docker ps | grep redis

# 手动连接测试
redis-cli -h localhost -p 6379 ping
```

---

## 📈 性能调优

### 调整并发数

编辑 `config/kafka.yaml`:

```yaml
scheduler:
  max_concurrent_tasks: 100  # 默认 50，根据服务器性能调整
```

### 调整 Kafka 分区数

```bash
# 增加分区以提高并行度
kafka-topics.sh --alter --topic detection-results \
  --partitions 32 --bootstrap-server localhost:9092
```

### API Key 调度策略

编辑 `config/api_keys.yaml`:

```yaml
selection_strategy: least_loaded  # 或 round_robin, weighted
```

**策略说明**:
- `least_loaded`: 选择调用次数最少的 Key（推荐）
- `round_robin`: 轮询选择
- `weighted`: 基于优先级加权选择

---

## 🔄 停止服务

### Linux/macOS
```bash
./scripts/stop_streaming_services.sh
```

### Windows (命令提示符)
```cmd
scripts\stop_streaming_services.bat
```

### Windows (PowerShell)
```powershell
.\scripts\stop_streaming_services.ps1
```

### 停止基础设施
```bash
cd deployment
docker-compose -f docker-compose.infra.yml down
```

---

## 📝 配置文件说明

### config/api_keys.yaml
```yaml
keys:
  - id: key-001
    api_key: "sk-xxx"
    priority: 1
    qps_limit: 10
    rpm_limit: 600
```

### config/kafka.yaml
```yaml
bootstrap_servers:
  - "localhost:9092"

topics:
  detection_results:
    name: "detection-results"
    partitions: 16
```

### config/monitoring.yaml
```yaml
prometheus:
  port: 9090
  scrape_interval: 15s
```

---

## 🎓 最佳实践

1. **生产环境部署**
   - 使用至少 10 个 API Key
   - 配置 Kafka 集群（3+ 节点）
   - 启用 Redis 持久化
   - 配置 Prometheus 告警规则

2. **性能优化**
   - 根据摄像头数量调整并发数
   - 使用 `least_loaded` 策略平衡负载
   - 定期清理 Redis 缓存

3. **监控告警**
   - 监控 API Key 成功率（< 95% 告警）
   - 监控 Kafka 消费延迟（> 5s 告警）
   - 监控 LLM 延迟（P95 > 10s 告警）

4. **容错设计**
   - Kafka 和 Redis 均支持降级开关
   - API Key 失败自动切换
   - 支持优雅重启，不丢失数据

---

## 📞 支持

遇到问题？请查看：
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - 部署指南
- [架构优化实施方案.md](docs/架构优化实施方案.md) - 详细架构文档
- [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) - 实施总结

---

**祝部署顺利！** 🚀
