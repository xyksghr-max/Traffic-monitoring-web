# Prometheus LLM 指标无数据问题修复

## 🐛 问题描述

在 Prometheus 中执行查询：
```promql
histogram_quantile(0.95, rate(llm_latency_seconds_bucket[5m]))
```

**结果**: 没有数据返回

---

## 🔍 问题根本原因

### 原因 1: **指标未被记录** ⚠️

`DangerousDrivingAnalyzer` 在调用 LLM API 后，**没有调用 `record_llm_request()`** 将指标记录到 Prometheus。

**问题代码** (`algo/llm/dangerous_driving_detector.py`):
```python
# ❌ 缺少 Prometheus 集成
response = self._client.chat.completions.create(...)
parsed["latency"] = time.time() - start_time
return parsed  # 没有记录到 Prometheus！
```

### 原因 2: **需要实际的 LLM 调用**

即使修复了代码，histogram 指标也只在**真正调用 LLM** 时才会产生数据：

**触发条件**:
1. ✅ 启动摄像头流（WebSocket 连接）
2. ✅ 检测到 ≥2 个对象 或 形成交通组
3. ✅ 满足 cooldown 间隔（默认 3 秒）
4. ✅ LLM 分析功能已启用（`model_config.yaml` 中 `llm.enabled: true`）
5. ✅ `DASHSCOPE_API_KEY` 已配置

**如果没有实际 LLM 调用，就不会有数据！**

---

## ✅ 解决方案

### 修复 1: 集成 Prometheus 指标记录

**已修复文件**: `algo/llm/dangerous_driving_detector.py`

#### 1.1 导入 metrics 模块

```python
# Import Prometheus metrics (optional)
try:
    from algo.monitoring.metrics import record_llm_request
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    logger.warning("Prometheus metrics not available for LLM monitoring")
```

#### 1.2 记录成功的请求

```python
# 在 LLM 调用成功后
latency = time.time() - start_time

if METRICS_AVAILABLE:
    usage = getattr(response, 'usage', None)
    prompt_tokens = getattr(usage, 'prompt_tokens', 0) if usage else 0
    completion_tokens = getattr(usage, 'completion_tokens', 0) if usage else 0
    
    record_llm_request(
        model=self.config.model,
        api_key_id='default',
        latency=latency,
        status='success',
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens
    )
```

#### 1.3 记录失败的请求

```python
# 捕获异常时
except Exception as exc:
    latency = time.time() - start_time
    if METRICS_AVAILABLE:
        record_llm_request(
            model=self.config.model,
            api_key_id='default',
            latency=latency,
            status='error'
        )
```

---

### 修复 2: 触发 LLM 调用以生成数据

#### 方法 1: 使用真实摄像头流（推荐）

```powershell
# 1. 启动 Flask 应用
python app.py

# 2. 打开前端页面
# 访问: http://localhost:5000

# 3. 添加摄像头并启动
# - 点击"添加摄像头"
# - 输入 RTSP URL（或使用测试视频）
# - 点击"开始检测"

# 4. 等待检测到对象
# - 至少需要 2 个对象或形成交通组
# - 每次 LLM 调用间隔 3 秒
```

#### 方法 2: 使用测试视频文件

```powershell
# 准备测试视频
# 将包含车辆/行人的视频文件放到项目中

# 在前端 RTSP URL 输入框中使用本地文件
# 例如: /path/to/test_traffic.mp4
```

#### 方法 3: 使用模拟数据（开发测试）

创建测试脚本 `test_llm_metrics.py`:

```python
import time
from algo.llm.dangerous_driving_detector import DangerousDrivingAnalyzer, DangerousDrivingConfig
from algo.monitoring.metrics import record_llm_request

# 配置
config = DangerousDrivingConfig(
    model="qwen-vl-plus",
    timeout=30,
    max_retry=2
)

analyzer = DangerousDrivingAnalyzer(config, enabled=True)

# 模拟检测数据
detections = [
    {"class": "car", "confidence": 0.95, "bbox": [100, 100, 200, 200]},
    {"class": "person", "confidence": 0.92, "bbox": [150, 150, 180, 250]},
]

groups = [
    {
        "groupIndex": 1,
        "objectCount": 2,
        "classes": ["car", "person"],
        "bbox": [100, 100, 200, 250],
        "memberIndices": [0, 1]
    }
]

group_images = [
    {
        "groupIndex": 1,
        "objectCount": 2,
        "classes": ["car", "person"],
        "dataUri": "data:image/jpeg;base64,..."  # 需要实际图片
    }
]

# 触发 LLM 分析
if analyzer.should_analyze(detections, groups, group_images):
    result = analyzer.analyze(group_images, detections, groups)
    print(f"LLM Analysis Result: {result}")
    print(f"Latency: {result.get('latency', 0):.2f}s")
```

运行测试：
```powershell
python test_llm_metrics.py
```

---

## 🔍 验证修复

### 1. 检查指标是否被记录

访问 Flask metrics 端点：
```powershell
curl http://localhost:5000/metrics | Select-String "llm_latency"
```

