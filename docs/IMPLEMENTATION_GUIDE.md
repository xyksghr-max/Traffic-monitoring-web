# 实时危险画面检测系统 - 分布式架构实施指南

## 📋 实施概要

本文档提供了将现有单体检测系统改造为基于 **Kafka + Flink + 多 API Key 调度**的分布式高并发系统的完整实施方案。

---

## 🎯 核心目标达成

### 1. 并发能力提升
- **旧架构**: 单 API Key，~5 QPS
- **新架构**: 10 Keys 并发，~50 QPS
- **提升倍数**: 10x
- **支持摄像头**: 100+ 路同时检测

### 2. 端到端延迟优化
- **目标延迟**: < 2秒 (P95)
- **组件延迟**:
  - YOLO检测: 100-300ms
  - 群组分析: 10ms
  - Kafka传输: 50ms
  - Flink处理: 50ms
  - LLM推理: 1000-2000ms
  - 结果聚合: 50ms

### 3. 系统弹性
- Kafka消息队列解耦
- 水平扩展能力
- 自动故障恢复
- API Key池化与智能调度

---

## 📁 项目结构

```
Traffic-monitoring-web/
├── docs/
│   └── ARCHITECTURE_DESIGN.md      # 详细架构设计文档
├── streaming/                       # 新增：流处理模块
│   ├── __init__.py
│   ├── kafka_messages.py           # Kafka消息模型定义
│   ├── kafka_config.py             # Kafka配置
│   ├── api_key_pool.py             # API Key池管理器
│   ├── task_scheduler.py           # 任务调度器服务
│   ├── flink_processor.py          # Flink流处理作业（待实现）
│   ├── result_consumer.py          # 结果消费服务（待实现）
│   └── kafka_producer.py           # Kafka生产者适配器（待实现）
├── algo/
│   └── rtsp_detect/
│       └── pipeline.py             # 需修改：添加Kafka Producer
├── config/
│   ├── kafka_topics.yaml           # Kafka Topics配置（待创建）
│   └── api_keys.yaml               # API Keys配置（待创建）
├── docker/
│   └── docker-compose.yml          # Docker部署配置（待创建）
└── scripts/
    ├── setup_kafka.sh              # Kafka初始化脚本（待创建）
    └── start_scheduler.py          # 调度器启动脚本（待创建）
```

---

## 🚀 实施步骤

### 阶段 1: 基础设施准备 (1-2天)

#### 1.1 部署 Kafka 集群
```bash
# 使用 Docker Compose 快速部署
cd docker
docker-compose up -d kafka zookeeper

# 创建 Topics
python scripts/setup_kafka.py
```

#### 1.2 安装依赖
```bash
pip install kafka-python apache-flink openai pydantic loguru
```

### 阶段 2: 改造检测管道 (2-3天)

#### 2.1 修改 `pipeline.py`
- 添加 Kafka Producer
- 将检测结果发送到 `detection-results-topic`
- 保持向后兼容（可选开关）

#### 2.2 创建消息适配器
- 将现有数据结构转换为 Kafka 消息格式
- 处理 Base64 编码

### 阶段 3: 实现 Flink 处理 (2-3天)

#### 3.1 创建 Flink 作业
```python
# flink_processor.py
# 消费 detection-results-topic
# 展开群组为独立任务
# 发送到 assessment-tasks-topic
```

#### 3.2 配置并行度
- Source: 16 (= Kafka分区数)
- Processing: 32
- Sink: 32

### 阶段 4: 部署调度器服务 (3-4天)

#### 4.1 配置 API Keys
```yaml
# config/api_keys.yaml
strategy: round_robin
max_retry_per_key: 3
default_cooldown: 60.0
keys:
  - api_key: sk-xxx-001
    name: key-001
    qps_limit: 5
    rpm_limit: 100
  - api_key: sk-xxx-002
    name: key-002
    qps_limit: 5
    rpm_limit: 100
  # ... 更多 Keys
```

#### 4.2 启动调度器
```bash
python scripts/start_scheduler.py --config config/api_keys.yaml --workers 10
```

