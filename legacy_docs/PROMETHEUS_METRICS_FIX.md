# Prometheus Metrics 端点配置

## 🐛 问题描述

Flask 应用启动后，终端持续输出：

```
127.0.0.1 - - [20/Oct/2025 21:17:01] "GET /metrics HTTP/1.1" 404 -
127.0.0.1 - - [20/Oct/2025 21:17:17] "GET /metrics HTTP/1.1" 404 -
127.0.0.1 - - [20/Oct/2025 21:17:33] "GET /metrics HTTP/1.1" 404 -
```

---

## 🔍 问题原因

1. **Prometheus 正在抓取指标**: Prometheus 配置为每 15 秒从 `http://localhost:5000/metrics` 抓取指标
2. **Flask 应用缺少 `/metrics` 端点**: 应用还没有暴露 Prometheus 指标端点
3. **结果**: 持续返回 404 错误

---

## ✅ 解决方案

### 方案 1: 在 Flask 中添加 `/metrics` 端点（推荐）

已修改 `app.py`，自动启用 Prometheus metrics 端点。

**修改内容**:

```python
# 导入 Prometheus 库
try:
    from prometheus_client import make_wsgi_app
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client not installed")

# 在 create_app() 中添加 metrics 端点
if PROMETHEUS_AVAILABLE:
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {
        '/metrics': make_wsgi_app()
    })
    logger.info("Prometheus metrics endpoint enabled at /metrics")
```

### 方案 2: 禁用 Prometheus 抓取（临时方案）

如果暂时不需要监控，可以停止 Prometheus：

```powershell
# Windows
cd deployment
docker-compose -f docker-compose.infra.yml stop prometheus

# 或者完全移除 Prometheus
docker-compose -f docker-compose.infra.yml rm -f prometheus
```

---

## 🚀 应用修复

### 1. 确保已安装依赖

```powershell
# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 安装 Prometheus 客户端
pip install prometheus-client>=0.19.0

# 或安装完整的流处理依赖
pip install -r requirements-streaming.txt
```

### 2. 重启 Flask 应用

```powershell
# 停止当前运行的应用 (Ctrl+C)

# 重新启动
$env:ALGO_ENABLE_KAFKA_STREAMING="true"
python app.py
```

### 3. 验证 `/metrics` 端点

**方法 1: 浏览器访问**

打开 http://localhost:5000/metrics

**方法 2: PowerShell 命令**

```powershell
curl http://localhost:5000/metrics
```

**预期输出**（部分）:
```
# HELP python_gc_objects_collected_total Objects collected during gc
# TYPE python_gc_objects_collected_total counter
python_gc_objects_collected_total{generation="0"} 1234.0
python_gc_objects_collected_total{generation="1"} 567.0
python_gc_objects_collected_total{generation="2"} 89.0
# HELP python_info Python platform information
# TYPE python_info gauge
python_info{implementation="CPython",major="3",minor="10",patchlevel="11",version="3.10.11"} 1.0
...
```

---

## 📊 查看 Prometheus 抓取状态

1. 访问 Prometheus UI: http://localhost:9100
2. 点击 **Status → Targets**
3. 查找 `flask-app` 目标

**状态说明**:
- **UP** (绿色) ✅ - 成功抓取指标
- **DOWN** (红色) ❌ - 连接失败或 404

---

## 🔧 自定义指标配置

### 1. 配置 Prometheus 抓取间隔

编辑 `deployment/prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'flask-app'
    scrape_interval: 15s  # 修改为 30s 或 60s 以减少请求频率
    static_configs:
      - targets: ['host.docker.internal:5000']
```

重启 Prometheus：
```powershell
cd deployment
docker-compose -f docker-compose.infra.yml restart prometheus
```

### 2. 添加自定义业务指标

在 `algo/monitoring/metrics.py` 中已定义了业务指标，可以在代码中使用：

```python
from algo.monitoring.metrics import (
    detection_total,
    detection_latency,
    llm_requests_total,
    record_detection,
)

# 记录检测
record_detection(
    camera_id="1",
    model_type="yolov8n",
    latency=0.5,
    num_objects=10,
    num_groups=3
)

# 手动计数
detection_total.labels(camera_id="1", model_type="yolov8n").inc()
```

