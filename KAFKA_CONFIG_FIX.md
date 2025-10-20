# Kafka Consumer 配置问题修复

## 🐛 问题描述

运行流处理服务时出现以下错误：

```
KafkaError{code=_INVALID_ARG,val=-186,str="No such configuration property: "max.poll.records""}
```

以及后续的日志格式化错误：

```
KeyError: 'code=_INVALID_ARG,val=-186,str="No such configuration property'
```

---

## 🔍 问题原因

### 1. Kafka 配置错误

**问题**: `confluent-kafka` Python 客户端基于 `librdkafka`，不支持 Java Kafka 客户端的 `max.poll.records` 配置项。

**对比**:

| 配置项 | Java Kafka Client | confluent-kafka (librdkafka) |
|--------|------------------|------------------------------|
| `max.poll.records` | ✅ 支持 | ❌ **不支持** |
| `queued.max.messages.kbytes` | ❌ 不支持 | ✅ 支持 |

### 2. Loguru 日志格式化错误

**问题**: Kafka 错误消息中包含花括号 `{}`，被 loguru 误认为是格式化占位符。

```python
# ❌ 错误写法（会导致 KeyError）
logger.error(f"Failed to start: {e}", exc_info=True)

# ✅ 正确写法
logger.error("Failed to start: {}", str(e))
logger.exception("Exception details:")
```

---

## ✅ 修复方案

### 1. 修改 `algo/kafka/base_consumer.py`

**原代码** (❌ 错误):
```python
self.consumer = Consumer({
    'bootstrap.servers': bootstrap_servers,
    'group.id': group_id,
    'auto.offset.reset': auto_offset_reset,
    'enable.auto.commit': auto_commit,
    'auto.commit.interval.ms': 5000,
    'max.poll.records': 500,  # ❌ 不支持
    'session.timeout.ms': 30000,
    'heartbeat.interval.ms': 3000,
})
```

**修复后** (✅ 正确):
```python
self.consumer = Consumer({
    'bootstrap.servers': bootstrap_servers,
    'group.id': group_id,
    'auto.offset.reset': auto_offset_reset,
    'enable.auto.commit': auto_commit,
    'auto.commit.interval.ms': 5000,
    # 移除 'max.poll.records'，使用 librdkafka 支持的配置
    'queued.max.messages.kbytes': 65536,  # 64MB 队列大小
    'session.timeout.ms': 30000,
    'heartbeat.interval.ms': 3000,
})
```

### 2. 修改启动脚本的日志处理

修改以下文件：
- `scripts/start_task_generator.py`
- `scripts/start_scheduler.py`
- `scripts/start_result_aggregator.py`

**原代码** (❌ 错误):
```python
except Exception as e:
    logger.error(f"Failed to start: {e}", exc_info=True)
    sys.exit(1)
```

**修复后** (✅ 正确):
```python
except Exception as e:
    logger.error("Failed to start: {}", str(e))
    logger.exception("Exception details:")
    sys.exit(1)
```

---

## 📚 librdkafka 配置参考

### 常用配置项对照表

| Java Kafka | confluent-kafka (librdkafka) | 说明 |
|-----------|----------------------------|------|
| `max.poll.records` | `fetch.message.max.bytes` | 单次拉取最大消息数/字节 |
| - | `queued.max.messages.kbytes` | 消费者内存队列大小 (KB) |
| `fetch.max.bytes` | `fetch.message.max.bytes` | 单条消息最大字节数 |
| `max.partition.fetch.bytes` | `max.partition.fetch.bytes` | 单个分区拉取最大字节数 |

### librdkafka Consumer 推荐配置

```python
consumer_config = {
    # 基础配置
    'bootstrap.servers': 'localhost:9092',
    'group.id': 'my-consumer-group',
    'auto.offset.reset': 'latest',  # 或 'earliest'
    
    # 自动提交
    'enable.auto.commit': True,
    'auto.commit.interval.ms': 5000,
    
    # 会话管理
    'session.timeout.ms': 30000,
    'heartbeat.interval.ms': 3000,
    
    # 内存和性能
    'queued.max.messages.kbytes': 65536,  # 64MB 队列
    'fetch.message.max.bytes': 1048576,   # 单条消息最大 1MB
    'max.partition.fetch.bytes': 1048576,  # 单分区拉取最大 1MB
    
    # 可靠性
    'enable.auto.offset.store': True,
    'isolation.level': 'read_committed',  # 仅读取已提交的消息
}
```

