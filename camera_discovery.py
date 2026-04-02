#!/usr/bin/env python3
"""
IP Camera Discovery Module
Supports ONVIF and direct RTSP scanning
"""

import json
import socket
import subprocess
import platform
import threading
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
import time
import struct


class CameraDiscovery:
    """摄像头发现类"""
    
    # 常见摄像头的RTSP路径 - 按优先级排序
    COMMON_RTSP_PATHS = [
        # 海康威视
        "/Streaming/Channels/101",
        "/Streaming/Channels/102",
        "/ch1/main/av_stream",
        "/ch1/sub/av_stream",
        # 大华
        "/cam/realmonitor?channel=1&subtype=0",
        "/cam/realmonitor?channel=1&subtype=1",
        # 通用
        "/live/ch00_0",
        "/live/ch01_0", 
        "/live/stream1",
        "/live/stream2",
        "/stream1",
        "/stream2",
        "/ch0_0.h264",
        "/ch0_1.h264",
        "/videoMain",
        "/videoSub",
        "/11",
        "/12",
        "/1",
        "/onvif1",
        "/onvif2",
        "/profile1",
        "/profile2",
        "/media/video1",
        "/media/video2",
        "/av0_0",
        "/av0_1",
        "/live.sdp",
        "/mpeg4",
        "/h264",
    ]
    
    # 私有网段
    PRIVATE_NETWORKS = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
    ]
    
    def __init__(self, config_path: str = "config.json"):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        self.discovered_cameras: List[Dict] = []
        self.lock = threading.Lock()
        self.verbose = True
        
    def log(self, msg: str):
        """打印日志"""
        if self.verbose:
            print(f"[Discovery] {msg}")
        
    def get_local_networks(self) -> List[str]:
        """获取本地网络IP段，过滤VPN/虚拟网卡"""
        networks = []
        vpn_networks = []
        
        try:
            import netifaces
            for interface in netifaces.interfaces():
                # 跳过虚拟/VPN接口
                if self._is_virtual_interface(interface):
                    continue
                    
                addrs = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in addrs:
                    for addr_info in addrs[netifaces.AF_INET]:
                        ip = addr_info.get('addr')
                        netmask = addr_info.get('netmask')
                        if ip and netmask and not ip.startswith('127.'):
                            try:
                                network = ipaddress.IPv4Network(f"{ip}/{netmask}", strict=False)
                                
                                # 检查是否是VPN网段（如198.18.x.x是Tailscale等VPN常用）
                                if self._is_vpn_network(network):
                                    vpn_networks.append(str(network))
                                else:
                                    networks.append(str(network))
                                    self.log(f"发现本地网段: {interface} -> {network}")
                            except Exception as e:
                                pass
        except ImportError:
            pass
        
        # 备用方案：使用socket获取
        if not networks:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(('8.8.8.8', 80))
                local_ip = s.getsockname()[0]
                if local_ip.startswith('192.168.'):
                    networks.append(f"{local_ip.rsplit('.', 1)[0]}.0/24")
                elif local_ip.startswith('10.'):
                    networks.append(f"{local_ip.rsplit('.', 1)[0]}.0/24")
                else:
                    networks.append(f"{local_ip.rsplit('.', 1)[0]}.0/24")
                self.log(f"使用备用方案发现网段: {networks[0]}")
            except Exception:
                networks = ["192.168.1.0/24", "192.168.0.0/24", "10.0.0.0/24"]
            finally:
                s.close()
        
        if vpn_networks:
            self.log(f"跳过VPN网段: {vpn_networks}")
        
        # 如果配置中指定了网段，优先使用
        if self.config.get('discovery', {}).get('ip_ranges'):
            networks = self.config['discovery']['ip_ranges']
            self.log(f"使用配置网段: {networks}")
        
        return networks if networks else ["192.168.1.0/24"]
    
    def _is_virtual_interface(self, iface: str) -> bool:
        """检查是否为虚拟接口"""
        virtual_prefixes = ('utun', 'tun', 'tap', 'veth', 'docker', 'br-', 'vmnet', 
                           'ppp', 'gif', 'stf', 'awdl', 'llw', 'bridge')
        return iface.startswith(virtual_prefixes)
    
    def _is_vpn_network(self, network: ipaddress.IPv4Network) -> bool:
        """检查是否为VPN网络"""
        # 198.18.0.0/15 是 VPN 常用网段
        vpn_ranges = [
            ipaddress.ip_network("198.18.0.0/15"),
            ipaddress.ip_network("100.64.0.0/10"),  # CGNAT, 也可能是VPN
        ]
        for vpn_range in vpn_ranges:
            if network.subnet_of(vpn_range) or network.supernet_of(vpn_range):
                return True
        # 排除非常小的子网（通常是点对点VPN）
        if network.prefixlen >= 30:
            return True
        return False
    
    def ping_host(self, ip: str, timeout: int = 1) -> bool:
        """Ping主机检查是否存活"""
        try:
            system = platform.system().lower()
            if system == "windows":
                cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), ip]
            else:
                cmd = ["ping", "-c", "1", "-W", str(timeout), ip]
            result = subprocess.run(cmd, stdout=subprocess.DEVNULL, 
                                  stderr=subprocess.DEVNULL, timeout=timeout+1)
            return result.returncode == 0
        except Exception:
            return False
    
    def check_port_open(self, ip: str, port: int, timeout: float = 1.0) -> bool:
        """检查端口是否开放"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except Exception:
            return False
    
    def try_rtsp_url(self, ip: str, port: int, path: str, 
                     username: str = "", password: str = "", 
                     timeout: int = 3) -> Optional[str]:
        """尝试连接RTSP URL - 使用线程防止卡死"""
        import cv2
        import threading
        
        result = [None]
        
        if username and password:
            url = f"rtsp://{username}:{password}@{ip}:{port}{path}"
        else:
            url = f"rtsp://{ip}:{port}{path}"
        
        def try_connect():
            try:
                cap = cv2.VideoCapture(url)
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout * 1000)
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout * 1000)
                
                if cap.isOpened():
                    ret, frame = cap.read()
                    cap.release()
                    if ret and frame is not None and frame.size > 0:
                        result[0] = url
                else:
                    cap.release()
            except Exception:
                pass
        
        thread = threading.Thread(target=try_connect)
        thread.daemon = True
        thread.start()
        thread.join(timeout + 1)  # 给一点额外时间
        
        return result[0]
    
    def onvif_discovery(self, timeout: int = 2) -> List[Dict]:
        """ONVIF WS-Discovery 多播发现"""
        cameras = []
        
        # ONVIF WS-Discovery 多播地址和端口
        multicast_addr = "239.255.255.250"
        multicast_port = 3702
        
        probe_msg = '''<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
            xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
            xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
            xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <e:Header>
    <w:MessageID>uuid:%s</w:MessageID>
    <w:To e:mustUnderstand="true">urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
    <w:Action e:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
  </e:Header>
  <e:Body>
    <d:Probe>
      <d:Types>dn:NetworkVideoTransmitter</d:Types>
    </d:Probe>
  </e:Body>
</e:Envelope>''' % self._gen_uuid()

        try:
            # 创建UDP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            sock.settimeout(timeout)
            
            # 绑定到所有接口
            sock.bind(("0.0.0.0", 0))
            
            # 发送多播探测
            self.log(f"发送ONVIF多播探测到 {multicast_addr}:{multicast_port}")
            sock.sendto(probe_msg.encode('utf-8'), (multicast_addr, multicast_port))
            
            # 接收响应
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    data, addr = sock.recvfrom(4096)
                    ip = addr[0]
                    self.log(f"收到ONVIF响应来自: {ip}")
                    
                    camera_info = {
                        'ip': ip,
                        'type': 'ONVIF',
                        'source': 'multicast_discovery',
                        'name': f"ONVIF_Camera_{ip.split('.')[-1]}"
                    }
                    cameras.append(camera_info)
                except socket.timeout:
                    break
                except Exception as e:
                    pass
                    
            sock.close()
        except Exception as e:
            self.log(f"ONVIF多播发现错误: {e}")
        
        return cameras
    
    def _gen_uuid(self) -> str:
        """生成UUID"""
        import uuid
        return str(uuid.uuid4())
    
    def find_rtsp_stream(self, ip: str, port: int = 554) -> Optional[Dict]:
        """尝试查找RTSP流"""
        # 首先检查RTSP端口是否开放
        if not self.check_port_open(ip, port, 1.0):
            return None
        
        self.log(f"  {ip}:{port} 端口开放，尝试RTSP路径...")
        
        # 尝试无认证访问（优先级高的路径）
        for path in self.COMMON_RTSP_PATHS[:5]:
            url = self.try_rtsp_url(ip, port, path, "", "", 2)
            if url:
                self.log(f"  ✓ 发现RTSP流: {path}")
                return {
                    'ip': ip,
                    'port': port,
                    'rtsp_url': url,
                    'path': path,
                    'auth_required': False
                }
        
        # 尝试常见凭据
        for cred in self.config['discovery']['common_credentials']:
            for path in self.COMMON_RTSP_PATHS:
                url = self.try_rtsp_url(ip, port, path, 
                                       cred['username'], cred['password'], 2)
                if url:
                    self.log(f"  ✓ 发现RTSP流(需认证): {path}")
                    return {
                        'ip': ip,
                        'rtsp_url': url,
                        'username': cred['username'],
                        'password': cred['password'],
                        'auth_required': True,
                        'path': path
                    }
        return None
    
    def scan_ip(self, ip: str) -> Optional[Dict]:
        """扫描单个IP"""
        # 先ping检查（快速过滤）
        if not self.ping_host(ip, timeout=1):
            return None
        
        self.log(f"扫描存活主机: {ip}")
        
        camera_info = {
            'ip': ip,
            'found_time': time.strftime('%Y-%m-%d %H:%M:%S'),
            'services': {}
        }
        
        # 检查RTSP
        for rtsp_port in self.config['discovery']['rtsp_ports']:
            rtsp_info = self.find_rtsp_stream(ip, rtsp_port)
            if rtsp_info:
                camera_info['rtsp'] = rtsp_info
                camera_info['type'] = 'RTSP'
                camera_info['stream_url'] = rtsp_info['rtsp_url']
                break
        
        # 如果没有任何服务被发现，返回None
        if 'rtsp' not in camera_info:
            return None
        
        # 设置名称
        camera_info['name'] = f"Camera_{ip.split('.')[-1]}"
        
        return camera_info
    
    def scan_network(self, network: str = None, progress_callback=None, fast_mode: bool = True) -> List[Dict]:
        """扫描整个网络"""
        self.discovered_cameras = []
        
        # 第一步：ONVIF多播发现（最快）
        self.log("=" * 50)
        self.log("步骤 1/3: ONVIF多播发现...")
        onvif_cameras = self.onvif_discovery(timeout=2 if fast_mode else 3)
        self.log(f"ONVIF多播发现: {len(onvif_cameras)} 个设备")
        
        for cam in onvif_cameras:
            # 尝试获取RTSP流
            for port in self.config['discovery']['rtsp_ports']:
                rtsp_info = self.find_rtsp_stream(cam['ip'], port)
                if rtsp_info:
                    cam['rtsp'] = rtsp_info
                    cam['stream_url'] = rtsp_info['rtsp_url']
                    break
            
            with self.lock:
                self.discovered_cameras.append(cam)
        
        # 第二步：为ONVIF设备获取RTSP流
        if onvif_cameras:
            self.log("=" * 50)
            self.log(f"步骤 2/3: 获取ONVIF设备RTSP流...")
            for cam in onvif_cameras:
                ip = cam['ip']
                # 快速检查RTSP端口
                for port in self.config['discovery']['rtsp_ports']:
                    rtsp_info = self.find_rtsp_stream(ip, port)
                    if rtsp_info:
                        cam['rtsp'] = rtsp_info
                        cam['stream_url'] = rtsp_info['rtsp_url']
                        break
                with self.lock:
                    self.discovered_cameras.append(cam)
        
        # 第三步：IP扫描（补充模式，可选）
        if not fast_mode:
            if network is None:
                networks = self.get_local_networks()
            else:
                networks = [network]
            
            self.log("=" * 50)
            self.log(f"步骤 3/3: 扫描IP网段...")
            self.log(f"目标网段: {networks}")
            
            all_ips = []
            for net in networks:
                try:
                    network_obj = ipaddress.IPv4Network(net, strict=False)
                    hosts = list(network_obj.hosts())
                    if len(hosts) > 256:
                        self.log(f"网段 {net} 较大，只扫描前256个IP")
                        hosts = hosts[:256]
                    all_ips.extend([str(ip) for ip in hosts])
                except Exception as e:
                    self.log(f"网络地址解析错误 {net}: {e}")
            
            # 排除已发现的IP
            discovered_ips = {cam['ip'] for cam in self.discovered_cameras}
            all_ips = [ip for ip in all_ips if ip not in discovered_ips]
            
            self.log(f"需要扫描 {len(all_ips)} 个IP地址...")
            
            # 使用线程池并行扫描
            max_workers = min(100, len(all_ips))
            scanned = 0
            found_count = len(self.discovered_cameras)
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_ip = {executor.submit(self.scan_ip, ip): ip for ip in all_ips}
                
                for future in as_completed(future_to_ip):
                    scanned += 1
                    ip = future_to_ip[future]
                    
                    if progress_callback and scanned % 50 == 0:
                        progress_callback(scanned, len(all_ips))
                    
                    try:
                        result = future.result()
                        if result:
                            with self.lock:
                                self.discovered_cameras.append(result)
                                found_count += 1
                            self.log(f"[+] 发现摄像头 #{found_count}: {ip}")
                    except Exception as e:
                        pass
        
        self.log("=" * 50)
        self.log(f"扫描完成! 共发现 {len(self.discovered_cameras)} 个摄像头")
        
        return self.discovered_cameras
    
    def get_cameras(self) -> List[Dict]:
        """获取已发现的摄像头列表"""
        return self.discovered_cameras
    
    def add_camera_manually(self, name: str, rtsp_url: str, 
                           username: str = "", password: str = "") -> bool:
        """手动添加摄像头"""
        try:
            parsed = urlparse(rtsp_url)
            ip = parsed.hostname
            
            camera_info = {
                'name': name,
                'ip': ip,
                'stream_url': rtsp_url,
                'username': username,
                'password': password,
                'manual': True,
                'found_time': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # 验证流是否可用
            import cv2
            cap = cv2.VideoCapture(rtsp_url)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
            
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                if ret:
                    with self.lock:
                        # 检查是否已存在
                        for i, cam in enumerate(self.discovered_cameras):
                            if cam.get('ip') == ip:
                                self.discovered_cameras[i] = camera_info
                                return True
                        self.discovered_cameras.append(camera_info)
                    return True
            else:
                cap.release()
        except Exception as e:
            self.log(f"手动添加摄像头失败: {e}")
        
        return False


if __name__ == "__main__":
    # 测试发现功能
    discovery = CameraDiscovery()
    
    print("开始测试扫描...")
    print(f"本机网段: {discovery.get_local_networks()}")
    
    cameras = discovery.scan_network()
    
    print(f"\n共发现 {len(cameras)} 个摄像头:")
    for cam in cameras:
        print(f"  - {cam.get('name', 'Unknown')} ({cam.get('ip', 'N/A')})")
        if 'stream_url' in cam:
            print(f"    URL: {cam['stream_url']}")
