# 分布式架构升级 - 当前进度

## 📊 总体进度: 50% 完成

### ✅ 已完成模块

#### 1. 架构设计 ✓
- **文档**: `docs/ARCHITECTURE_DESIGN.md`
- **状态**: 完成
- **内容**:
  - 完整的系统架构设计
  - 数据流定义
  - Topic设计
  - API Key池设计
  - 容量规划
  - 监控指标定义

#### 2. Kafka消息模型 ✓
- **文件**: `streaming/kafka_messages.py`
- **状态**: 完成
- **功能**:
  - `DetectionResultMessage`: 检测结果消息模型
  - `AssessmentTaskMessage`: 评估任务消息模型
  - `RiskAssessmentResultMessage`: 风险评估结果消息模型
  - 消息序列化/反序列化
  - 类型安全的数据结构

#### 3. Kafka配置 ✓
- **文件**: `streaming/kafka_config.py`
- **状态**: 完成
- **功能**:
  - 4个Topic定义（detection-results, assessment-tasks, risk-results, dlq）
  - Producer配置生成器
  - Consumer配置生成器
  - 支持SASL/SSL安全认证

#### 4. API Key池管理器 ✓
- **文件**: `streaming/api_key_pool.py`
- **状态**: 完成
- **功能**:
  - Key状态管理（AVAILABLE, IN_USE, COOLING, DISABLED）
  - 多种调度策略（轮询、最少负载、优先级）
  - 速率限制检测
  - 自动冷却机制
  - 健康检查API
  - 实时统计信息

#### 5. 任务调度器 ✓
- **文件**: `streaming/task_scheduler.py`
- **状态**: 完成
- **功能**:
  - Kafka消费者（从assessment-tasks-topic）
  - Kafka生产者（到risk-results-topic）
  - 异步Worker池
  - LLM API调用封装
  - 重试机制（指数退避）
  - 死信队列（DLQ）支持
  - 性能统计

#### 6. 实施指南 ✓
- **文件**: `docs/IMPLEMENTATION_GUIDE.md`
- **状态**: 完成
- **内容**:
  - 完整的实施步骤
  - 测试计划
  - 监控方案
  - 运维手册
  - 故障排查指南

---

## 🚧 待完成模块

### 1. Kafka Producer适配器 (优先级: HIGH)
**文件**: `streaming/kafka_producer.py`

**任务**:
```python
class DetectionKafkaProducer:
    """Adapter for sending detection results to Kafka."""
    
    def __init__(self, config: KafkaSettings):
        self.producer = KafkaProducer(...)
    
    def send_detection_result(self, pipeline_payload: Dict):
        """Convert pipeline payload to Kafka message."""
        message = self._convert_to_kafka_message(pipeline_payload)
        self.producer.send(DETECTION_RESULTS_TOPIC.name, message)
```

**预计工时**: 4小时

---

### 2. 改造检测管道 (优先级: HIGH)
**文件**: `algo/rtsp_detect/pipeline.py`

**任务**:
- 添加Kafka Producer作为可选组件
- 修改`_run()`方法，在推送WebSocket前发送到Kafka
- 添加配置开关（向后兼容）
- 转换数据格式到Kafka消息

**代码示例**:
```python
class DetectionPipeline:
    def __init__(self, ..., kafka_producer=None, use_kafka=False):
        self.kafka_producer = kafka_producer
        self.use_kafka = use_kafka
    
    def _run(self):
        # ... 现有检测逻辑 ...
        
        # 新增：发送到Kafka
        if self.use_kafka and self.kafka_producer:
            kafka_message = self._create_kafka_message(
                detected_objects, groups, raw_frame
            )
            self.kafka_producer.send_detection_result(kafka_message)
        
        # 保持原有WebSocket推送
        if self.callback:
            self.callback(payload)
```

**预计工时**: 8小时

---

### 3. Flink流处理作业 (优先级: MEDIUM)
**文件**: `streaming/flink_processor.py`

