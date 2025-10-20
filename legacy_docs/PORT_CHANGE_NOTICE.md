# 端口配置变更说明

## 📋 变更内容

为避免端口冲突，已将监控服务的默认端口进行调整：

| 服务 | 原端口 | 新端口 | 访问地址 |
|-----|-------|-------|---------|
| **Prometheus** | 9090 | **9100** | http://localhost:9100 |
| **Grafana** | 3000 | **3100** | http://localhost:3100 |

---

## 🔧 已更新的文件

### 配置文件
1. ✅ `deployment/docker-compose.infra.yml`
   - Prometheus: `9100:9090` (宿主机端口:容器端口)
   - Grafana: `3100:3000` (宿主机端口:容器端口)
   - Grafana 环境变量: `GF_SERVER_ROOT_URL=http://localhost:3100`

2. ✅ `config/monitoring.yaml`
   - `prometheus.port: 9100`
   - `grafana.url: http://localhost:3100`
   - `grafana.datasources[0].url: http://localhost:9100`

### 文档文件
3. ✅ `KAFKA_INTEGRATION_GUIDE.md`
4. ✅ `DEPLOYMENT_GUIDE.md`
5. ✅ `IMPLEMENTATION_SUMMARY.md`
6. ✅ `STREAMING_OPTIMIZATION.md`
7. ✅ `docs/快速开始指南.md`
8. ✅ `docs/项目总结.md`

---

## 🚀 如何应用变更

### 如果已经启动了服务

**方法 1: 重启基础设施（推荐）**

```bash
# 停止现有服务
cd deployment
docker-compose -f docker-compose.infra.yml down

# 重新启动（使用新端口）
docker-compose -f docker-compose.infra.yml up -d

# 验证端口
docker-compose -f docker-compose.infra.yml ps
```

**方法 2: 仅重启 Prometheus 和 Grafana**

```bash
cd deployment

# 重启单个服务
docker-compose -f docker-compose.infra.yml restart prometheus
docker-compose -f docker-compose.infra.yml restart grafana
```

### 如果首次启动

```bash
cd deployment
docker-compose -f docker-compose.infra.yml up -d
```

---

## ✅ 验证变更

### 1. 检查容器端口映射

```bash
docker ps | grep -E "prometheus|grafana"
```

**预期输出**:
```
traffic-prometheus   ... 0.0.0.0:9100->9090/tcp
traffic-grafana      ... 0.0.0.0:3100->3000/tcp
```

### 2. 访问服务

- **Prometheus**: http://localhost:9100
  - 检查 Targets: http://localhost:9100/targets
  - 执行查询: http://localhost:9100/graph

- **Grafana**: http://localhost:3100
  - 默认账号: `admin` / `admin`
  - 首次登录会要求修改密码

### 3. 测试数据源连接

在 Grafana 中：
1. 进入 **Configuration → Data Sources**
2. 选择 **Prometheus**
3. URL 应该显示: `http://prometheus:9090` (容器内部通信)
4. 点击 **Test** 按钮，应该显示 "Data source is working"

---

## 🔄 其他服务端口（未变更）

以下服务端口保持不变：

| 服务 | 端口 | 说明 |
|-----|------|-----|
| Flask 应用 | 5000 | HTTP API + WebSocket |
| Kafka Broker | 9092 | Kafka 主端口 |
| Kafka JMX | 9093 | JMX 监控端口 |
| Kafka UI | 8080 | Web 管理界面 |
| Zookeeper | 2181 | 集群协调 |
| Redis | 6379 | 缓存和消息 |
| PostgreSQL | 5432 | 数据库 (可选) |

---

## 📝 注意事项

### Grafana 数据源配置

在 Grafana 中配置 Prometheus 数据源时：

- **容器内访问**: 使用 `http://prometheus:9090` (Docker 网络)
- **宿主机访问**: 使用 `http://localhost:9100` (端口映射)

我们的配置文件中使用的是容器名 `prometheus`，这样服务间可以直接通信，无需经过宿主机端口映射。

### 防火墙配置

如果需要从外部访问监控服务，请确保防火墙允许以下端口：

```bash
# Ubuntu/Debian
sudo ufw allow 9100/tcp  # Prometheus
sudo ufw allow 3100/tcp  # Grafana

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=9100/tcp
sudo firewall-cmd --permanent --add-port=3100/tcp
sudo firewall-cmd --reload
```

### Nginx 反向代理

如果使用 Nginx 作为反向代理，需要更新配置：

```nginx
# Prometheus
location /prometheus/ {
    proxy_pass http://localhost:9100/;
}

# Grafana
location /grafana/ {
    proxy_pass http://localhost:3100/;
}
```

---

## 🐛 故障排查

### 问题 1: 端口已被占用

**症状**: 启动失败，提示 "address already in use"

**解决方案**:

```bash
# 检查端口占用
sudo netstat -tulpn | grep -E "9100|3100"
# 或
sudo lsof -i :9100
sudo lsof -i :3100

# 如果端口被占用，停止占用进程或修改端口
```

### 问题 2: Grafana 无法连接 Prometheus

**症状**: Data source test 失败

**解决方案**:

```bash
# 1. 检查容器网络
docker network inspect traffic-network

# 2. 进入 Grafana 容器测试连接
docker exec -it traffic-grafana sh
wget -O- http://prometheus:9090/api/v1/status/config

# 3. 检查 Prometheus 是否正常
curl http://localhost:9100/api/v1/status/config
```

### 问题 3: 无法访问监控页面

**症状**: 浏览器无法打开 http://localhost:9100 或 http://localhost:3100

**解决方案**:

```bash
# 1. 检查容器状态
docker-compose -f deployment/docker-compose.infra.yml ps

# 2. 查看日志
docker logs traffic-prometheus
docker logs traffic-grafana

# 3. 重启服务
docker-compose -f deployment/docker-compose.infra.yml restart prometheus grafana
```

---

## 📚 相关文档

- [KAFKA_INTEGRATION_GUIDE.md](KAFKA_INTEGRATION_GUIDE.md) - Kafka 集成指南
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - 快速部署指南
- [config/monitoring.yaml](config/monitoring.yaml) - 监控配置文件

---

## ✅ 变更确认清单

部署前请确认：

- [ ] 已停止旧版本的服务
- [ ] 已更新 `docker-compose.infra.yml` 文件
- [ ] 已更新 `config/monitoring.yaml` 文件
- [ ] 已重新启动 Docker 容器
- [ ] 可以访问 http://localhost:9100 (Prometheus)
- [ ] 可以访问 http://localhost:3100 (Grafana)
- [ ] Grafana 可以正常连接 Prometheus 数据源

---

**变更完成！** 🎉

如有问题，请查看故障排查章节或提交 Issue。