**预期输出**（如果有 LLM 调用）:
```
# HELP llm_latency_seconds LLM API request latency in seconds
# TYPE llm_latency_seconds histogram
llm_latency_seconds_bucket{api_key_id="default",le="0.5",model="qwen-vl-plus"} 0.0
llm_latency_seconds_bucket{api_key_id="default",le="1.0",model="qwen-vl-plus"} 1.0
llm_latency_seconds_bucket{api_key_id="default",le="2.0",model="qwen-vl-plus"} 3.0
llm_latency_seconds_bucket{api_key_id="default",le="5.0",model="qwen-vl-plus"} 5.0
llm_latency_seconds_bucket{api_key_id="default",le="10.0",model="qwen-vl-plus"} 5.0
llm_latency_seconds_bucket{api_key_id="default",le="30.0",model="qwen-vl-plus"} 5.0
llm_latency_seconds_bucket{api_key_id="default",le="+Inf",model="qwen-vl-plus"} 5.0
llm_latency_seconds_count{api_key_id="default",model="qwen-vl-plus"} 5.0
llm_latency_seconds_sum{api_key_id="default",model="qwen-vl-plus"} 12.3456
```

**如果没有输出**，说明：
- ❌ 没有发生 LLM 调用
- ❌ 指标记录代码未执行

---

### 2. 在 Prometheus 中查询

访问 Prometheus UI: http://localhost:9100

#### 基础查询（查看原始数据）

```promql
# 查看是否有 llm_latency 指标
llm_latency_seconds_bucket

# 查看 LLM 请求总数
llm_requests_total

# 查看成功的请求数
llm_requests_total{status="success"}
```

**如果返回 "No data"**:
1. 检查 Prometheus 是否正常抓取 Flask metrics
2. 访问 **Status → Targets**，确认 `flask-app` 状态为 **UP**
3. 确认已经触发了 LLM 调用（检查 Flask 日志）

#### P95 延迟查询

```promql
# P95 延迟（需要至少有一些数据点）
histogram_quantile(0.95, rate(llm_latency_seconds_bucket[5m]))

# 平均延迟
rate(llm_latency_seconds_sum[5m]) / rate(llm_latency_seconds_count[5m])

# 请求速率（每秒）
rate(llm_requests_total{status="success"}[1m])
```

---

### 3. 查看 Flask 日志

启动应用时，应该看到：
```
2025-10-20 21:40:00.123 | INFO     | algo.monitoring.metrics:<module>:260 - Prometheus metrics initialized
2025-10-20 21:40:05.456 | INFO     | app:create_app:45 - Prometheus metrics endpoint enabled at /metrics
```

触发 LLM 分析时：
```
2025-10-20 21:40:30.789 | INFO     | algo.llm.dangerous_driving_detector:analyze:115 - DashScope API call successful, latency=2.34s
```

---

## 📊 完整监控流程

### 1. 启动监控基础设施

```powershell
cd deployment
docker-compose -f docker-compose.infra.yml up -d prometheus grafana
```

### 2. 启动 Flask 应用

```powershell
# 确保安装了 prometheus-client
pip install prometheus-client>=0.19.0

# 启动应用
python app.py
```

### 3. 验证 Prometheus 连接

访问 http://localhost:9100/targets

确认 `flask-app` 目标：
- **State**: UP ✅
- **Labels**: `job="flask-app"`
- **Last Scrape**: 几秒前

### 4. 触发 LLM 调用

**方式 1**: 通过 WebSocket 启动摄像头

```javascript
// 在浏览器控制台
ws = new WebSocket('ws://localhost:5000/ws');
ws.onopen = () => {
    ws.send(JSON.stringify({
        type: 'start_stream',
        data: {
            cameraId: 1,
            rtspUrl: 'rtsp://your-camera-url'
        }
    }));
};
```

**方式 2**: 直接调用 Python API

```python
from algo.llm.dangerous_driving_detector import DangerousDrivingAnalyzer, DangerousDrivingConfig

config = DangerousDrivingConfig()
analyzer = DangerousDrivingAnalyzer(config)

# 准备测试数据（需要实际图片）
result = analyzer.analyze(group_images, detections, groups)
```

### 5. 查询 Prometheus 指标

等待 1-2 分钟后（让 Prometheus 抓取数据），执行查询：

```promql
# 查看所有 LLM 指标
{__name__=~"llm_.*"}

# P50/P95/P99 延迟
histogram_quantile(0.50, rate(llm_latency_seconds_bucket[5m]))
histogram_quantile(0.95, rate(llm_latency_seconds_bucket[5m]))
histogram_quantile(0.99, rate(llm_latency_seconds_bucket[5m]))

# LLM 错误率
rate(llm_requests_total{status!="success"}[5m]) / rate(llm_requests_total[5m])
```

---

## 🐛 故障排查

### 问题 1: `/metrics` 返回空的 LLM 指标