**任务**:
```python
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import (
    FlinkKafkaConsumer,
    FlinkKafkaProducer
)

def create_traffic_assessment_job():
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(32)
    env.enable_checkpointing(10000)  # 10s
    
    # Source
    detection_consumer = FlinkKafkaConsumer(
        topics='detection-results-topic',
        deserialization_schema=...,
        properties={...}
    )
    
    detection_stream = env.add_source(detection_consumer)
    
    # Transform: 展开群组为独立任务
    task_stream = detection_stream.flat_map(lambda msg: [
        create_assessment_task(msg, group) 
        for group in msg.traffic_groups
        if should_assess(group)
    ])
    
    # Sink
    task_producer = FlinkKafkaProducer(
        topic='assessment-tasks-topic',
        serialization_schema=...,
        producer_config={...}
    )
    
    task_stream.add_sink(task_producer)
    
    env.execute("TrafficRiskAssessmentJob")
```

**预计工时**: 12小时

**注意**: 可以暂时跳过Flink，直接在调度器中消费detection-results-topic

---

### 4. 结果消费服务 (优先级: HIGH)
**文件**: `streaming/result_consumer.py`

**任务**:
```python
class RiskResultConsumer:
    """Consume risk assessment results and push to WebSocket."""
    
    def __init__(self, websocket_manager):
        self.ws_manager = websocket_manager
        self.consumer = KafkaConsumer(
            RISK_ASSESSMENT_RESULTS_TOPIC.name,
            ...
        )
        self._result_cache = {}  # camera_id -> results
    
    async def start(self):
        """Start consuming results."""
        while True:
            messages = self.consumer.poll(timeout_ms=1000)
            for tp, records in messages.items():
                for record in records:
                    result = RiskAssessmentResultMessage.from_dict(record.value)
                    await self._handle_result(result)
    
    async def _handle_result(self, result: RiskAssessmentResultMessage):
        """Process a single result."""
        # 聚合同一摄像头的结果
        camera_id = result.camera_id
        if camera_id not in self._result_cache:
            self._result_cache[camera_id] = []
        
        self._result_cache[camera_id].append(result)
        
        # 当收集到所有群组结果时，推送到WebSocket
        if self._is_complete(camera_id):
            await self._push_to_websocket(camera_id)
```

**预计工时**: 6小时

---

### 5. Docker Compose配置 (优先级: MEDIUM)
**文件**: `docker/docker-compose.yml`

**任务**:
```yaml
version: '3.8'

services:
  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
      ZOOKEEPER_TICK_TIME: 2000
    ports:
      - "2181:2181"
  
  kafka:
    image: confluentinc/cp-kafka:7.5.0
    depends_on:
      - zookeeper
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: 'zookeeper:2181'
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:29092,PLAINTEXT_HOST://localhost:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
  
  flink-jobmanager:
    image: flink:1.18
    ports:
      - "8081:8081"
    command: jobmanager
    environment:
      - JOB_MANAGER_RPC_ADDRESS=flink-jobmanager
  
  flink-taskmanager:
    image: flink:1.18
    depends_on:
      - flink-jobmanager
    command: taskmanager
    scale: 4
    environment:
      - JOB_MANAGER_RPC_ADDRESS=flink-jobmanager
  
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"
  
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
```

**预计工时**: 4小时

---

### 6. 初始化脚本 (优先级: MEDIUM)
**文件**: `scripts/setup_kafka.sh` 和 `scripts/setup_kafka.py`

**任务**:
```bash
#!/bin/bash
# setup_kafka.sh

echo "Creating Kafka topics..."

kafka-topics.sh --create \
  --bootstrap-server localhost:9092 \
  --topic detection-results-topic \
  --partitions 16 \
  --replication-factor 3 \
  --config retention.ms=3600000 \
  --config compression.type=snappy

kafka-topics.sh --create \
  --bootstrap-server localhost:9092 \
  --topic assessment-tasks-topic \
  --partitions 32 \
  --replication-factor 3 \
  --config retention.ms=7200000

kafka-topics.sh --create \
  --bootstrap-server localhost:9092 \
  --topic risk-assessment-results-topic \
  --partitions 16 \
  --replication-factor 3 \
  --config retention.ms=86400000

echo "Topics created successfully!"
```

