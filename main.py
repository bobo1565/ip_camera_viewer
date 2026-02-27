#!/usr/bin/env python3
"""
IP Camera Viewer - Main Application
低延迟局域网摄像头监控平台
"""

import os
import sys
import json
import uuid
import threading
import time
from typing import Dict, List
from datetime import datetime

from flask import Flask, render_template, jsonify, Response, request
from flask_cors import CORS

from camera_discovery import CameraDiscovery
from stream_server import StreamManager, generate_mjpeg

# 配置Flask
app = Flask(__name__, 
            template_folder='web/templates',
            static_folder='web/static')
CORS(app)

# 添加安全头部
@app.after_request
def add_security_headers(response):
    """添加安全相关的HTTP头部"""
    # Content Security Policy - 允许本地资源和内联脚本
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "font-src 'self'; "
    )
    # 其他安全头部
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    return response

# 全局实例
discovery: CameraDiscovery = None
stream_manager: StreamManager = None
cameras_db: Dict[str, Dict] = {}
DB_FILE = "cameras_db.json"

# 扫描任务状态 - 使用原子操作而不是锁
scan_status = {
    'is_scanning': False,
    'progress': 0,
    'total': 0,
    'found': 0,
    'last_result': [],
    'message': '',
}

# 简单的文件锁用于数据库操作
db_lock = threading.Lock()


def load_cameras_db():
    """从文件加载摄像头数据库"""
    global cameras_db
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                cameras_db = json.load(f)
            print(f"[DB] 已加载 {len(cameras_db)} 个摄像头")
        except Exception as e:
            print(f"[DB] 加载失败: {e}")
            cameras_db = {}


