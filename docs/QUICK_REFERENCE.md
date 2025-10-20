# 🚀 分布式交通监控系统 - 快速参考

## 📦 已交付内容

### 1. 完整设计文档
- **架构设计**: `docs/ARCHITECTURE_DESIGN.md` (详细技术方案)
- **实施指南**: `docs/IMPLEMENTATION_GUIDE.md` (分步实施步骤)
- **进度跟踪**: `streaming/README.md` (当前进度和待办)

### 2. 核心代码模块

#### Kafka消息层 (`streaming/kafka_messages.py`)
```python
# 三种核心消息类型
DetectionResultMessage      # YOLO检测 → Kafka
AssessmentTaskMessage       # Kafka → LLM调度器
RiskAssessmentResultMessage # LLM结果 → Kafka
```

#### Kafka配置 (`streaming/kafka_config.py`)
```python
# 4个Topic定义
DETECTION_RESULTS_TOPIC      # 检测结果队列
ASSESSMENT_TASKS_TOPIC       # 评估任务队列
RISK_ASSESSMENT_RESULTS_TOPIC # 风险结果队列
DLQ_TOPIC                    # 死信队列

# 配置管理
kafka_settings.get_producer_config()
kafka_settings.get_consumer_config()
```

#### API Key池 (`streaming/api_key_pool.py`)
```python
# 核心功能
APIKeyPool(keys, strategy="round_robin")
- acquire_key()  # 智能获取可用Key
- release_key()  # 释放并更新统计
- health_check() # 健康检查
- 支持策略: 轮询/最少负载/优先级
```

#### 任务调度器 (`streaming/task_scheduler.py`)
```python
# 分布式调度服务
TaskScheduler(api_key_pool, max_workers=10)
- 从Kafka消费任务
- 使用Key池并发调用LLM
- 自动重试和容错
- 结果写回Kafka
```

---

## 🎯 核心价值

### 性能提升
| 指标 | 旧架构 | 新架构 | 提升 |
|------|--------|--------|------|
| 并发QPS | 5 | 50 | **10x** |
| 支持摄像头 | 10路 | 100路 | **10x** |
| 单Key故障影响 | 100% | <10% | **容错** |
| 水平扩展 | ❌ | ✅ | **弹性** |

### 架构优势
1. **解耦**: Kafka消息队列实现模块独立
2. **弹性**: 各组件可独立扩展
3. **容错**: 单点故障不影响整体
4. **监控**: 完整的指标体系

---

## 📊 系统架构图

```
┌─────────────┐
│ 摄像头群组  │
│ (100+ 路)   │
└──────┬──────┘
       │
       ↓
┌─────────────────────────────────────────┐
│  Detection Pipeline (YOLO + 群组分析)   │
│  [并行处理: 每路独立]                    │
└──────┬──────────────────────────────────┘
       │ Kafka Producer
       ↓
┌─────────────────────────────────────────┐
│  Kafka: detection-results-topic         │
│  [16分区, 3副本, 1小时保留]             │
└──────┬──────────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────────┐
│  Flink Stream Processor (可选)          │
│  [展开群组, 任务分发]                    │
└──────┬──────────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────────┐
│  Kafka: assessment-tasks-topic          │
│  [32分区, 3副本, 2小时保留]             │
└──────┬──────────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────────┐
│  Task Scheduler Cluster                 │
│  [10实例 × 10 Workers = 100并发]       │
│  ┌──────────────────────────────────┐  │
│  │ API Key Pool (10 Keys)           │  │
│  │ - Key 1: 5 QPS                   │  │
│  │ - Key 2: 5 QPS                   │  │
│  │ - ...                            │  │
│  │ Total: 50 QPS                    │  │
│  └──────────────────────────────────┘  │
└──────┬──────────────────────────────────┘
       │ LLM API Calls (并发)
       ↓
┌─────────────────────────────────────────┐
│  多模态大模型 (Qwen-VL)                 │
│  [分布式负载, 突破单Key限制]             │
└──────┬──────────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────────┐
│  Kafka: risk-assessment-results-topic   │
│  [16分区, 3副本, 24小时保留]            │
└──────┬──────────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────────┐
│  Result Consumer & WebSocket Server     │
│  [聚合结果, 实时推送]                    │
└──────┬──────────────────────────────────┘
       │
       ↓
┌─────────────┐
│ 前端客户端  │
└─────────────┘
```

---

## 🔧 快速开始

### 步骤1: 安装依赖
```bash
pip install -r requirements.txt
# 新增依赖:
# - kafka-python
# - apache-flink (可选)
```

### 步骤2: 配置API Keys
```bash
# 创建配置文件
cat > config/api_keys.yaml << EOF
strategy: round_robin
max_retry_per_key: 3
default_cooldown: 60.0

keys:
  - api_key: ${DASHSCOPE_KEY_001}
    name: key-001
    qps_limit: 5
    rpm_limit: 100
  - api_key: ${DASHSCOPE_KEY_002}
    name: key-002
    qps_limit: 5
    rpm_limit: 100
EOF

# 设置环境变量
export DASHSCOPE_KEY_001="sk-your-key-1"
export DASHSCOPE_KEY_002="sk-your-key-2"
```