---

## 🎯 常见 Prometheus 查询

访问 http://localhost:9100/graph 执行查询：

### 系统指标

```promql
# Python 进程内存使用 (MB)
process_resident_memory_bytes / 1024 / 1024

# CPU 使用率
rate(process_cpu_seconds_total[1m]) * 100

# HTTP 请求速率
rate(flask_http_request_total[1m])
```

### 业务指标（需要在代码中记录）

```promql
# 检测吞吐量（每秒）
rate(detection_total[1m])

# LLM P95 延迟
histogram_quantile(0.95, rate(llm_latency_seconds_bucket[5m]))

# API Key 成功率
avg(api_key_success_rate) by (key_id)
```

---

## ⚠️ 注意事项

### 1. Docker 网络访问

Prometheus 运行在 Docker 容器中，需要通过特殊地址访问宿主机：

- **Windows/Mac Docker Desktop**: `host.docker.internal`
- **Linux**: 使用宿主机 IP 地址

如果 Prometheus 无法访问，编辑 `deployment/prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'flask-app'
    static_configs:
      # Windows/Mac
      - targets: ['host.docker.internal:5000']
      
      # 或使用实际 IP（Linux）
      # - targets: ['192.168.1.100:5000']
```

### 2. 防火墙规则

确保防火墙允许 Docker 容器访问宿主机的 5000 端口：

```powershell
# 查看防火墙状态
Get-NetFirewallProfile

# 如需要，添加规则（管理员权限）
New-NetFirewallRule -DisplayName "Flask App" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow
```

### 3. 性能影响

Prometheus metrics 对性能影响很小，但如果担心：

- 增加抓取间隔（如 60s）
- 仅在生产环境启用
- 使用条件判断：

```python
# 仅在配置启用时暴露 metrics
if settings.enable_prometheus:
    app.wsgi_app = DispatcherMiddleware(...)
```

---

## 🐛 故障排查

### 问题 1: `/metrics` 仍然返回 404

**检查清单**:
```powershell
# 1. 确认 prometheus_client 已安装
pip show prometheus-client

# 2. 确认 app.py 已更新
Get-Content app.py | Select-String "prometheus"

# 3. 重启 Flask 应用
# Ctrl+C 停止，然后重新启动
```

### 问题 2: 指标数据为空

**原因**: 业务指标需要在代码中主动记录。

**解决方案**:
1. 默认只有 Python 运行时指标（process_*, python_*）
2. 业务指标需要集成 `algo/monitoring/metrics.py`
3. 参考 [集成监控指标](#) 章节

### 问题 3: Prometheus 显示 "Context Deadline Exceeded"

**原因**: Flask 应用响应超时。

**解决方案**:
```yaml
# deployment/prometheus.yml
scrape_configs:
  - job_name: 'flask-app'
    scrape_timeout: 10s  # 增加超时时间
```

---

## 📚 相关资源

### 文档
- [Prometheus Client Python](https://github.com/prometheus/client_python) - 官方文档
- [Flask + Prometheus](https://pypi.org/project/prometheus-flask-exporter/) - Flask 集成库（可选）
- [algo/monitoring/metrics.py](algo/monitoring/metrics.py) - 业务指标定义

### 监控界面
- **Prometheus**: http://localhost:9100
- **Grafana**: http://localhost:3100 (admin/admin)
- **Metrics 端点**: http://localhost:5000/metrics

---

## ✅ 验证清单

完成修复后，确认以下项：

- [ ] `pip install prometheus-client` 成功
- [ ] Flask 启动时显示 "Prometheus metrics endpoint enabled"
- [ ] 访问 http://localhost:5000/metrics 返回指标数据（非 404）
- [ ] Prometheus Targets 页面显示 flask-app 状态为 UP
- [ ] 终端不再频繁输出 404 错误
- [ ] 可以在 Prometheus 中查询到 `process_*` 和 `python_*` 指标

---

**问题已解决！** 🎉

现在 Flask 应用正确暴露了 `/metrics` 端点，Prometheus 可以正常抓取指标了。