**检查清单**:
```powershell
# 1. 确认指标已注册
curl http://localhost:5000/metrics | Select-String "llm_"

# 2. 检查是否有 LLM 调用
# 查看 Flask 日志，搜索 "DashScope"

# 3. 确认 Prometheus metrics 已导入
python -c "from algo.monitoring.metrics import llm_latency; print(llm_latency)"
```

**原因**: 没有触发 LLM 调用，或代码中没有调用 `record_llm_request()`

---

### 问题 2: Prometheus 查询返回 "No datapoints found"

**可能原因**:

#### A. 时间范围太短
```promql
# ❌ 5分钟内可能没有足够数据
histogram_quantile(0.95, rate(llm_latency_seconds_bucket[5m]))

# ✅ 尝试更长时间范围
histogram_quantile(0.95, rate(llm_latency_seconds_bucket[1h]))
```

#### B. Histogram bucket 没有数据
```promql
# 先检查是否有任何 bucket 数据
llm_latency_seconds_bucket

# 检查总请求数
llm_latency_seconds_count
```

#### C. 标签不匹配
```promql
# ❌ 如果指定了不存在的标签
histogram_quantile(0.95, rate(llm_latency_seconds_bucket{model="gpt-4"}[5m]))

# ✅ 先查看可用标签
llm_latency_seconds_bucket{model="qwen-vl-plus"}
```

---

### 问题 3: Histogram 只有一个数据点

**原因**: LLM 调用频率太低

**解决方案**:
1. 降低 cooldown 时间（`model_config.yaml`）:
   ```yaml
   llm:
     cooldown_seconds: 1.0  # 从 3.0 减少到 1.0
   ```

2. 启动多个摄像头流

3. 使用循环脚本生成测试数据：
   ```python
   import time
   for i in range(10):
       result = analyzer.analyze(...)
       print(f"Request {i+1}: latency={result['latency']:.2f}s")
       time.sleep(2)
   ```

---

## 📈 Grafana 仪表板配置

### 添加 LLM 延迟面板

1. 访问 Grafana: http://localhost:3100
2. 登录（admin/admin）
3. 创建新 Dashboard
4. 添加 Panel，配置查询：

**P95 延迟**:
```promql
histogram_quantile(0.95, sum(rate(llm_latency_seconds_bucket[5m])) by (le, model))
```

**平均延迟**:
```promql
rate(llm_latency_seconds_sum[5m]) / rate(llm_latency_seconds_count[5m])
```

**请求成功率**:
```promql
sum(rate(llm_requests_total{status="success"}[5m])) 
/ 
sum(rate(llm_requests_total[5m])) * 100
```

**延迟热力图（Heatmap）**:
```promql
sum(increase(llm_latency_seconds_bucket[1m])) by (le)
```

---

## ✅ 验证清单

完成修复后，确认以下项：

- [ ] `algo/llm/dangerous_driving_detector.py` 已导入 `record_llm_request`
- [ ] 成功的 LLM 调用会记录 `status='success'`
- [ ] 失败的 LLM 调用会记录 `status='error'`
- [ ] Token 使用量被正确提取和记录
- [ ] Flask `/metrics` 端点显示 `llm_latency_seconds_bucket` 指标
- [ ] Prometheus 能成功抓取 Flask metrics（Targets 页面显示 UP）
- [ ] 至少触发了几次 LLM 调用（检查 `llm_requests_total` > 0）
- [ ] Prometheus 查询 `llm_latency_seconds_bucket` 返回数据
- [ ] `histogram_quantile(...)` 查询返回有效值（非空）

---

## 🎯 快速测试命令

```powershell
# 1. 检查 Flask metrics
curl http://localhost:5000/metrics | Select-String "llm_"

# 2. 检查 Prometheus 连接
curl http://localhost:9100/api/v1/targets | ConvertFrom-Json | Select-Object -ExpandProperty data | Select-Object -ExpandProperty activeTargets | Where-Object { $_.labels.job -eq "flask-app" }

# 3. 查询 LLM 请求总数
curl "http://localhost:9100/api/v1/query?query=llm_requests_total" | ConvertFrom-Json | Select-Object -ExpandProperty data | Select-Object -ExpandProperty result

# 4. 查询 P95 延迟
curl "http://localhost:9100/api/v1/query?query=histogram_quantile(0.95,%20rate(llm_latency_seconds_bucket[5m]))" | ConvertFrom-Json | Select-Object -ExpandProperty data | Select-Object -ExpandProperty result
```

---

## 📚 相关文档

- [PROMETHEUS_METRICS_FIX.md](PROMETHEUS_METRICS_FIX.md) - Metrics 端点配置
- [algo/monitoring/metrics.py](algo/monitoring/metrics.py) - 指标定义
- [Prometheus Histogram](https://prometheus.io/docs/practices/histograms/) - 官方文档

---

**修复完成！** 🎉

现在 LLM 调用会自动记录到 Prometheus，可以查询延迟分位数了。

**重要提示**: 必须有**实际的 LLM 调用**才会产生数据，请确保：
1. ✅ 摄像头流正在运行
2. ✅ 检测到足够的对象
3. ✅ LLM 功能已启用
4. ✅ API Key 已配置
