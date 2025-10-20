# Prometheus LLM 监控 - 快速参考

## 🎯 问题：histogram_quantile 没有数据

### ✅ 已修复
- ✅ `DangerousDrivingAnalyzer` 现在记录所有 LLM 请求到 Prometheus
- ✅ 成功/失败/重试 状态都会被追踪
- ✅ Token 使用量自动提取
- ✅ 延迟数据记录到 histogram buckets

---

## 📊 快速验证

### 1. 检查 Flask Metrics
```powershell
curl http://localhost:5000/metrics | Select-String "llm_"
```

**预期输出**（如果有 LLM 调用）:
```
llm_latency_seconds_bucket{api_key_id="default",le="0.5",model="qwen-vl-plus"} 0.0
llm_latency_seconds_count{api_key_id="default",model="qwen-vl-plus"} 5.0
llm_requests_total{api_key_id="default",model="qwen-vl-plus",status="success"} 5.0
```

### 2. Prometheus 查询
访问 http://localhost:9100/graph

```promql
# 查看原始数据
llm_requests_total

# P95 延迟
histogram_quantile(0.95, rate(llm_latency_seconds_bucket[5m]))

# 平均延迟
rate(llm_latency_seconds_sum[5m]) / rate(llm_latency_seconds_count[5m])

# 成功率
sum(rate(llm_requests_total{status="success"}[5m])) / sum(rate(llm_requests_total[5m])) * 100
```

---

## ⚠️ 重要：需要触发 LLM 调用

**指标只在实际 LLM 调用时才会产生！**

### 触发条件（全部满足）：
1. ✅ 摄像头流正在运行
2. ✅ 检测到 ≥2 个对象 或 形成交通组
3. ✅ 满足 cooldown 间隔（默认 3 秒）
4. ✅ `model_config.yaml` 中 `llm.enabled: true`
5. ✅ `DASHSCOPE_API_KEY` 环境变量已设置

### 快速测试方法：

**启动摄像头**:
```powershell
# 1. 启动应用
python app.py

# 2. 打开浏览器
# http://localhost:5000

# 3. 添加摄像头并开始检测
# - 输入 RTSP URL 或视频文件路径
# - 点击"开始检测"
# - 确保视频中有多个车辆/行人

# 4. 等待几分钟，让 LLM 分析运行多次
```

**检查日志**（确认 LLM 被调用）:
```
INFO: DashScope API call successful, latency=2.34s
```

---

## 🐛 如果还是没有数据

### 检查清单：

```powershell
# 1. Prometheus 是否正常抓取？
curl http://localhost:9100/api/v1/targets | ConvertFrom-Json

# 2. Flask metrics 端点是否可访问？
curl http://localhost:5000/metrics

# 3. 是否有任何 LLM 请求？
curl http://localhost:5000/metrics | Select-String "llm_requests_total"

# 4. 检查 Flask 日志（查找 LLM 调用）
# 搜索: "DashScope" 或 "analyze"
```

### 常见问题：

| 症状 | 原因 | 解决方案 |
|------|------|----------|
| `llm_requests_total` = 0 | 没有 LLM 调用 | 启动摄像头流，确保检测到对象 |
| Metrics 端点无 `llm_` | 代码未执行 | 重启 Flask 应用 |
| Prometheus 显示 404 | Target 配置错误 | 检查 `prometheus.yml` |
| Bucket 数据为空 | 时间范围太短 | 使用 `[1h]` 而不是 `[5m]` |

---

## 📈 推荐 Grafana 面板

### Panel 1: LLM P95 延迟
```promql
histogram_quantile(0.95, sum(rate(llm_latency_seconds_bucket[5m])) by (le, model))
```

### Panel 2: LLM 请求速率
```promql
sum(rate(llm_requests_total[1m])) by (status)
```

### Panel 3: LLM 成功率
```promql
sum(rate(llm_requests_total{status="success"}[5m])) 
/ 
sum(rate(llm_requests_total[5m])) * 100
```

### Panel 4: Token 使用量
```promql
sum(rate(llm_token_usage_total[5m])) by (token_type)
```

---

## 📝 相关文件

- **修复文件**: `algo/llm/dangerous_driving_detector.py`
- **指标定义**: `algo/monitoring/metrics.py`
- **详细文档**: `PROMETHEUS_NO_DATA_FIX.md`
- **Metrics 端点**: `app.py` (已集成)

---

## 🎉 现在可以：

✅ 追踪 LLM API 延迟（P50/P95/P99）  
✅ 监控 LLM 请求成功率  
✅ 统计 Token 使用量  
✅ 分析 LLM 性能瓶颈  
✅ 设置延迟告警（Grafana Alerts）

**重启应用后立即生效！** 🚀