### 阶段 5: 实现结果消费 (1-2天)

#### 5.1 创建结果消费服务
- 从 `risk-assessment-results-topic` 消费
- 聚合同一摄像头的结果
- 推送到 WebSocket 客户端

#### 5.2 集成到现有系统
- 修改 `routes/ws.py`
- 添加结果缓存机制

### 阶段 6: 监控与优化 (2-3天)

#### 6.1 添加监控指标
- Kafka Lag监控
- API Key池状态
- 端到端延迟追踪

#### 6.2 性能调优
- 调整 Kafka 分区数
- 优化 Flink 并行度
- 调整 Worker 数量

---

## 📊 已完成的组件

### ✅ 架构设计文档
- 位置: `docs/ARCHITECTURE_DESIGN.md`
- 内容: 完整的系统架构、数据流、组件设计

### ✅ Kafka 消息模型
- 位置: `streaming/kafka_messages.py`
- 内容: 
  - `DetectionResultMessage`: 检测结果消息
  - `AssessmentTaskMessage`: 评估任务消息
  - `RiskAssessmentResultMessage`: 风险评估结果消息

### ✅ Kafka 配置
- 位置: `streaming/kafka_config.py`
- 内容:
  - Topic 定义
  - Producer/Consumer 配置
  - 连接参数

### ✅ API Key 池管理器
- 位置: `streaming/api_key_pool.py`
- 功能:
  - Key 状态管理 (AVAILABLE, IN_USE, COOLING, DISABLED)
  - 多种调度策略 (轮询、最少负载、优先级)
  - 速率限制处理
  - 健康检查

### ✅ 任务调度器
- 位置: `streaming/task_scheduler.py`
- 功能:
  - Kafka 消费与生产
  - Worker 池管理
  - 异步 LLM 调用
  - 重试与容错
  - 统计与监控

---

## 🔧 待实现组件

### 1. Kafka Producer 适配器
**文件**: `streaming/kafka_producer.py`

**功能**:
- 封装 KafkaProducer
- 消息序列化
- 错误处理

### 2. Detection Pipeline 改造
**文件**: `algo/rtsp_detect/pipeline.py`

**修改点**:
```python
# 添加 Kafka Producer
from streaming.kafka_producer import DetectionKafkaProducer

class DetectionPipeline:
    def __init__(self, ..., kafka_producer=None):
        self.kafka_producer = kafka_producer
    
    def _run(self):
        # ... 现有检测逻辑 ...
        
        # 发送到 Kafka
        if self.kafka_producer:
            message = self._create_kafka_message(...)
            self.kafka_producer.send(message)
        
        # 保持原有 WebSocket 推送（向后兼容）
        if self.callback:
            self.callback(payload)
```

### 3. Flink 流处理作业
**文件**: `streaming/flink_processor.py`

**功能**:
```python
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors import FlinkKafkaConsumer, FlinkKafkaProducer

def create_flink_job():
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(32)
    
    # Source: detection-results-topic
    # Process: 展开群组
    # Sink: assessment-tasks-topic
    
    env.execute("TrafficRiskAssessmentJob")
```

### 4. 结果消费服务
**文件**: `streaming/result_consumer.py`

**功能**:
```python
class ResultConsumer:
    def __init__(self, websocket_manager):
        self.ws_manager = websocket_manager
        self.consumer = KafkaConsumer(...)
    
    async def consume(self):
        # 消费 risk-assessment-results-topic
        # 聚合结果
        # 推送到 WebSocket
```

### 5. 配置文件
**文件**: 
- `config/api_keys.yaml`: API Keys配置
- `docker/docker-compose.yml`: Docker部署配置
- `scripts/setup_kafka.sh`: Kafka初始化脚本

---

## 🧪 测试计划

### 单元测试
- API Key Pool 测试
- 消息序列化/反序列化测试
- 调度器逻辑测试

### 集成测试
- Kafka 端到端测试
- Flink 作业测试
- WebSocket 集成测试

