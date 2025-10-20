# Logger 日志格式修复说明

## 🐛 问题描述

日志输出显示 `%s` 占位符而不是实际值：

```
2025-10-20 21:32:42.001 | INFO     | algo.rtsp_detect.pipeline:__init__:67 - Kafka streaming enabled for camera %s
2025-10-20 21:32:42.002 | INFO     | algo.rtsp_detect.video_stream:_open_capture:54 - Opening video stream %s
[rtsp @ 000001ad410dbd80] method DESCRIBE failed: 404 Not Found
2025-10-20 21:32:42.354 | WARNING  | algo.rtsp_detect.video_stream:_open_capture:57 - Failed to open video stream %s
```

---

## 🔍 根本原因

**错误的日志格式**：使用了 Python 标准库 `logging` 的 `%s` 占位符，但项目使用的是 `loguru` 库。

### logging vs loguru 格式差异

| 库 | 格式 | 示例 |
|------|------|------|
| **logging** (标准库) | `%s`, `%d`, `%f` | `logger.info("Value: %s", value)` |
| **loguru** (项目使用) | `{}` 或 f-string | `logger.info("Value: {}", value)` |

---

## ✅ 修复方案

### 批量修复工具

创建了 `scripts/fix_logger_format.py` 自动修复工具：

```python
# 修复前
logger.info("Opening video stream %s", self.name)
logger.error("Failed for camera %s: %s", camera_id, exc)

# 修复后
logger.info("Opening video stream {}", self.name)
logger.error("Failed for camera {}: {}", camera_id, exc)
```

### 修复的文件

执行 `python scripts/fix_logger_format.py` 修复了以下文件：

1. **algo/rtsp_detect/pipeline.py** - 9 处
2. **algo/rtsp_detect/video_stream.py** - 4 处
3. **algo/rtsp_detect/session_manager.py** - 2 处
4. **algo/rtsp_detect/yolo_detector.py** - 3 处
5. **routes/ws.py** - 3 处
6. **algo/llm/dangerous_driving_detector.py** - 5 处

**总计**: 26 处日志格式错误

---

## 🚀 验证修复

### 1. 重启应用

```bash
# 停止当前应用 (Ctrl+C)
python app.py
```

### 2. 查看新的日志输出

**修复后的正确日志** ✅:
```
2025-10-20 21:35:00.001 | INFO     | algo.rtsp_detect.pipeline:__init__:67 - Kafka streaming enabled for camera 1
2025-10-20 21:35:00.002 | INFO     | algo.rtsp_detect.video_stream:_open_capture:54 - Opening video stream rtsp://example.com/stream
2025-10-20 21:35:00.354 | WARNING  | algo.rtsp_detect.video_stream:_open_capture:57 - Failed to open video stream rtsp://example.com/stream
```

现在可以看到：
- **摄像头 ID**: `camera 1` 而不是 `camera %s`
- **RTSP URL**: 完整的流地址而不是 `%s`
- **异常信息**: 具体的错误内容而不是 `%s`

---

## 🎯 关于 RTSP 404 错误

### 错误信息

```
[rtsp @ 000001ad410dbd80] method DESCRIBE failed: 404 Not Found
2025-10-20 21:32:42.354 | WARNING  | algo.rtsp_detect.video_stream:_open_capture:57 - Failed to open video stream <URL>
```

### 常见原因

| 原因 | 说明 | 解决方案 |
|------|------|---------|
| **URL 错误** | RTSP 地址拼写错误或路径不存在 | 检查前端传入的 `rtspUrl` |
| **认证失败** | 需要用户名密码但未提供 | 使用 `rtsp://user:pass@ip:port/path` |
| **摄像头离线** | 设备断电或网络不可达 | 检查设备状态 |
| **端口错误** | 默认 RTSP 端口是 554，可能被修改 | 确认正确端口 |
| **协议不支持** | 摄像头可能使用 HTTP-FLV/HLS | 改用对应的协议 |

### 调试方法

#### 1. 使用 VLC 测试

```
媒体 → 打开网络串流 → 输入 RTSP URL
```

如果 VLC 也无法播放，说明 URL 本身有问题。

#### 2. 使用 FFprobe 检查

```bash
ffprobe -rtsp_transport tcp rtsp://your-camera-ip:554/stream
```

