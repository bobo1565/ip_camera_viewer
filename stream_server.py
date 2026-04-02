#!/usr/bin/env python3
"""
Low-latency MJPEG Streaming Server
Uses OpenCV to capture RTSP and serve as MJPEG over HTTP
"""

import cv2
import threading
import time
import json
from typing import Dict, Optional, Callable
from collections import deque
import numpy as np


class CameraStream:
    """单个摄像头的视频流处理"""
    
    def __init__(self, camera_id: str, rtsp_url: str, config: Dict):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.config = config
        
        self.cap: Optional[cv2.VideoCapture] = None
        self.cap_lock = threading.Lock()  # 保护 cv2.VideoCapture 的线程安全锁
        self.is_running = False
        self.is_connected = False
        self.frame: Optional[np.ndarray] = None
        self.frame_lock = threading.Lock()
        
        # 统计信息
        self.fps = 0
        self.frame_count = 0
        self.last_fps_time = time.time()
        self.error_count = 0
        self.last_frame_time = 0
        
        # 使用双缓冲减少延迟
        self.frame_buffer = deque(maxlen=config.get('buffer_size', 2))
        
        self.capture_thread: Optional[threading.Thread] = None
        self.is_main = False # 主窗口标志，提供更高刷新率
        
    def start(self) -> bool:
        """启动视频流"""
        if self.is_running:
            return True
        
        try:
            # 配置FFmpeg参数以优化延迟
            with self.cap_lock:
                self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                
                # 设置缓冲区大小为最小
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                # 设置超时
                timeout_ms = self.config.get('connection_timeout', 10) * 1000
                self.cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms)
                self.cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000)
                
                if not self.cap.isOpened():
                    print(f"[Stream {self.camera_id}] 无法打开RTSP流: {self.rtsp_url}")
                    self.cap.release()
                    self.cap = None
                    return False
            
            self.is_running = True
            self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.capture_thread.start()
            
            # 等待第一帧
            wait_start = time.time()
            while time.time() - wait_start < 5:
                with self.frame_lock:
                    if self.frame is not None:
                        self.is_connected = True
                        print(f"[Stream {self.camera_id}] 连接成功")
                        return True
                time.sleep(0.1)
            
            print(f"[Stream {self.camera_id}] 等待第一帧超时")
            return False
            
        except Exception as e:
            print(f"[Stream {self.camera_id}] 启动错误: {e}")
            self.error_count += 1
            return False
    
    def _capture_loop(self):
        """视频捕获线程"""
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        while self.is_running:
            try:
                # 在持有 cap_lock 的情况下读取帧，防止 stop/reconnect 并发释放
                with self.cap_lock:
                    if self.cap is None or not self.cap.isOpened():
                        cap_ok = False
                    else:
                        ret, frame = self.cap.read()
                        cap_ok = True
                
                if not cap_ok:
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        print(f"[Stream {self.camera_id}] 连接断开，尝试重连...")
                        self._reconnect()
                        consecutive_errors = 0
                    time.sleep(0.5)
                    continue
                
                if not ret or frame is None:
                    consecutive_errors += 1
                    time.sleep(0.01)
                    continue
                
                consecutive_errors = 0
                self.error_count = 0
                
                # 更新帧
                with self.frame_lock:
                    self.frame = frame
                    self.last_frame_time = time.time()
                
                self.frame_count += 1
                
                # 计算FPS
                current_time = time.time()
                if current_time - self.last_fps_time >= 1.0:
                    self.fps = self.frame_count
                    self.frame_count = 0
                    self.last_fps_time = current_time
                
                # 控制帧率避免CPU过高：主力窗口跑满，其他副窗口降帧(约20FPS上限)降低整体延迟
                if self.is_main:
                    time.sleep(0.001)
                else:
                    time.sleep(0.05)
                
            except Exception as e:
                print(f"[Stream {self.camera_id}] 捕获错误: {e}")
                consecutive_errors += 1
                time.sleep(0.1)
    
    def _reconnect(self):
        """重新连接"""
        try:
            with self.cap_lock:
                if self.cap:
                    self.cap.release()
                    self.cap = None
                
                self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            print(f"[Stream {self.camera_id}] 重连完成")
        except Exception as e:
            print(f"[Stream {self.camera_id}] 重连失败: {e}")
    
    def get_frame(self) -> Optional[np.ndarray]:
        """获取当前帧"""
        with self.frame_lock:
            if self.frame is not None:
                return self.frame.copy()
        return None
    
    def get_jpeg_bytes(self, quality: int = None) -> Optional[bytes]:
        """获取JPEG编码的图像字节"""
        frame = self.get_frame()
        if frame is None:
            return None
        
        if quality is None:
            quality = self.config.get('jpeg_quality', 70)
        
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        ret, jpeg = cv2.imencode('.jpg', frame, encode_params)
        
        if ret:
            return jpeg.tobytes()
        return None
    
    def get_status(self) -> Dict:
        """获取流状态"""
        with self.frame_lock:
            frame_age = time.time() - self.last_frame_time if self.last_frame_time > 0 else -1
        
        return {
            'camera_id': self.camera_id,
            'is_running': self.is_running,
            'is_connected': self.is_connected and frame_age < 5,
            'fps': self.fps,
            'error_count': self.error_count,
            'frame_age': frame_age,
            'rtsp_url': self.rtsp_url
        }
    
    def stop(self):
        """停止视频流"""
        self.is_running = False
        if self.capture_thread:
            self.capture_thread.join(timeout=3)
        # 捕获线程退出后再释放，保证不会与 cap.read() 并发
        with self.cap_lock:
            if self.cap:
                self.cap.release()
                self.cap = None
        print(f"[Stream {self.camera_id}] 已停止")