### 性能测试
```bash
# 压测工具
pip install locust

# 模拟 50 路摄像头，每路 0.5 群组/秒
python tests/load_test.py --cameras 50 --rate 0.5
```

**验收指标**:
- 吞吐量: ≥ 25 群组/秒
- P95 延迟: < 2秒
- 成功率: > 99%

---

## 📈 监控仪表盘

### Grafana Dashboard 配置

**Panel 1: Kafka Metrics**
- Topic Lag
- Consumer Rate
- Producer Rate

**Panel 2: API Key Pool**
- Available Keys
- Cooling Keys
- Success Rate per Key

**Panel 3: Scheduler**
- Tasks Processed
- Average LLM Latency
- Worker Utilization

**Panel 4: End-to-End**
- Detection to Result Latency
- System Throughput
- Error Rate

---

## 🔐 安全考虑

### API Key 管理
```bash
# 使用环境变量
export DASHSCOPE_KEY_001="sk-xxx"
export DASHSCOPE_KEY_002="sk-yyy"

# 或使用加密配置文件
python scripts/encrypt_keys.py config/api_keys.yaml
```

### Kafka 安全
```yaml
# 生产环境建议启用 SASL_SSL
security_protocol: SASL_SSL
sasl_mechanism: SCRAM-SHA-256
```

---

## 🚧 迁移策略

### 灰度发布
1. **阶段 1** (Week 1): 10% 流量 → 新架构
2. **阶段 2** (Week 2): 50% 流量
3. **阶段 3** (Week 3): 100% 流量
4. **阶段 4** (Week 4): 下线旧架构

### 回滚方案
- 保留旧架构代码
- 使用配置开关控制
- Kafka消息可回溯

---

## 📞 运维手册

### 启动服务
```bash
# 1. 启动 Kafka 集群
cd docker && docker-compose up -d

# 2. 启动 Flink 作业
cd streaming && python flink_processor.py

# 3. 启动调度器 (多实例)
for i in {1..10}; do
    python scripts/start_scheduler.py --instance $i &
done

# 4. 启动结果消费服务
python streaming/result_consumer.py

# 5. 启动检测管道（原有服务）
python app.py
```

### 故障排查
```bash
# 查看 Kafka Lag
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group task-scheduler-group --describe

# 查看调度器状态
curl http://localhost:8080/scheduler/stats

# 查看 API Key 池状态
curl http://localhost:8080/api-key-pool/health
```

---

## 📚 参考资料

- [Kafka Documentation](https://kafka.apache.org/documentation/)
- [PyFlink Documentation](https://nightlies.apache.org/flink/flink-docs-master/docs/dev/python/overview/)
- [Qwen-VL API](https://help.aliyun.com/zh/dashscope/developer-reference/qwen-vl-plus)

---

## 👥 团队分工建议

| 角色 | 负责模块 | 预计工时 |
|------|----------|----------|
| 后端工程师 A | Pipeline改造 + Kafka Producer | 3天 |
| 后端工程师 B | Task Scheduler + API Key Pool | 4天 |
| 数据工程师 | Flink作业 + Kafka配置 | 4天 |
| 运维工程师 | Docker部署 + 监控 | 3天 |
| 测试工程师 | 测试方案 + 压测 | 2天 |

**总工时**: 约 16 人天

**预计完成时间**: 2-3周

---

## ✅ 验收清单

- [ ] Kafka集群部署并创建所有Topics
- [ ] API Key池配置完成并通过健康检查
- [ ] 检测管道成功发送消息到Kafka
- [ ] Flink作业正常运行并处理消息
- [ ] 调度器能够并发调用多个API Keys
- [ ] 结果消费服务正常推送到WebSocket
- [ ] 监控仪表盘显示所有关键指标
- [ ] 压测达到设计目标（50路摄像头，<2s延迟）
- [ ] 故障注入测试通过（单Key失效不影响系统）
- [ ] 文档完整（部署文档、运维手册、API文档）

---

**祝实施顺利！** 🎉