### 步骤3: 启动Kafka (Docker)
```bash
# 快速部署（开发环境）
docker run -d --name zookeeper -p 2181:2181 zookeeper:3.8
docker run -d --name kafka -p 9092:9092 \
  -e KAFKA_ZOOKEEPER_CONNECT=host.docker.internal:2181 \
  -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092 \
  confluentinc/cp-kafka:7.5.0

# 创建Topics
python scripts/setup_kafka.py
```

### 步骤4: 启动调度器
```bash
# 单实例测试
python -m streaming.task_scheduler \
  --config config/api_keys.yaml \
  --workers 10

# 多实例生产环境
for i in {1..10}; do
  python -m streaming.task_scheduler \
    --config config/api_keys.yaml \
    --workers 5 \
    --instance-id $i &
done
```

### 步骤5: 运行检测管道
```bash
# 修改后的管道（支持Kafka）
python app.py --enable-kafka
```

---

## 📈 监控指标

### Kafka指标
```
kafka_lag{topic="assessment-tasks-topic"} < 1000
kafka_consumer_rate{group="task-scheduler"} > 20 msg/s
```

### API Key Pool指标
```
api_key_available_count > 5
api_key_success_rate > 0.95
api_key_avg_latency_ms < 2000
```

### 端到端指标
```
detection_to_result_latency_p95 < 2000 ms
system_throughput > 25 groups/s
error_rate < 0.01
```

---

## 🔍 故障排查

### 问题1: Kafka消息积压
```bash
# 查看Lag
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group task-scheduler-group

# 解决方案
# 1. 增加Consumer实例
# 2. 增加Worker数量
# 3. 检查LLM API延迟
```

### 问题2: API Key全部冷却
```bash
# 查看Key状态
curl http://localhost:8080/api-key-pool/health

# 解决方案
# 1. 检查速率限制配置
# 2. 增加API Key数量
# 3. 调整冷却时间
```

### 问题3: 端到端延迟高
```bash
# 分段追踪
# 1. 检查YOLO检测耗时 → 优化模型/硬件
# 2. 检查Kafka传输延迟 → 增加带宽
# 3. 检查LLM API延迟 → 优化Prompt/并发
```

---

## 📚 文档索引

### 设计文档
- [x] `docs/ARCHITECTURE_DESIGN.md` - 完整架构设计
- [x] `docs/IMPLEMENTATION_GUIDE.md` - 实施指南
- [x] `streaming/README.md` - 进度跟踪

### 代码文档
- [x] `streaming/kafka_messages.py` - 消息模型
- [x] `streaming/kafka_config.py` - Kafka配置
- [x] `streaming/api_key_pool.py` - Key池管理
- [x] `streaming/task_scheduler.py` - 任务调度器

### 待完成
- [ ] `streaming/kafka_producer.py` - Producer适配器
- [ ] `streaming/flink_processor.py` - Flink作业
- [ ] `streaming/result_consumer.py` - 结果消费者
- [ ] `docker/docker-compose.yml` - Docker配置
- [ ] `scripts/setup_kafka.py` - 初始化脚本

---

## 💡 最佳实践

### 1. API Key管理
- 定期轮换Key (建议每月)
- 使用环境变量存储
- 设置合理的QPS限制
- 监控每个Key的使用情况

### 2. Kafka配置
- 开发环境: 1 Broker, RF=1
- 生产环境: 3+ Brokers, RF=3
- 合理设置保留期
- 启用压缩节省带宽

### 3. 性能调优
- Worker数 = API Key数 × 平均QPS
- Kafka分区数 ≥ Consumer数
- 监控队列长度避免积压
- 使用Checkpoint保证一致性

### 4. 容错策略
- 启用死信队列（DLQ）
- 设置合理的重试次数
- 实现断路器模式
- 定期备份配置

---

## ✅ 验收标准

### 功能验收
- [ ] Kafka集群正常运行
- [ ] 所有Topic创建成功
- [ ] API Key池健康检查通过
- [ ] 调度器能够并发调用
- [ ] 端到端流程打通

### 性能验收
- [ ] 支持50+路摄像头并发
- [ ] P95延迟 < 2秒
- [ ] 吞吐量 > 25 群组/秒
- [ ] 成功率 > 99%
- [ ] 单Key失效不影响系统

### 可靠性验收
- [ ] 消息不丢失（Exactly-Once）
- [ ] 服务重启后自动恢复
- [ ] 故障注入测试通过
- [ ] 监控告警正常触发

---

## 🎓 培训材料

### 对于开发人员
1. Kafka基础概念 (Producer, Consumer, Topic, Partition)
2. 异步编程 (asyncio, async/await)
3. LLM API调用最佳实践
4. 消息序列化/反序列化

### 对于运维人员
1. Kafka集群部署与运维
2. Docker/Docker Compose使用
3. 监控系统配置 (Prometheus + Grafana)
4. 故障排查流程

### 对于测试人员
1. 压力测试方法
2. 性能分析工具
3. 故障注入测试
4. 端到端测试用例

---

## 📞 技术支持

### 问题反馈
- 创建 GitHub Issue
- 标签: `distributed-architecture`
- 提供日志和配置信息

### 代码审查
- 所有PR需要通过审查
- 运行单元测试和集成测试
- 性能测试报告

---

**项目状态**: ✨ 核心组件完成，准备集成测试

**下一步**: 选择优先级最高的待办项开始实施

**预计完整交付时间**: 2-3周
