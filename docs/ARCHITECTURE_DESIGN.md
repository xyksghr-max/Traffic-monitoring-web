# 实时危险画面检测系统架构设计文档

## 版本信息
- **版本**: v2.0 (分布式高并发版)
- **日期**: 2025-10-20
- **作者**: System Architecture Team

---

## 1. 系统架构概览

### 1.1 架构演进

**旧架构 (v1.0):**
```
摄像头 → YOLO检测 → 群组分析 → LLM分析(单Key) → WebSocket推送
```
**问题**: 单API Key限制、无法水平扩展、高延迟

**新架构 (v2.0):**
```
摄像头 → YOLO检测 → 群组分析 → Kafka Producer
                                      ↓
                          [Kafka: detection-results-topic]
                                      ↓
                            [Flink Stream Processor]
                                      ↓
                          [Kafka: assessment-tasks-topic]
                                      ↓
                   [Task Scheduler with API Key Pool]
                    (并发调用多个LLM API Keys)
                                      ↓
                        [Kafka: risk-results-topic]
                                      ↓
                      [Result Consumer & WebSocket]
```

### 1.2 核心组件

| 组件 | 职责 | 技术栈 |
|------|------|--------|
| Detection Pipeline | YOLO检测+群组分析 | Python, Ultralytics, OpenCV |
| Kafka Cluster | 消息队列 | Apache Kafka |
| Flink Processor | 流式数据处理 | Apache Flink (PyFlink) |
| Task Scheduler | API Key池管理+任务调度 | Python, AsyncIO |
| Result Consumer | 结果聚合+WebSocket推送 | Python, Flask-Sock |
| Monitoring | 监控和指标 | Prometheus, Grafana |

---

## 2. 数据流设计

### 2.1 Topic 定义

#### Topic 1: `detection-results-topic`
**用途**: 存储YOLO检测和群组分析结果

**消息格式**:
```json
{
  "message_id": "uuid",
  "camera_id": 1,
  "timestamp": "2025-10-20T12:00:00.000Z",
  "frame_metadata": {
    "width": 1920,
    "height": 1080,
    "fps": 30
  },
  "detected_objects": [
    {
      "class": "car",
      "confidence": 0.85,
      "bbox": [100, 200, 150, 250]
    }
  ],
  "traffic_groups": [
    {
      "group_index": 1,
      "object_count": 3,
      "bbox": [90, 180, 170, 280],
      "classes": ["car", "person"],
      "avg_confidence": 0.82,
      "member_indices": [0, 2, 5],
      "group_image_base64": "iVBORw0KGgo...",
      "spatial_features": {
        "density": 25.3,
        "avg_spacing": 45.2,
        "min_spacing": 20.1,
        "ped_vehicle_min_dist": 15.5
      }
    }
  ],
  "raw_frame_base64": "optional_base64_data"
}
```

**分区策略**: 按 `camera_id` 分区 (保证同一摄像头消息顺序)

#### Topic 2: `assessment-tasks-topic`
**用途**: Flink处理后的LLM评估任务队列

**消息格式**:
```json
{
  "task_id": "uuid",
  "origin_message_id": "uuid",
  "camera_id": 1,
  "timestamp": "2025-10-20T12:00:00.000Z",
  "group_index": 1,
  "group_image_base64": "iVBORw0KGgo...",
  "detection_context": {
    "detected_objects": [...],
    "group_metadata": {...},
    "spatial_features": {...}
  },
  "priority": 1,
  "retry_count": 0
}
```

**分区策略**: 轮询分区 (负载均衡)

#### Topic 3: `risk-assessment-results-topic`
**用途**: LLM风险评估结果

**消息格式**:
```json
{
  "result_id": "uuid",
  "task_id": "uuid",
  "origin_message_id": "uuid",
  "camera_id": 1,
  "group_index": 1,
  "timestamp": "2025-10-20T12:00:00.500Z",
  "assessment_result": {
    "has_dangerous_driving": true,
    "risk_level": "high",
    "risk_types": ["车人冲突", "跟车过近"],
    "description": "车辆与行人距离过近",
    "confidence": 0.92,
    "danger_object_ids": [0, 3]
  },
  "llm_metadata": {
    "model": "qwen-vl-plus",
    "api_key_id": "key-001",
    "latency_ms": 1200,
    "raw_response": "..."
  },
  "status": "success"
}
```

**分区策略**: 按 `camera_id` 分区

### 2.2 消息流转时序

```
T0: 摄像头捕获帧
T1: YOLO检测完成 (100-300ms)
T2: 群组分析完成 (10ms)
T3: 发送到 detection-results-topic
T4: Flink消费并转换 (50ms)
T5: 发送到 assessment-tasks-topic
T6: Scheduler分配API Key
T7: 调用LLM API (1000-3000ms)
T8: 发送到 risk-assessment-results-topic
T9: Consumer聚合并推送WebSocket
```

