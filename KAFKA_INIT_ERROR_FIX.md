# Kafka Producer 初始化错误修复

## 🐛 错误信息

```
2025-10-20 21:27:48.093 | ERROR    | routes.ws:<module>:28 - Failed to initialize Kafka producer: %s
```

---

## 🔍 问题原因

### 1. 构造函数参数不匹配

**错误代码** (`routes/ws.py` 第 24 行):
```python
KAFKA_PRODUCER = DetectionResultProducer(settings.kafka_bootstrap_servers)
```

**实际构造函数签名** (`algo/kafka/detection_producer.py`):
```python
def __init__(self, bootstrap_servers: str, topic: str, enable_kafka: bool = True):
```

**问题**: 缺少必需参数 `topic`

### 2. 日志格式错误

**错误代码**:
```python
logger.error("Failed to initialize Kafka producer: %s", exc)
```

**问题**: 使用了 `%s` 占位符，但 loguru 应该使用 `{}` 或 f-string

---

## ✅ 解决方案

### 修复 1: 补充缺失参数

```python
# routes/ws.py
KAFKA_PRODUCER = DetectionResultProducer(
    bootstrap_servers=settings.kafka_bootstrap_servers,
    topic='detection-results',  # ✅ 添加 topic 参数
    enable_kafka=True
)
```

### 修复 2: 修正日志格式

```python
# 使用 f-string 格式化
logger.error(f"Failed to initialize Kafka producer: {exc}")
```

---

## 🔧 完整修复代码

**文件**: `routes/ws.py`

```python
# Kafka integration (optional)
KAFKA_PRODUCER = None
if settings.enable_kafka_streaming:
    try:
        from algo.kafka.detection_producer import DetectionResultProducer
        KAFKA_PRODUCER = DetectionResultProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            topic='detection-results',
            enable_kafka=True
        )
        logger.info("Kafka producer initialized for streaming mode")
    except ImportError:
        logger.warning("Kafka module not available, streaming mode disabled")
    except Exception as exc:
        logger.error(f"Failed to initialize Kafka producer: {exc}")
```

---

## 🚀 验证修复

### 1. 启用 Kafka 模式

```powershell
# Windows PowerShell
$env:ALGO_ENABLE_KAFKA_STREAMING="true"
python app.py
```

```bash
# Linux/WSL
export ALGO_ENABLE_KAFKA_STREAMING=true
python app.py
```

### 2. 检查启动日志

**成功日志** ✅:
```
INFO: Kafka producer initialized for streaming mode
INFO: Kafka Producer initialized for topic: detection-results
```

**失败日志** ❌ (如果 Kafka 未运行):
```
ERROR: Failed to initialize Kafka producer: [Errno -1] Connection refused
```

### 3. 确认 Kafka 服务运行

```powershell
# 检查 Kafka 容器状态
docker ps | findstr kafka

# 预期输出
# <container_id>  confluentinc/cp-kafka:7.5.0  ...  9092->9092
```

---

## 📊 Kafka Topic 配置

### 默认 Topic 名称

| Service | Topic Name | Purpose |
|---------|-----------|---------|
| **Detection Producer** | `detection-results` | 实时检测结果 |
| **LLM Task Scheduler** | `llm-analysis-tasks` | LLM 分析任务 |
| **Result Aggregator** | `llm-analysis-results` | LLM 分析结果 |

### 自定义 Topic 名称

编辑 `config.py` 添加配置：

```python
class Settings(BaseSettings):
    # ... 现有配置 ...
    
    kafka_detection_topic: str = Field(
        "detection-results",
        description="Kafka topic for detection results"
    )
```

然后在 `routes/ws.py` 中使用：

```python
KAFKA_PRODUCER = DetectionResultProducer(
    bootstrap_servers=settings.kafka_bootstrap_servers,
    topic=settings.kafka_detection_topic,  # 使用配置
    enable_kafka=True
)
```

---

## 🐛 常见错误排查

