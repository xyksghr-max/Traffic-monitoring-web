# 并发优化相关文件说明

本目录包含了实时危险画面检测系统并发处理能力优化所需的所有配置、文档和脚本。

## 📁 目录结构

```
Traffic-monitoring-web/
│
├── config/                          # 配置文件目录 (新增)
│   ├── api_keys.yaml               # API Keys 池化配置
│   ├── kafka.yaml                  # Kafka 集群配置
│   └── monitoring.yaml             # 监控和告警配置
│
├── deployment/                      # 部署文件目录 (新增)
│   ├── docker-compose.infra.yml    # 基础设施编排 (Kafka/Redis/Prometheus)
│   ├── prometheus.yml              # Prometheus 配置
│   └── grafana-datasources.yml     # Grafana 数据源配置
│
├── docs/                            # 文档目录 (新增)
│   ├── 架构优化实施方案.md          # 详细技术方案 (80+ 页)
│   ├── 快速开始指南.md              # 部署和配置指南
│   └── 项目总结.md                  # 项目总结和交付清单
│
├── scripts/                         # 工具脚本目录 (新增)
│   ├── init_kafka_topics.py        # 初始化 Kafka Topics
│   └── verify_api_keys.py          # 验证 API Keys 可用性
│
├── algo/                            # 算法模块 (待实现)
│   ├── kafka/                      # Kafka 集成模块
│   │   ├── detection_producer.py   # 检测结果生产者
│   │   └── base_consumer.py        # 基础消费者类
│   │
│   ├── task_generator/             # 任务生成器模块
│   │   └── simple_generator.py     # Python 简化版任务生成器
│   │
│   ├── scheduler/                  # 调度器模块
│   │   ├── api_key_pool.py         # API Key 池管理
│   │   └── task_scheduler.py       # LLM 任务调度器
│   │
│   ├── consumers/                  # 消费者模块
│   │   └── result_aggregator.py    # 结果聚合消费者
│   │
│   └── monitoring/                 # 监控模块
│       └── metrics.py              # Prometheus 指标导出
│
├── flink_jobs/                      # Flink 作业目录 (可选)
│   └── assessment_task_generator.py # Flink 任务生成器
│
└── requirements-streaming.txt       # 流处理相关依赖 (新增)
```

## 📖 核心文档

### 1. 架构优化实施方案 (`docs/架构优化实施方案.md`)

**80+ 页的详细技术方案**，包含：

- ✅ 现有系统分析和瓶颈定位
- ✅ 目标架构设计和数据流设计
- ✅ Kafka 集成方案 (Topic 设计、Producer/Consumer 实现)
- ✅ Flink 流处理方案 (或 Python 简化方案)
- ✅ API Key 池化调度器设计 (完整代码示例)
- ✅ 监控和可观测性方案
- ✅ 实施计划和验收标准

### 2. 快速开始指南 (`docs/快速开始指南.md`)

**一步步的部署指南**，包含：

- ✅ 环境准备和依赖安装
- ✅ 配置文件说明
- ✅ 服务启动步骤
- ✅ 验证和测试方法
- ✅ 故障排查指南
- ✅ 性能调优建议

### 3. 项目总结 (`docs/项目总结.md`)

**项目交付总结**，包含：

- ✅ 架构设计总览
- ✅ 核心模块说明
- ✅ 预期性能提升
- ✅ 实施计划
- ✅ 验收标准

## ⚙️ 配置文件说明

### 1. `config/api_keys.yaml`

配置多个 DashScope API Key 用于池化调度：

```yaml
api_keys:
  - key: "sk-your-key-1"
    key_id: "key_1"
    qps_limit: 10
    rpm_limit: 300
    enabled: true

scheduler:
  max_concurrent_tasks: 50
  key_cooldown_seconds: 60
  strategy: "least_loaded"
```

### 2. `config/kafka.yaml`

配置 Kafka 集群和 Topics：

```yaml
kafka:
  bootstrap_servers: "localhost:9092"
  
  topics:
    detection_results:
      name: "detection-results"
      partitions: 16
      replication_factor: 3
```

### 3. `config/monitoring.yaml`

配置监控和告警：

```yaml
prometheus:
  enabled: true
  port: 9091

alerts:
  rules:
    - name: "high_latency"
      threshold: 2.5
      severity: "warning"
```

## 🚀 快速开始

### 第一步: 启动基础设施

```bash
cd deployment
docker-compose -f docker-compose.infra.yml up -d
```

这将启动：
- Kafka (+ Zookeeper)
- Kafka UI (Web 管理界面)
- Redis
- Prometheus
- Grafana
- PostgreSQL (可选)

### 第二步: 安装依赖

```bash
pip install -r requirements-streaming.txt
```

### 第三步: 配置 API Keys

编辑 `config/api_keys.yaml`，添加你的 API Keys。

### 第四步: 初始化系统

```bash
# 创建 Kafka Topics
python scripts/init_kafka_topics.py

# 验证 API Keys
python scripts/verify_api_keys.py
```

### 第五步: 启动服务

参考 `docs/快速开始指南.md` 启动各个服务组件。

## 🛠️ 工具脚本

### `scripts/init_kafka_topics.py`

自动创建系统所需的 Kafka Topics：
- `detection-results` (16 分区)
- `assessment-tasks` (16 分区)
- `risk-assessment-results` (16 分区)

### `scripts/verify_api_keys.py`

批量测试所有配置的 API Key 是否可用，输出验证报告。

## 📊 监控面板

启动基础设施后，可以访问：

- **Kafka UI**: http://localhost:8080
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)
- **Redis**: localhost:6379

## 🔍 验证部署

运行以下命令验证服务状态：

```bash
# 检查 Docker 容器
docker-compose -f deployment/docker-compose.infra.yml ps

# 检查 Kafka Topics
kafka-topics --bootstrap-server localhost:9092 --list

# 检查 Redis
redis-cli ping

# 检查 Prometheus 采集目标
curl http://localhost:9090/api/v1/targets
```

## 📝 下一步

1. **阅读文档**: 从 `docs/架构优化实施方案.md` 开始
2. **配置系统**: 编辑 `config/` 目录下的配置文件
3. **实现模块**: 根据方案实现 `algo/` 目录下的各个模块
4. **测试验证**: 使用测试脚本验证功能和性能
5. **部署上线**: 参考快速开始指南进行部署

## 🆘 获取帮助

- 📖 查看详细文档: `docs/` 目录
- 🐛 问题反馈: [GitHub Issues](https://github.com/xyksghr-max/Traffic-monitoring-web/issues)
- 📧 联系方式: 见项目主 README

---

**祝开发顺利！🎉**