**目标端到端延迟**: < 2秒 (P95)

---

## 3. API Key 池设计

### 3.1 Key 状态机

```
     [AVAILABLE]
         ↓ (获取)
    [IN_USE]
         ↓ (调用成功)
    [AVAILABLE]
         ↓ (速率限制)
    [COOLING]
         ↓ (冷却期结束)
    [AVAILABLE]
         ↓ (调用失败3次)
    [DISABLED]
```

### 3.2 数据结构

```python
@dataclass
class APIKeyInfo:
    key_id: str
    api_key: str
    status: KeyStatus  # AVAILABLE, IN_USE, COOLING, DISABLED
    total_calls: int
    success_calls: int
    failed_calls: int
    last_call_time: float
    cooldown_until: float
    qps_limit: int = 5
    rpm_limit: int = 100
```

### 3.3 调度算法

**轮询策略 (Round-Robin)**:
- 适用场景: 所有Key能力相同
- 优点: 简单、公平
- 实现: 维护全局索引，循环选择

**最少负载策略 (Least-Loaded)**:
- 适用场景: Key能力不同或负载不均
- 优点: 动态平衡
- 实现: 选择当前调用数最少的Key

**优先级队列策略**:
- 适用场景: 有优先级任务
- 优点: 保证关键任务
- 实现: 高优先级任务优先获取最佳Key

---

## 4. Flink 作业设计

### 4.1 作业拓扑

```
Source: Kafka[detection-results-topic]
  ↓
Map: 提取群组信息
  ↓
FlatMap: 展开多个群组为独立任务
  ↓
Filter: 过滤需要LLM评估的群组
  ↓
Map: 构建评估任务
  ↓
Sink: Kafka[assessment-tasks-topic]
```

### 4.2 并行度配置

- **Source并行度**: = Kafka分区数 (建议: 16)
- **处理算子并行度**: 2x Source并行度 (建议: 32)
- **Sink并行度**: = 目标Topic分区数 (建议: 32)

### 4.3 Checkpoint配置

```yaml
checkpoint:
  interval: 10s
  timeout: 60s
  min_pause_between: 5s
  mode: EXACTLY_ONCE
  storage: file:///flink/checkpoints
```

---

## 5. 任务调度器设计

### 5.1 核心流程

```python
async def process_task(task: AssessmentTask):
    # 1. 获取可用API Key
    api_key = await key_pool.acquire_key()
    
    try:
        # 2. 调用LLM API
        result = await call_llm_api(task, api_key)
        
        # 3. 发送结果到Kafka
        await producer.send(result)
        
        # 4. 更新Key统计
        await key_pool.mark_success(api_key)
        
    except RateLimitException:
        # 5. 速率限制，Key冷却
        await key_pool.mark_cooling(api_key, cooldown=60)
        await retry_task(task)
        
    except APIException as e:
        # 6. API错误，Key可能失效
        await key_pool.mark_failed(api_key)
        await retry_task(task)
        
    finally:
        # 7. 释放Key
        await key_pool.release_key(api_key)
```

### 5.2 并发控制

- **Worker数量**: 可配置 (建议: API Key数量 × 平均QPS)
- **最大并发**: 限制为 `sum(key.qps_limit for key in keys)`
- **任务队列**: 使用 asyncio.Queue，容量 1000

### 5.3 重试策略

```python
retry_config = {
    "max_attempts": 3,
    "backoff": "exponential",  # 1s, 2s, 4s
    "retry_on": [
        RateLimitException,
        NetworkException,
        TimeoutException
    ]
}
```

---

## 6. 监控指标

### 6.1 Kafka 指标

- `kafka_topic_lag`: 各Topic的消息积压量
- `kafka_consumer_rate`: 消费速率 (msg/s)
- `kafka_producer_rate`: 生产速率 (msg/s)

### 6.2 Flink 指标

- `flink_task_records_in_per_second`: 输入速率
- `flink_task_records_out_per_second`: 输出速率
- `flink_task_back_pressure`: 背压情况
- `flink_checkpoint_duration`: Checkpoint耗时

### 6.3 调度器指标

- `api_key_pool_available`: 可用Key数量
- `api_key_pool_in_use`: 使用中Key数量
- `api_key_pool_cooling`: 冷却中Key数量
- `llm_api_call_total`: API调用总数
- `llm_api_call_success`: 成功调用数
- `llm_api_call_latency`: 调用延迟分布
- `llm_api_rate_limit_errors`: 速率限制错误数

### 6.4 端到端指标

- `detection_to_result_latency`: 端到端延迟
- `system_throughput`: 系统吞吐量 (群组/秒)
- `active_cameras`: 活跃摄像头数量

---

## 7. 扩展性设计

### 7.1 水平扩展点