---

## 🔧 验证修复

### 1. 重新启动服务

**Windows (PowerShell)**:
```powershell
# 停止旧服务
.\scripts\stop_streaming_services.ps1

# 启动新服务
.\scripts\start_streaming_services.ps1
```

**Linux/macOS**:
```bash
# 停止旧服务
./scripts/stop_streaming_services.sh

# 启动新服务
./scripts/start_streaming_services.sh
```

### 2. 检查日志

查看服务是否成功启动：

```bash
# Windows
Get-Content logs\streaming\task_generator.log -Tail 20

# Linux/macOS
tail -n 20 logs/streaming/task_generator.log
```

**预期输出**:
```
2025-10-20 20:55:54.348 | INFO     | __main__:main:28 - === Starting Task Generator ===
2025-10-20 20:55:54.356 | INFO     | algo.kafka.base_consumer:__init__:49 - Kafka Consumer initialized: group=task-generator-group, topics=['detection-results']
2025-10-20 20:55:54.358 | SUCCESS  | __main__:main:51 - === Task Generator started successfully ===
```

### 3. 测试消息流转

```bash
python scripts/test_streaming_pipeline.py --mode e2e --duration 30
```

---

## 📖 参考资料

### librdkafka 官方文档

- **配置参考**: https://github.com/confluentinc/librdkafka/blob/master/CONFIGURATION.md
- **Python 客户端**: https://docs.confluent.io/kafka-clients/python/current/overview.html

### 关键配置说明

#### `queued.max.messages.kbytes`
- **类型**: Integer
- **默认值**: 65536 (64MB)
- **说明**: 消费者本地队列的最大内存大小（KB）
- **用途**: 控制消费者缓存的消息量，防止内存溢出

#### `fetch.message.max.bytes`
- **类型**: Integer
- **默认值**: 1048576 (1MB)
- **说明**: 单条消息的最大字节数
- **用途**: 限制单条消息大小，如果消息超过此值会被拒绝

#### `max.partition.fetch.bytes`
- **类型**: Integer
- **默认值**: 1048576 (1MB)
- **说明**: 从单个分区拉取的最大字节数
- **用途**: 控制单次 fetch 请求的数据量

---

## ⚠️ 注意事项

### 1. Java vs Python 客户端

**不要直接照搬 Java Kafka 配置！**

很多在线教程和 Stack Overflow 答案使用的是 Java Kafka 客户端配置，这些配置在 Python `confluent-kafka` 中可能不适用。

### 2. 配置属性命名

- **Java**: 使用点号分隔的小写命名 (`max.poll.records`)
- **librdkafka**: 使用点号分隔的小写命名，但属性名不同 (`queued.max.messages.kbytes`)

### 3. 日志格式化

使用 loguru 时，避免在异常消息中出现花括号问题：

```python
# ❌ 错误：f-string + exc_info=True 可能导致 KeyError
logger.error(f"Error: {exception}", exc_info=True)

# ✅ 正确：使用 loguru 的占位符
logger.error("Error: {}", str(exception))
logger.exception("Details:")  # 自动包含堆栈跟踪
```

---

## ✅ 修复清单

- [x] 移除 `max.poll.records` 配置
- [x] 添加 `queued.max.messages.kbytes` 配置
- [x] 修复 `start_task_generator.py` 日志格式化
- [x] 修复 `start_scheduler.py` 日志格式化
- [x] 修复 `start_result_aggregator.py` 日志格式化
- [x] 验证服务可以正常启动
- [x] 创建问题修复文档

---

## 🎉 总结

问题已修复！主要改动：

1. **配置修复**: 使用 librdkafka 兼容的配置项
2. **日志修复**: 正确处理异常消息中的特殊字符
3. **文档完善**: 提供详细的配置对照表和最佳实践

现在可以正常启动流处理服务了！🚀

---

**相关文档**:
- [KAFKA_INTEGRATION_GUIDE.md](KAFKA_INTEGRATION_GUIDE.md) - Kafka 集成指南
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - 部署指南
- [librdkafka Configuration](https://github.com/confluentinc/librdkafka/blob/master/CONFIGURATION.md) - 官方配置文档
