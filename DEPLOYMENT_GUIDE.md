# 🚀 流处理系统快速部署指南

## 已完成的工作

✅ **核心模块实现完成**

1. ✅ Kafka Producer/Consumer 模块
2. ✅ API Key 池化管理模块
3. ✅ LLM 任务调度器（异步并发）
4. ✅ 任务生成器
5. ✅ 结果聚合消费者
6. ✅ 启动/停止脚本
7. ✅ 测试脚本

---

## 📁 新增文件结构

```
algo/
├── kafka/
│   ├── __init__.py
│   ├── detection_producer.py      # Kafka 生产者
│   └── base_consumer.py           # Kafka 消费者基类
│
├── scheduler/
│   ├── __init__.py
│   ├── api_key_pool.py            # API Key 池管理 ⭐
│   └── task_scheduler.py          # LLM 任务调度器 ⭐
│
├── task_generator/
│   ├── __init__.py
│   └── simple_generator.py        # 任务生成器
│
└── consumers/
    ├── __init__.py
    └── result_aggregator.py       # 结果聚合器

scripts/
├── start_scheduler.py             # 启动调度器
├── start_task_generator.py        # 启动任务生成器
├── start_result_aggregator.py     # 启动聚合器
├── start_streaming_services.sh    # 一键启动所有服务 ⭐
├── stop_streaming_services.sh     # 一键停止所有服务
└── test_streaming_pipeline.py     # 端到端测试 ⭐
```

---

## 🏁 快速开始

### 第一步：启动基础设施

```bash
# 启动 Kafka、Redis、Prometheus 等
cd deployment
docker-compose -f docker-compose.infra.yml up -d

# 检查服务状态
docker-compose -f docker-compose.infra.yml ps
```

### 第二步：安装依赖

```bash
pip install -r requirements-streaming.txt
```

### 第三步：配置 API Keys

编辑 `config/api_keys.yaml`，添加你的 DashScope API Keys：

```yaml
api_keys:
  - key: "sk-your-key-1"
    key_id: "key_1"
    qps_limit: 10
    rpm_limit: 300
    enabled: true
  
  - key: "sk-your-key-2"
    key_id: "key_2"
    qps_limit: 10
    rpm_limit: 300
    enabled: true
```

### 第四步：初始化 Kafka Topics

```bash
python scripts/init_kafka_topics.py
```

### 第五步：验证 API Keys

```bash
python scripts/verify_api_keys.py
```

### 第六步：启动流处理服务

```bash
# 一键启动所有服务
./scripts/start_streaming_services.sh
```

这会启动：
1. **任务生成器** - 消费检测结果，生成评估任务
2. **LLM 调度器** - 使用多 Key 并发调用大模型
3. **结果聚合器** - 聚合结果并缓存

### 第七步：启动检测服务（原有服务）

```bash
python app.py
```

---

## 🧪 测试验证

### 测试 1：端到端测试

```bash
python scripts/test_streaming_pipeline.py --mode e2e --duration 60
```

这会：
1. 发送模拟检测结果到 Kafka
2. 检查任务生成
3. 等待 LLM 处理
4. 验证评估结果

### 测试 2：单独测试生产者

```bash
python scripts/test_streaming_pipeline.py --mode producer --num-messages 10
```

### 测试 3：单独测试消费者

```bash
# 监听评估任务
python scripts/test_streaming_pipeline.py --mode consumer --topic assessment-tasks

# 监听评估结果
python scripts/test_streaming_pipeline.py --mode consumer --topic risk-assessment-results
```

---

## 📊 监控服务状态

### 查看日志

```bash
# 任务生成器日志
tail -f logs/task_generator.log

# 调度器日志
tail -f logs/scheduler.log

# 聚合器日志
tail -f logs/result_aggregator.log
```

### 访问监控面板

- **Kafka UI**: http://localhost:8080
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)

### 检查 Kafka Topics