def save_cameras_db():
    """保存摄像头数据库到文件"""
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(cameras_db, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[DB] 保存失败: {e}")


def init_camera_streams():
    """初始化时不自动启动任何流，改为按需启动以降低延迟和资源占用"""
    pass


def scan_task():
    """后台扫描任务"""
    global scan_status
    
    # 重置状态
    scan_status['is_scanning'] = True
    scan_status['progress'] = 0
    scan_status['total'] = 100
    scan_status['found'] = 0
    scan_status['message'] = '正在扫描ONVIF设备...'
    scan_status['last_result'] = []
    
    try:
        print("[Scan] 开始后台扫描...")
        
        # ONVIF多播发现
        scan_status['message'] = '正在发现ONVIF设备...'
        onvif_cameras = discovery.onvif_discovery(timeout=2)
        print(f"[Scan] ONVIF发现 {len(onvif_cameras)} 个设备")
        
        # 获取每个设备的RTSP流
        scan_status['message'] = f'发现 {len(onvif_cameras)} 个设备，正在获取视频流...'
        scan_status['total'] = len(onvif_cameras)
        
        cameras = []
        credentials = [{'username': 'admin', 'password': 'admin'}]
        
        for i, cam in enumerate(onvif_cameras):
            ip = cam['ip']
            scan_status['progress'] = i + 1
            scan_status['message'] = f'正在获取视频流: {ip}'
            
            # 快速检查RTSP
            stream_found = False
            for port in [554, 8554]:
                if stream_found:
                    break
                for cred in credentials:
                    url = discovery.try_rtsp_url(ip, port, '/Streaming/Channels/101', 
                                                cred['username'], cred['password'], 2)
                    if url:
                        cam['stream_url'] = url
                        cam['rtsp'] = {'rtsp_url': url, 'auth_required': True, **cred}
                        stream_found = True
                        print(f"[Scan] ✓ {ip} 成功")
                        break
            
            if stream_found:
                cameras.append(cam)
            
            scan_status['found'] = len(cameras)
        
        # 去重并分配ID
        seen_ips = set()
        unique_cameras = []
        for cam in cameras:
            ip = cam.get('ip')
            if ip and ip not in seen_ips:
                seen_ips.add(ip)
                cam['id'] = ip
                if 'stream_url' not in cam and 'rtsp' in cam:
                    cam['stream_url'] = cam['rtsp'].get('rtsp_url', '')
                unique_cameras.append(cam)
        
        # 同步到 discovery.discovered_cameras
        discovery.discovered_cameras = unique_cameras
        scan_status['last_result'] = unique_cameras
        scan_status['message'] = f'扫描完成，发现 {len(unique_cameras)} 个摄像头'
        
        print(f"[Scan] 扫描完成，发现 {len(unique_cameras)} 个摄像头")
    except Exception as e:
        print(f"[Scan] 扫描出错: {e}")
        import traceback
        traceback.print_exc()
        scan_status['message'] = f'扫描出错: {str(e)}'
    finally:
        scan_status['is_scanning'] = False


# ==================== Web Routes ====================

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/api/cameras')
def get_cameras():
    """获取所有摄像头列表"""
    result = []
    for cam_id, cam_data in cameras_db.items():
        cam_info = {
            'id': cam_id,
            'name': cam_data.get('name', f'Camera {cam_id}'),
            'ip': cam_data.get('ip', ''),
            'type': cam_data.get('type', 'RTSP'),
            'stream_url': cam_data.get('stream_url', ''),
            'is_online': cam_id in stream_manager.get_all_streams()
        }
        result.append(cam_info)
    return jsonify(result)


@app.route('/api/cameras', methods=['POST'])
def add_camera():
    """添加摄像头"""
    data = request.json
    
    if not data or 'stream_url' not in data:
        return jsonify({'success': False, 'error': '缺少RTSP地址'})
    
    cam_id = str(uuid.uuid4())[:8]
    
    # 解析IP
    import urllib.parse
    parsed = urllib.parse.urlparse(data['stream_url'])
    
    # 保存到数据库
    with db_lock:
        cameras_db[cam_id] = {
            'id': cam_id,
            'name': data.get('name', f'Camera {cam_id}'),
            'ip': parsed.hostname or '',
            'stream_url': data['stream_url'],
            'username': data.get('username', ''),
            'password': data.get('password', ''),
            'added_time': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        save_cameras_db()
    
    return jsonify({'success': True, 'camera': cameras_db[cam_id]})


@app.route('/api/cameras/<cam_id>', methods=['DELETE'])
def remove_camera(cam_id):
    """删除摄像头"""
    with db_lock:
        if cam_id in cameras_db:
            del cameras_db[cam_id]
            save_cameras_db()
    
    stream_manager.remove_camera(cam_id)
    return jsonify({'success': True})


@app.route('/api/cameras/add', methods=['POST'])
def add_camera_manual():
    """手动添加摄像头（表单提交）"""
    return add_camera()


@app.route('/api/cameras/<cam_id>/add', methods=['POST'])
def add_discovered_camera(cam_id):
    """添加发现的摄像头"""
    print(f"[API] 添加摄像头请求: {cam_id}")
    
    # 从扫描结果中查找
    scan_results = scan_status['last_result']
    print(f"[API] 扫描结果中有 {len(scan_results)} 个摄像头")
    
    cam = None
    for c in scan_results:
        if c.get('id') == cam_id or c.get('ip') == cam_id:
            cam = c
            break
    
    if not cam:
        print(f"[API] 摄像头 {cam_id} 未找到")
        return jsonify({'success': False, 'error': '摄像头未找到，请重新扫描'})
    
    if 'stream_url' not in cam or not cam['stream_url']:
        return jsonify({'success': False, 'error': '该摄像头没有可用的流地址'})
    
    # 生成新ID
    new_id = str(uuid.uuid4())[:8]
    print(f"[API] 生成新ID: {new_id}")
    
    try:
        # 保存到数据库
        with db_lock:
            cameras_db[new_id] = {
                'id': new_id,
                'name': cam.get('name', f'Camera {cam["ip"]}'),
                'ip': cam.get('ip', ''),
                'stream_url': cam['stream_url'],
                'type': cam.get('type', 'RTSP'),
                'added_time': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            save_cameras_db()
        
        print(f"[API] 摄像头 {new_id} 已保存到数据库")
        
        return jsonify({'success': True, 'camera': cameras_db[new_id]})
    except Exception as e:
        print(f"[API] 保存失败: {e}")
        return jsonify({'success': False, 'error': f'保存失败: {str(e)}'})


@app.route('/api/scan', methods=['POST'])
def start_scan():
    """启动异步扫描"""
    global scan_status
    
    if scan_status['is_scanning']:
        return jsonify({
            'success': False,
            'error': '扫描正在进行中',
            'status': scan_status
        })
    
    # 清空上次结果
    scan_status['last_result'] = []
    
    # 启动后台扫描线程
    scan_thread = threading.Thread(target=scan_task, daemon=True)
    scan_thread.start()
    
    return jsonify({
        'success': True,
        'message': '扫描已启动',
        'status': {'is_scanning': True, 'message': '扫描启动中...'}
    })


@app.route('/api/scan/status')
def get_scan_status():
    """获取扫描状态"""
    return jsonify(scan_status)


@app.route('/api/scan/results')
def get_scan_results():
    """获取扫描结果"""
    return jsonify(scan_status['last_result'])


@app.route('/api/cameras/sync', methods=['POST'])
def sync_cameras_from_scan():
    """用扫描结果完全替换摄像头列表，并重置所有流"""
    scan_results = scan_status.get('last_result', [])

    if not scan_results:
        return jsonify({'success': False, 'error': '没有可用的扫描结果，请先扫描网络'})

    # 停止所有现有视频流
    stream_manager.stop_all()

    with db_lock:
        cameras_db.clear()

        new_cameras = []
        for cam in scan_results:
            if not cam.get('stream_url'):
                continue
            cam_id = str(uuid.uuid4())[:8]
            cameras_db[cam_id] = {
                'id': cam_id,
                'name': cam.get('name', f'Camera {cam.get("ip", cam_id)}'),
                'ip': cam.get('ip', ''),
                'stream_url': cam['stream_url'],
                'type': cam.get('type', 'RTSP'),
                'added_time': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            new_cameras.append(cameras_db[cam_id])

        save_cameras_db()

    print(f"[Sync] 已同步 {len(new_cameras)} 个摄像头（视频流改为按需启动）")
    return jsonify({'success': True, 'count': len(new_cameras), 'cameras': new_cameras})


@app.route('/api/cameras/refresh', methods=['POST'])
def refresh_cameras():
    """强制重新检测所有摄像头在线状态（轻量级TCP探测，不启动视频流）"""
    snapshot = {}
    with db_lock:
        snapshot = dict(cameras_db)

    def do_refresh():
        import socket
        from urllib.parse import urlparse
        
        for cam_id, cam_data in snapshot.items():
            url = cam_data.get('stream_url', '')
            if not url:
                continue
            try:
                parsed = urlparse(url)
                host = parsed.hostname
                port = parsed.port or 554
                
                if host:
                    try:
                        sock = socket.create_connection((host, port), timeout=2.0)
                        sock.close()
                        is_online = True
                        print(f"[Refresh] 摄像头在线: {cam_data.get('name', cam_id)}")
                    except (socket.timeout, ConnectionRefusedError, OSError):
                        is_online = False
                        print(f"[Refresh] 摄像头离线: {cam_data.get('name', cam_id)}")
                        
                    with db_lock:
                        if cam_id in cameras_db:
                            cameras_db[cam_id]['is_online'] = is_online
                            
            except Exception as e:
                print(f"[Refresh] 探测异常 {cam_id}: {e}")

    threading.Thread(target=do_refresh, daemon=True).start()
    return jsonify({'success': True, 'message': f'正在重新检测 {len(snapshot)} 个摄像头'})


@app.route('/api/stream/<cam_id>')
def stream_video(cam_id):
    """MJPEG视频流"""
    stream = stream_manager.get_stream(cam_id)
    
    if not stream:
        # 尝试从数据库启动
        if cam_id in cameras_db:
            stream_url = cameras_db[cam_id].get('stream_url')
            if stream_url:
                if stream_manager.add_camera(cam_id, stream_url):
                    stream = stream_manager.get_stream(cam_id)
        
        if not stream:
            return jsonify({'error': 'Stream not found'}), 404
    
    quality = request.args.get('quality', 70, type=int)
    
    return Response(
        generate_mjpeg(stream, quality),
        mimetype='multipart/x-mixed-replace; boundary=--frameboundary',
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    )


@app.route('/api/snapshot/<cam_id>')
def snapshot(cam_id):
    """获取摄像头快照（原始分辨率）"""
    stream = stream_manager.get_stream(cam_id)
    
    if not stream:
        return jsonify({'error': 'Stream not found'}), 404
    
    # 获取原始分辨率的JPEG图片（质量95）
    jpeg_bytes = stream.get_jpeg_bytes(quality=95)
    
    if not jpeg_bytes:
        return jsonify({'error': 'Failed to capture frame'}), 500
    
    # 生成文件名
    camera_name = cameras_db.get(cam_id, {}).get('name', cam_id)
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    filename = f"{camera_name}_{timestamp}.jpg"
    
    return Response(
        jpeg_bytes,
        mimetype='image/jpeg',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Cache-Control': 'no-cache'
        }
    )


@app.route('/api/streams/status')
def get_streams_status():
    """获取所有流状态，管理生命周期以降低延迟"""
    active_ids_str = request.args.get('active', '')
    main_id = request.args.get('main', '')
    
    active_ids = [cid.strip() for cid in active_ids_str.split(',') if cid.strip()]
    
    with db_lock:
        db_snapshot = dict(cameras_db)
        
    all_streams_dict = stream_manager.get_all_streams()
    
    # 停止所有未在窗口中显示的流，节省后台带宽和解码CPU，大幅降低整体延迟
    if active_ids_str is not None:
        for cid in list(all_streams_dict.keys()):
            if cid not in active_ids:
                stream_manager.remove_camera(cid)
                print(f"[Stream] 停止闲置视频流以降低延迟: {cid}")
                
    # 确保 active 的流都已启动
    for cid in active_ids:
        if cid not in stream_manager.get_all_streams() and cid in db_snapshot:
            stream_url = db_snapshot[cid].get('stream_url')
            if stream_url:
                print(f"[Stream] 按需启动活动视频流: {cid}")
                stream_manager.add_camera(cid, stream_url)

    # 给主力窗口提供更高优先级或标记
    for cid, stream in stream_manager.get_all_streams().items():
        stream.is_main = (cid == main_id)
        
    statuses = []
    # 依然返回所有db中摄像头的状态（如果没启动则为离线），或者返回当前运行的流
    for cam_id, cam_data in db_snapshot.items():
        s = stream_manager.get_stream(cam_id)
        if s:
            status = s.get_status()
            # 运行中的流，如果是联通的，更新数据库的存活状态
            if status.get('is_connected'):
                with db_lock:
                    if cam_id in cameras_db:
                        cameras_db[cam_id]['is_online'] = True
        else:
            status = {
                'camera_id': cam_id,
                'is_running': False,
                'is_connected': cam_data.get('is_online', False),
                'fps': 0,
                'error_count': 0,
                'frame_age': -1,
                'rtsp_url': cam_data.get('stream_url', '')
            }
        status['name'] = cam_data.get('name', cam_id)
        statuses.append(status)
    
    return jsonify(statuses)


# ==================== Main ====================

def main():
    global discovery, stream_manager
    
    print("=" * 50)
    print("IP Camera Viewer - 局域网摄像头监控")
    print("=" * 50)
    
    # 初始化
    print("\n[1/4] 初始化摄像头发现模块...")
    discovery = CameraDiscovery('config.json')
    
    print("[2/4] 初始化视频流管理器...")
    stream_manager = StreamManager('config.json')
    
    print("[3/4] 加载摄像头数据库...")
    load_cameras_db()
    
    print("[4/4] 启动视频流服务...")
    init_camera_streams()
    
    # 加载配置
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    host = config['server']['host']
    port = config['server']['port']
    debug = config['server']['debug']
    
    print("\n" + "=" * 50)
    print(f"服务启动成功!")
    print(f"访问地址: http://localhost:{port}")
    print(f"局域网地址: http://0.0.0.0:{port}")
    print("=" * 50 + "\n")
    
    # 启动Flask
    app.run(
        host=host,
        port=port,
        debug=debug,
        threaded=True,
        use_reloader=False
    )


if __name__ == '__main__':
    main()