#### 3. 检查前端传入的 URL

在 WebSocket 消息中查看 `rtspUrl` 字段：

```json
{
  "type": "start_stream",
  "data": {
    "cameraId": 1,
    "rtspUrl": "rtsp://admin:password@192.168.1.100:554/stream1"
  }
}
```

#### 4. 启用更详细的 OpenCV 日志

```python
# 在 app.py 开头添加
import os
os.environ['OPENCV_FFMPEG_LOGLEVEL'] = '-1'  # 显示所有 FFmpeg 日志
```

---

## 📋 RTSP URL 格式参考

### 标准格式

```
rtsp://[username:password@]host[:port]/path
```

### 常见品牌示例

| 品牌 | 主码流 | 子码流 |
|------|--------|--------|
| **海康威视** | `rtsp://admin:12345@192.168.1.64:554/h264/ch1/main/av_stream` | `rtsp://admin:12345@192.168.1.64:554/h264/ch1/sub/av_stream` |
| **大华** | `rtsp://admin:admin@192.168.1.108:554/cam/realmonitor?channel=1&subtype=0` | `rtsp://admin:admin@192.168.1.108:554/cam/realmonitor?channel=1&subtype=1` |
| **宇视** | `rtsp://admin:admin@192.168.1.100:554/video1` | `rtsp://admin:admin@192.168.1.100:554/video2` |
| **通用 ONVIF** | `rtsp://user:pass@ip:554/onvif1` | `rtsp://user:pass@ip:554/onvif2` |

### 测试用公开流

```bash
# Big Buck Bunny (测试用)
rtsp://wowzaec2demo.streamlock.net/vod/mp4:BigBuckBunny_115k.mp4
```

---

## 🔧 前端集成建议

### 1. URL 验证

在前端发送 `start_stream` 之前验证 URL：

```javascript
function isValidRtspUrl(url) {
  try {
    const urlObj = new URL(url);
    return urlObj.protocol === 'rtsp:';
  } catch {
    return false;
  }
}

// 使用
if (!isValidRtspUrl(rtspUrl)) {
  alert('无效的 RTSP 地址');
  return;
}
```

### 2. 连接超时提示

```javascript
// 发送启动请求后，5 秒内没收到 detection_result 则提示
const timeoutId = setTimeout(() => {
  showError('摄像头连接超时，请检查 RTSP 地址');
}, 5000);

// 收到首帧后清除超时
websocket.addEventListener('message', (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === 'detection_result' && msg.data.cameraId === cameraId) {
    clearTimeout(timeoutId);
  }
});
```

### 3. 提供常用格式模板

```javascript
const rtspTemplates = {
  hikvision: 'rtsp://admin:12345@192.168.1.64:554/h264/ch1/main/av_stream',
  dahua: 'rtsp://admin:admin@192.168.1.108:554/cam/realmonitor?channel=1&subtype=0',
  generic: 'rtsp://username:password@ip:554/stream'
};
```

---

## ✅ 修复确认清单

完成后确认以下项：

- [ ] 日志中显示完整的摄像头 ID（如 `camera 1`）
- [ ] 日志中显示完整的 RTSP URL
- [ ] 日志中显示完整的异常信息
- [ ] 没有看到 `%s` 占位符
- [ ] RTSP URL 格式正确（包含协议、IP、端口、路径）
- [ ] 摄像头设备在线且可访问
- [ ] 使用 VLC 或 FFprobe 验证 URL 可用

---

## 🎉 总结

### 修复内容

1. ✅ **日志格式**: 26 处 `%s` → `{}` 修复完成
2. ✅ **自动化工具**: `scripts/fix_logger_format.py` 可重复使用
3. ✅ **完整文档**: 包含 RTSP 故障排查指南

### 现在可以看到的信息

- 摄像头 ID
- 完整的 RTSP URL
- 详细的错误信息
- 重连尝试次数
- Kafka 发送状态

### 下一步

1. 重启应用查看修复后的日志
2. 检查前端传入的 RTSP URL 是否正确
3. 使用 VLC 验证 URL 可用性
4. 根据日志中的完整 URL 排查连接问题

---

**修复完成！** 🎉 现在日志会显示完整的调试信息。