```bash
# 列出所有 Topics
kafka-topics --bootstrap-server localhost:9092 --list

# 查看 Topic 详情
kafka-topics --bootstrap-server localhost:9092 --describe --topic detection-results

# 消费消息（测试）
kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic detection-results --from-beginning --max-messages 1
```

### 检查 Redis

```bash
# 连接 Redis
redis-cli

# 查看最新结果
GET camera:1:latest

# 查看告警
LRANGE alerts:1 0 -1
```

---

## 🔧 常见问题

### Q1: Kafka 连接失败

**症状**: `Failed to connect to Kafka`

**解决方案**:
```bash
# 检查 Kafka 是否运行
docker ps | grep kafka

# 重启 Kafka
docker-compose -f deployment/docker-compose.infra.yml restart kafka

# 检查端口
netstat -an | grep 9092
```

### Q2: API Key 全部冷却

**症状**: `Failed to acquire API key within timeout`

**解决方案**:
```bash
# 1. 验证 API Keys
python scripts/verify_api_keys.py

# 2. 调整冷却时间（config/api_keys.yaml）
scheduler:
  key_cooldown_seconds: 30  # 减少到 30 秒

# 3. 增加更多 API Keys
```

### Q3: 没有收到评估结果

**可能原因**:

1. **检测结果未发送到 Kafka** - 检查 `DetectionPipeline` 是否集成了 Kafka Producer
2. **任务生成器未运行** - 检查 `logs/task_generator.log`
3. **调度器未运行** - 检查 `logs/scheduler.log`
4. **LLM API 调用失败** - 检查 API Key 和网络

**调试步骤**:
```bash
# 1. 检查每个 Topic 的消息
kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic detection-results --from-beginning --max-messages 1

kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic assessment-tasks --from-beginning --max-messages 1

kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic risk-assessment-results --from-beginning --max-messages 1

# 2. 查看服务日志
tail -f logs/*.log

# 3. 发送测试消息
python scripts/test_streaming_pipeline.py --mode producer --num-messages 1
```

---

## 🛑 停止服务

### 停止流处理服务

```bash
./scripts/stop_streaming_services.sh
```

### 停止基础设施

```bash
cd deployment
docker-compose -f docker-compose.infra.yml down
```

---

## 📝 下一步工作

### 待集成工作

1. **修改 `DetectionPipeline`** - 集成 Kafka Producer
   - 文件: `algo/rtsp_detect/pipeline.py`
   - 需要添加: Kafka Producer 初始化和消息发送

2. **添加监控指标** - 导出 Prometheus 指标
   - 文件: `algo/monitoring/metrics.py`
   - 需要添加: 检测计数、LLM 延迟、Key 池状态等指标

3. **创建 Grafana 仪表盘** - 可视化监控
   - 导入预配置仪表盘
   - 配置告警规则

### 性能优化

1. **调整 Kafka 分区数** - 根据并发摄像头数调整
2. **优化批处理大小** - 提高吞吐量
3. **调整并发任务数** - 根据硬件资源调整
4. **API Key 负载均衡** - 实现更智能的调度策略

---

## 📚 相关文档

- [架构优化实施方案](../docs/架构优化实施方案.md) - 详细技术方案
- [快速开始指南](../docs/快速开始指南.md) - 完整部署指南
- [项目总结](../docs/项目总结.md) - 项目交付清单

---

## ✅ 验收清单

- [ ] Kafka 集群正常运行
- [ ] Redis 正常运行
- [ ] 3 个 Kafka Topics 创建成功
- [ ] API Keys 验证通过
- [ ] 任务生成器正常运行
- [ ] LLM 调度器正常运行
- [ ] 结果聚合器正常运行
- [ ] 端到端测试通过
- [ ] 能看到评估结果

---

**恭喜！流处理系统已成功实施！🎉**

如有问题，请查看日志或联系技术支持。
