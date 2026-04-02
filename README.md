# IP Camera Viewer - 局域网摄像头监控平台

一个基于 Web 的低延迟 IP 摄像头监控解决方案，支持自动发现局域网内的摄像头并提供实时视频流查看。

## 特性

- 🔍 **自动发现**: 通过 ONVIF 协议和 RTSP 扫描自动发现局域网内的摄像头
- ⚡ **低延迟**: 使用 MJPEG over HTTP 技术，延迟低至 100-200ms
- 🖥️ **多画面**: 支持 1x1 到 4x4 多种布局
- 🔧 **手动添加**: 支持手动输入 RTSP 地址添加摄像头
- 📱 **响应式设计**: 支持桌面和移动设备
- 🔄 **自动重连**: 摄像头断线后自动重连

## 系统要求

- Python 3.8+
- OpenCV (with FFmpeg support)
- Flask

## 快速开始

### 1. 安装依赖

```bash
pip install flask opencv-python requests netifaces
```

### 2. 启动服务

**Linux/macOS:**
```bash
./start.sh
```

**Windows:**
```bash
start.bat
```

或直接运行：
```bash
python main.py
```

### 3. 访问界面

打开浏览器访问:
- 本地: http://localhost:5000
- 局域网: http://你的IP:5000

## 使用方法

### 自动扫描摄像头

1. 点击页面顶部的"扫描网络"按钮
2. 等待扫描完成（通常需要 1-2 分钟）
3. 在扫描结果中选择要添加的摄像头

### 手动添加摄像头

1. 点击"添加摄像头"按钮
2. 输入摄像头名称和 RTSP 地址
3. 如有需要，输入用户名和密码
4. 点击"添加"

### 常见 RTSP 地址格式

| 品牌 | 主码流 | 子码流 |
|-----|-------|-------|
| 海康威视 | `rtsp://admin:password@IP:554/Streaming/Channels/101` | `rtsp://admin:password@IP:554/Streaming/Channels/102` |
| 大华 | `rtsp://admin:password@IP:554/cam/realmonitor?channel=1&subtype=0` | `rtsp://admin:password@IP:554/cam/realmonitor?channel=1&subtype=1` |
| 宇视 | `rtsp://admin:password@IP:554/video1` | `rtsp://admin:password@IP:554/video2` |
| TP-Link | `rtsp://admin:password@IP:554/stream1` | `rtsp://admin:password@IP:554/stream2` |

## 配置文件

`config.json` 包含以下可配置项:

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 5000
  },
  "discovery": {
    "scan_timeout": 2,
    "common_credentials": [
      {"username": "admin", "password": "admin"},
      {"username": "admin", "password": "123456"}
    ]
  },
  "streaming": {
    "jpeg_quality": 70,
    "max_fps": 25
  }
}
```

## 项目结构

```
ip_camera_viewer/
├── main.py              # 主程序入口
├── camera_discovery.py  # 摄像头发现模块
├── stream_server.py     # 视频流服务
├── config.json          # 配置文件
├── web/
│   ├── templates/       # HTML模板
│   └── static/          # CSS/JS资源
├── start.sh             # Linux/macOS启动脚本
└── start.bat            # Windows启动脚本
```

## 技术说明

### 低延迟实现

1. **MJPEG over HTTP**: 相比 HLS(1-3秒延迟)，MJPEG 延迟仅 100-200ms
2. **小缓冲区**: OpenCV 缓冲区设置为最小 (1帧)
3. **FFmpeg 优化参数**: 使用 `-fflags nobuffer -flags low_delay`
4. **直接推送**: 服务端直接推送 JPEG 帧，无转码延迟

### 支持的协议

- ONVIF 发现
- RTSP/RTP
- HTTP/MJPEG (部分摄像头)

## 故障排除

### 摄像头无法连接

1. 确认摄像头 IP 可访问: `ping 摄像头IP`
2. 确认 RTSP 端口开放: `telnet 摄像头IP 554`
3. 检查用户名密码是否正确
4. 尝试使用子码流（带宽要求更低）

### 视频卡顿

1. 降低 JPEG 质量 (`config.json` 中 `jpeg_quality`)
2. 使用子码流
3. 检查网络带宽

### 扫描不到摄像头

1. 确认摄像头和服务器在同一网段
2. 检查摄像头是否开启 ONVIF 协议
3. 手动指定 IP 范围:
   ```python
   # 在 main.py 中修改
   cameras = discovery.scan_network(network="192.168.1.0/24")
   ```

## 安全提示

- 建议在局域网内部署使用
- 如需公网访问，请配置 HTTPS 和身份验证
- 定期更换摄像头默认密码

## License

MIT License