**预计工时**: 2小时

---

### 7. 监控集成 (优先级: LOW)
**文件**: 
- `streaming/metrics.py`: Prometheus指标导出
- `config/prometheus.yml`: Prometheus配置
- `config/grafana_dashboard.json`: Grafana仪表盘

**任务**:
- 集成prometheus-client
- 导出关键指标
- 创建Grafana仪表盘模板

**预计工时**: 6小时

---

### 8. 配置文件 (优先级: HIGH)
**文件**: 
- `config/api_keys.yaml`: API Keys配置
- `config/kafka.yaml`: Kafka连接配置

**示例**:
```yaml
# config/api_keys.yaml
strategy: round_robin  # round_robin | least_loaded | priority
max_retry_per_key: 3
default_cooldown: 60.0

keys:
  - api_key: ${DASHSCOPE_KEY_001}
    name: production-key-001
    qps_limit: 5
    rpm_limit: 100
    priority: 1
  
  - api_key: ${DASHSCOPE_KEY_002}
    name: production-key-002
    qps_limit: 5
    rpm_limit: 100
    priority: 1
  
  # 添加更多keys...
```

**预计工时**: 2小时

---

## 📅 实施时间线

### 第一阶段 (本周)
- [x] 架构设计文档
- [x] Kafka消息模型
- [x] API Key池
- [x] 任务调度器
- [ ] Kafka Producer适配器
- [ ] 配置文件

### 第二阶段 (下周)
- [ ] 改造检测管道
- [ ] 结果消费服务
- [ ] Docker Compose
- [ ] 初始化脚本

### 第三阶段 (第三周)
- [ ] Flink流处理作业（可选）
- [ ] 监控集成
- [ ] 性能测试
- [ ] 文档完善

---

## 🎯 快速开始（当前可用）

虽然系统未完全实现，但核心组件已可独立测试：

### 测试API Key Pool
```python
from streaming.api_key_pool import APIKeyPool, APIKeyInfo, create_key_pool_from_config
import asyncio

# 创建测试配置
config = {
    "strategy": "round_robin",
    "keys": [
        {"api_key": "test-key-1", "name": "key-1", "qps_limit": 5},
        {"api_key": "test-key-2", "name": "key-2", "qps_limit": 5},
    ]
}

pool = create_key_pool_from_config(config)

async def test():
    # 获取key
    key = await pool.acquire_key()
    print(f"Acquired: {key.name}")
    
    # 使用后释放
    await pool.release_key(key, success=True)
    
    # 查看统计
    stats = await pool.health_check()
    print(stats)

asyncio.run(test())
```

### 测试消息模型
```python
from streaming.kafka_messages import DetectionResultMessage, DetectedObject, TrafficGroup

# 创建检测结果消息
message = DetectionResultMessage(
    camera_id=1,
    detected_objects=[
        DetectedObject(
            object_id=0,
            class_name="car",
            confidence=0.85,
            bbox=[100, 200, 150, 250]
        )
    ],
    traffic_groups=[
        TrafficGroup(
            group_index=1,
            object_count=2,
            bbox=[90, 180, 170, 280],
            classes=["car", "person"],
            avg_confidence=0.82,
            member_indices=[0, 1],
            group_image_base64="base64_data_here"
        )
    ]
)

# 序列化
data = message.to_dict()
print(json.dumps(data, indent=2))

# 反序列化
restored = DetectionResultMessage.from_dict(data)
assert restored.camera_id == message.camera_id
```

---

## 📞 需要帮助？

如需继续实现剩余模块，请告知优先级，我可以继续完成：

1. **高优先级**: Kafka Producer + Pipeline改造 → 快速验证端到端流程
2. **中优先级**: 结果消费服务 → 完成闭环
3. **低优先级**: Flink作业 → 高级流处理（可暂时跳过）

---

**当前状态**: 核心架构和基础组件已完成，可以开始集成测试 ✨