### 错误 1: Connection refused

**完整错误**:
```
Failed to initialize Kafka producer: KafkaException: Failed to connect to broker at localhost:9092: Connection refused
```

**原因**: Kafka 服务未启动

**解决方案**:
```powershell
# 启动 Kafka 基础设施
cd deployment
docker-compose -f docker-compose.infra.yml up -d kafka zookeeper

# 等待 30 秒让 Kafka 完全启动
Start-Sleep -Seconds 30

# 验证 Kafka 可用
docker-compose -f docker-compose.infra.yml exec kafka kafka-topics --list --bootstrap-server localhost:9092
```

---

### 错误 2: Topic does not exist

**完整错误**:
```
UnknownTopicOrPartitionError: Topic detection-results does not exist
```

**原因**: Topic 未自动创建（可能禁用了 auto.create.topics.enable）

**解决方案**:
```powershell
# 手动创建 Topic
docker-compose -f docker-compose.infra.yml exec kafka `
  kafka-topics --create `
  --topic detection-results `
  --bootstrap-server localhost:9092 `
  --partitions 3 `
  --replication-factor 1

# 验证创建成功
docker-compose -f docker-compose.infra.yml exec kafka `
  kafka-topics --describe --topic detection-results --bootstrap-server localhost:9092
```

---

### 错误 3: Missing required parameter 'topic'

**完整错误**:
```
TypeError: __init__() missing 1 required positional argument: 'topic'
```

**原因**: 调用构造函数时缺少 `topic` 参数

**解决方案**: 已在本次修复中解决 ✅

---

## 🎯 完整测试流程

### 1. 启动基础设施

```powershell
# 启动 Kafka + Zookeeper
cd deployment
docker-compose -f docker-compose.infra.yml up -d zookeeper kafka

# 等待 Kafka 就绪
Start-Sleep -Seconds 30
```

### 2. 验证 Kafka 连接

```powershell
# 测试脚本
python -c "
from confluent_kafka.admin import AdminClient
admin = AdminClient({'bootstrap.servers': 'localhost:9092'})
metadata = admin.list_topics(timeout=10)
print(f'Kafka 连接成功！Topics: {list(metadata.topics.keys())}')
"
```

### 3. 启动 Flask 应用（Kafka 模式）

```powershell
$env:ALGO_ENABLE_KAFKA_STREAMING="true"
python app.py
```

### 4. 检查启动日志

**预期输出**:
```
2025-10-20 21:30:00.123 | INFO     | routes.ws:<module>:24 - Kafka producer initialized for streaming mode
2025-10-20 21:30:00.124 | INFO     | algo.kafka.detection_producer:__init__:42 - Kafka Producer initialized for topic: detection-results
2025-10-20 21:30:00.200 | INFO     | werkzeug:_log:224 - Running on http://0.0.0.0:5000
```

---

## 📚 相关文档

- [WINDOWS_KAFKA_GUIDE.md](WINDOWS_KAFKA_GUIDE.md) - Windows 完整启动指南
- [KAFKA_INTEGRATION_GUIDE.md](KAFKA_INTEGRATION_GUIDE.md) - Kafka 集成说明
- [KAFKA_CONFIG_FIX.md](KAFKA_CONFIG_FIX.md) - librdkafka 配置修复

---

## ✅ 修复确认清单

完成修复后，确认以下项：

- [ ] `routes/ws.py` 已更新，包含 3 个参数：`bootstrap_servers`, `topic`, `enable_kafka`
- [ ] 日志格式改为 f-string: `logger.error(f"... {exc}")`
- [ ] Kafka 服务正在运行（`docker ps` 可见 kafka 容器）
- [ ] Flask 启动时显示 "Kafka producer initialized"
- [ ] 没有看到 "Failed to initialize Kafka producer" 错误
- [ ] Topic `detection-results` 已创建（或允许自动创建）

---

**修复完成！** 🎉 现在 Kafka Producer 可以正确初始化了。