| 组件 | 扩展方式 | 预期效果 |
|------|----------|----------|
| Kafka | 增加分区数 | 提升吞吐量 |
| Flink | 增加并行度 | 提升处理能力 |
| Scheduler | 增加实例数 | 提升LLM调用并发 |
| API Keys | 增加Key数量 | 突破速率限制 |

### 7.2 容量规划

**假设**:
- 每个Key: 5 QPS
- LLM延迟: 1.5s (平均)
- 每路摄像头: 0.5群组/秒

**计算**:
```
单Key理论吞吐 = 5 QPS × 1.5s = 7.5 并发任务
10个Key总吞吐 = 10 × 5 = 50 QPS
支持摄像头数 = 50 QPS / 0.5 = 100 路
```

---

## 8. 容错设计

### 8.1 故障场景

| 故障 | 检测 | 恢复策略 |
|------|------|----------|
| Kafka宕机 | 连接超时 | 自动重连 + 本地缓存 |
| Flink作业失败 | Checkpoint失败 | 从最近Checkpoint恢复 |
| API Key失效 | 连续失败3次 | 标记DISABLED，切换其他Key |
| 网络抖动 | 请求超时 | 指数退避重试 |
| 下游拥堵 | 消息Lag增长 | 触发背压，减缓上游 |

### 8.2 数据一致性

- **消息去重**: 使用 `message_id` 和 `task_id` 去重
- **顺序保证**: 同一摄像头消息在同一分区，保证FIFO
- **Exactly-Once**: Flink的事务性写入 + Kafka的幂等Producer

---

## 9. 部署架构

### 9.1 服务拓扑

```
┌─────────────────────────────────────────────────────┐
│                  Load Balancer                      │
└─────────────────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ↓                ↓                ↓
  ┌──────────┐    ┌──────────┐    ┌──────────┐
  │Detection │    │Detection │    │Detection │
  │Pipeline-1│    │Pipeline-2│    │Pipeline-N│
  └──────────┘    └──────────┘    └──────────┘
        │                │                │
        └────────────────┼────────────────┘
                         ↓
              ┌─────────────────────┐
              │   Kafka Cluster     │
              │  (3 Brokers, RF=3)  │
              └─────────────────────┘
                         ↓
              ┌─────────────────────┐
              │   Flink Cluster     │
              │ (JobManager + 4 TM) │
              └─────────────────────┘
                         ↓
              ┌─────────────────────┐
              │   Kafka Cluster     │
              └─────────────────────┘
                         ↓
        ┌────────────────┼────────────────┐
        ↓                ↓                ↓
  ┌──────────┐    ┌──────────┐    ┌──────────┐
  │Scheduler │    │Scheduler │    │Scheduler │
  │   -1     │    │   -2     │    │   -M     │
  └──────────┘    └──────────┘    └──────────┘
        │                │                │
        └────────────────┼────────────────┘
                         ↓
              ┌─────────────────────┐
              │   Kafka Cluster     │
              └─────────────────────┘
                         ↓
              ┌─────────────────────┐
              │  Result Consumer    │
              │  & WebSocket Server │
              └─────────────────────┘
```

### 9.2 资源配置建议

**开发环境**:
- Kafka: 1 Broker, 8GB RAM, 4 vCPU
- Flink: 1 JM + 2 TM, 16GB RAM total
- Scheduler: 2 instances, 4GB RAM each

**生产环境**:
- Kafka: 3 Brokers, 32GB RAM, 8 vCPU each
- Flink: 1 JM + 8 TM, 128GB RAM total
- Scheduler: 10 instances, 8GB RAM each

---

## 10. 安全考虑

### 10.1 API Key安全

- **加密存储**: 使用环境变量或加密配置文件
- **最小权限**: 每个Key只有必要的API权限
- **定期轮换**: 建议每月轮换API Key
- **审计日志**: 记录所有Key的使用情况

### 10.2 网络安全

- **内部通信**: Kafka使用SASL_SSL加密
- **外部API**: HTTPS + API Key认证
- **访问控制**: Kafka ACL限制Topic访问

---

## 11. 未来优化方向

1. **智能路由**: 基于任务特征选择最优API Key
2. **自适应QPS**: 动态调整各Key的QPS限制
3. **成本优化**: 混合使用不同价格档次的API
4. **边缘计算**: 部分检测任务下沉到边缘节点
5. **模型优化**: 使用更小更快的视觉模型

---

## 附录

### A. 术语表

- **QPS**: Queries Per Second，每秒查询数
- **RPM**: Requests Per Minute，每分钟请求数
- **TM**: TaskManager (Flink组件)
- **JM**: JobManager (Flink组件)
- **RF**: Replication Factor，副本因子

### B. 参考文档

- [Apache Kafka Documentation](https://kafka.apache.org/documentation/)
- [Apache Flink Documentation](https://flink.apache.org/)
- [PyFlink Tutorial](https://nightlies.apache.org/flink/flink-docs-master/docs/dev/python/overview/)