class StreamManager:
    """管理多个摄像头的视频流"""
    
    def __init__(self, config_path: str = "config.json"):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        self.streams: Dict[str, CameraStream] = {}
        self.lock = threading.Lock()
    
    def add_camera(self, camera_id: str, rtsp_url: str) -> bool:
        """添加摄像头"""
        with self.lock:
            if camera_id in self.streams:
                # 如果URL改变，停止旧流
                if self.streams[camera_id].rtsp_url != rtsp_url:
                    self.streams[camera_id].stop()
                    del self.streams[camera_id]
                else:
                    return True
            
            stream = CameraStream(camera_id, rtsp_url, self.config['streaming'])
            if stream.start():
                self.streams[camera_id] = stream
                return True
            return False
    
    def remove_camera(self, camera_id: str):
        """移除摄像头"""
        with self.lock:
            if camera_id in self.streams:
                self.streams[camera_id].stop()
                del self.streams[camera_id]
    
    def get_stream(self, camera_id: str) -> Optional[CameraStream]:
        """获取视频流"""
        with self.lock:
            return self.streams.get(camera_id)
    
    def get_all_streams(self) -> Dict[str, CameraStream]:
        """获取所有视频流"""
        with self.lock:
            return dict(self.streams)
    
    def get_all_status(self) -> Dict:
        """获取所有流状态"""
        with self.lock:
            return {cid: stream.get_status() for cid, stream in self.streams.items()}
    
    def stop_all(self):
        """停止所有流"""
        with self.lock:
            for stream in self.streams.values():
                stream.stop()
            self.streams.clear()


# Flask路由需要的生成器函数
def generate_mjpeg(stream: CameraStream, quality: int = 70):
    """生成MJPEG流的生成器"""
    boundary = "--frameboundary"
    
    while stream.is_running:
        jpeg_bytes = stream.get_jpeg_bytes(quality)
        
        if jpeg_bytes:
            yield (b'--' + boundary.encode() + b'\r\n'
                   b'Content-Type: image/jpeg\r\n'
                   b'Content-Length: ' + str(len(jpeg_bytes)).encode() + b'\r\n'
                   b'\r\n' + jpeg_bytes + b'\r\n')
        else:
            # 如果没有帧，发送一个小延迟
            time.sleep(0.01)


if __name__ == "__main__":
    # 测试代码
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python stream_server.py <rtsp_url>")
        sys.exit(1)
    
    rtsp_url = sys.argv[1]
    print(f"测试RTSP流: {rtsp_url}")
    
    manager = StreamManager()
    
    if manager.add_camera("test", rtsp_url):
        print("流启动成功，按Ctrl+C停止")
        try:
            while True:
                status = manager.get_all_status()
                for cid, st in status.items():
                    print(f"\r{cid}: FPS={st['fps']}, Connected={st['is_connected']}", end="")
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    else:
        print("流启动失败")
    
    manager.stop_all()
