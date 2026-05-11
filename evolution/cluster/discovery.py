
import socket
import threading
import json
import time
import uuid
from typing import List, Dict, Any, Optional
from logger import logger
from config import PORT_CLUSTER_MANAGER, PORT_WEB

# 统一UDP广播端口：所有节点必须监听同一个端口才能互相发现
UDP_DISCOVERY_PORT = 50005

class ClusterDiscovery:
    """局域网房间发现机制 (基于 UDP 广播) - 完全跨平台兼容"""
    
    def __init__(self, port: int = UDP_DISCOVERY_PORT, room_name: str = "", room_id: str = None, host_port: int = 30001):
        self.port = port
        self.room_name = room_name  # 初始为空，用户创建房间时再设置
        self.room_id = room_id or str(uuid.uuid4())[:8]
        self.host_port = host_port
        self.running = False
        self.broadcasting = False  # 单独标记广播是否在运行 - 初始化时必须为False，绝对不自动启动广播！
        self.scanning = False       # 单独标记扫描是否在运行
        self.found_rooms = {} # {ip: room_info}
        self._broadcast_thread = None
        self._scan_thread = None
        self._local_ips = self._get_all_local_ips()  # 缓存本机所有IP地址列表
        self._last_processed_msg = None  # 用于去重的最后处理消息
        self._extra_broadcast_info = {}  # 持久化保存要广播的额外信息（密码标识、房主名、模型等）
    
    def _get_all_local_ips(self) -> List[str]:
        """获取本机所有网卡的IP地址（跨平台终极版 - 完美兼容Windows/Linux/Mac，支持有线+无线多网卡）"""
        local_ips = ['127.0.0.1']
        
        # 方式1：标准 gethostbyname_ex
        try:
            hostname = socket.gethostname()
            host_info = socket.gethostbyname_ex(hostname)
            for ip in host_info[2]:
                if ip not in local_ips:
                    local_ips.append(ip)
        except Exception as e:
            logger.debug(f"_get_all_local_ips 方式1失败: {e}")
        
        # 方式2：尝试获取能连接外网的网卡IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            if local_ip not in local_ips:
                local_ips.append(local_ip)
        except Exception as e:
            logger.debug(f"_get_all_local_ips 方式2失败: {e}")
        
        # 方式3：跨平台 netifaces 替代方案（不依赖第三方库）
        import sys
        platform = sys.platform
        
        if platform.startswith('win'):
            # Windows平台：使用 socket.gethostbyname_ex 的增强版 + 多探测
            try:
                hostname = socket.gethostname()
                # 额外探测：遍历 192.168.x.x 系列常见局域网IP，避免漏网
                import subprocess
                result = subprocess.run(['ipconfig', '/all'], capture_output=True, text=True, encoding='gbk', errors='ignore')
                if result.returncode == 0:
                    import re
                    ip_pattern = re.compile(r'IPv4.*?:\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})')
                    for match in ip_pattern.finditer(result.stdout):
                        ip = match.group(1)
                        if ip not in local_ips and not ip.startswith('255.') and not ip.startswith('0.'):
                            local_ips.append(ip)
            except Exception as e:
                logger.debug(f"Windows ipconfig解析补充失败: {e}")
        
        elif platform.startswith('linux') or platform.startswith('darwin'):
            # Linux/Mac平台：使用ioctl原生方式
            try:
                import array
                import fcntl
                import struct
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                max_possible = 128
                bytes_ = max_possible * 32
                names = array.array('B', b'\0' * bytes_)
                outbytes = struct.unpack('iP', fcntl.ioctl(
                    s.fileno(),
                    0x8912,
                    struct.pack('iL', bytes_, names.buffer_info()[0])
                ))[0]
                namestr = names.tobytes()
                for i in range(0, outbytes, 32):
                    ip = socket.inet_ntoa(namestr[i+20:i+24])
                    if ip not in local_ips and ip != '127.0.0.1':
                        local_ips.append(ip)
                s.close()
            except Exception as e:
                logger.debug(f"Linux/Mac ioctl 网卡枚举补充失败: {e}")
                # 备用方案：ifconfig 或 ip 命令解析
                try:
                    import subprocess
                    result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
                    if result.returncode == 0:
                        ips_str = result.stdout.strip()
                        for ip in ips_str.split():
                            if ip and ip.count('.') == 3:
                                if ip not in local_ips:
                                    local_ips.append(ip)
                except Exception:
                    pass
        
        logger.info(f"🏠 [ClusterDiscovery] 本机IP列表: {local_ips} (已遍历所有网卡，平台: {platform})")
        return local_ips

    def _is_ip_local(self, ip: str) -> bool:
        """判断一个IP是否属于本机"""
        return ip in self._local_ips

    def _get_local_broadcast_ips(self) -> List[str]:
        """获取所有可能的广播地址（终极版 - 完美支持Win无线/Linux有线等跨网卡同网段互发现）"""
        broadcast_addrs = []
        
        # 1. 无条件添加全局有限广播 255.255.255.255 - 这是最核心的保底手段
        broadcast_addrs.append('255.255.255.255')
        
        # 2. 从本机所有IP智能派生各自的子网广播地址
        for local_ip in self._local_ips:
            if local_ip != '127.0.0.1':
                parts = local_ip.split('.')
                if len(parts) == 4:
                    base3 = '.'.join(parts[:3])
                    subnet_bcast = f"{base3}.255"
                    if subnet_bcast not in broadcast_addrs:
                        broadcast_addrs.append(subnet_bcast)
                        logger.debug(f"📤 派生子网广播地址: {subnet_bcast} (来自本机IP: {local_ip})")
        
        # 3. 超全国内家用/办公局域网常见网段 - 兜底覆盖
        super_common_presets = [
            # 192.168.x.x 系列（最常见）
            "192.168.0.255",
            "192.168.1.255",
            "192.168.2.255",
            "192.168.3.255",
            "192.168.4.255",
            "192.168.5.255",
            "192.168.8.255",
            "192.168.9.255",
            "192.168.10.255",
            "192.168.11.255",
            "192.168.18.255",
            "192.168.20.255",
            "192.168.30.255",
            "192.168.31.255",  # 用户案例：Linux有线192.168.31.16 所在网段
            "192.168.50.255",
            "192.168.68.255",
            "192.168.88.255",
            "192.168.100.255",
            "192.168.123.255",
            "192.168.168.255",
            # 10.x.x.x 私网段
            "10.0.0.255",
            "10.0.1.255",
            "10.0.10.255",
            "10.0.100.255",
            # 172.16-31.x.x 私网段
            "172.16.0.255",
            "172.17.0.255",
            "172.18.0.255",
            "172.19.0.255",
            "172.20.0.255",
            "172.31.255.255"
        ]
        for preset_bcast in super_common_presets:
            if preset_bcast not in broadcast_addrs:
                broadcast_addrs.append(preset_bcast)
        
        final_result = list(set(broadcast_addrs))
        logger.info(f"📡 [ClusterDiscovery] 最终广播地址总数: {len(final_result)} 个 - 确保无线/有线跨网卡完美互发现")
        return final_result

    def update_room_info(self, room_name: str, room_id: str, extra_info: Dict[str, Any] = None):
        """更新要广播的房间信息（创建房间后调用） - 持久化保存extra_info"""
        self.room_name = room_name
        self.room_id = room_id
        if extra_info:
            self._extra_broadcast_info.update(extra_info)  # 合并更新，不是覆盖
        logger.info(f"📢 [ClusterDiscovery] 房间信息已更新: {room_name} (ID: {room_id}), 广播附加信息: {self._extra_broadcast_info}")

    def start_hosting(self, extra_info: Dict[str, Any] = None):
        """开启房主模式：持续广播房间信息 - 优先使用持久化的_extra_broadcast_info"""
        if self.broadcasting:
            logger.warning("[ClusterDiscovery] 广播已在运行，跳过重复启动")
            return
        # 合并传入的extra_info到持久化字典
        if extra_info:
            self._extra_broadcast_info.update(extra_info)
        self.broadcasting = True
        self.running = True  # 确保running标志正确设置
        threading.Thread(target=self._broadcast_loop, daemon=True).start()
        logger.info(f"🚀 [ClusterDiscovery] 房主广播已开启，房间: {self.room_name}, UDP端口: {self.port}, 广播信息: {self._extra_broadcast_info}")

    def _get_best_broadcast_source_ip(self) -> Optional[str]:
        """获取一个最适合作为广播源的本机IP（优先找能连外网的真实局域网IP）"""
        # 优先找能连接外网的那个IP（最常用的网卡）
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            src_ip = s.getsockname()[0]
            s.close()
            if src_ip and not src_ip.startswith('127.'):
                return src_ip
        except Exception:
            pass
        # 备选：取第一个非127的局域网IP
        for ip in self._local_ips:
            if ip != '127.0.0.1':
                return ip
        return '127.0.0.1'

    def _broadcast_loop(self):
        """广播主循环 - 使用持久化的_extra_broadcast_info，附带本机真实IP作为广播源标识"""
        broadcast_ips = self._get_local_broadcast_ips()
        # 获取自己的真实源IP，放到广播消息里，解决某些场景下sender不准确的问题
        my_real_source_ip = self._get_best_broadcast_source_ip()
        logger.info(f"📡 [ClusterDiscovery] 广播地址列表: {broadcast_ips}, 本机源IP标识: {my_real_source_ip}")
        
        while self.broadcasting:
            try:
                msg = {
                    "type": "ROOM_ADVERTISEMENT",
                    "room_name": self.room_name,
                    "room_id": self.room_id,
                    "manager_port": PORT_CLUSTER_MANAGER,
                    "web_port": PORT_WEB,
                    "timestamp": time.time(),
                    "source_ip": my_real_source_ip,  # 关键：显式附带自己的真实IP
                    **self._extra_broadcast_info  # 关键：使用持久化的信息，确保每次广播都包含所有需要的字段
                }
                data = json.dumps(msg, ensure_ascii=False).encode('utf-8')
                # 不使用with，保持socket更稳定的状态
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                for bcast_ip in broadcast_ips:
                    try:
                        s.sendto(data, (bcast_ip, self.port))
                        logger.debug(f"📤 [ClusterDiscovery] 已广播到 {bcast_ip}:{self.port}")
                    except Exception as e:
                        logger.debug(f"广播到 {bcast_ip} 失败: {e}")
                s.close()
            except Exception as e:
                logger.debug(f"广播循环异常: {e}")
            time.sleep(2)  # 更频繁一点，2秒发一次，确保跨平台快速发现

    def start_scanning(self):
        """开启扫描模式：监听局域网内的房间"""
        if self.scanning:
            logger.warning("[ClusterDiscovery] 扫描已在运行，跳过重复启动")
            return
        self.scanning = True
        self.running = True
        threading.Thread(target=self._scan_loop, daemon=True).start()
        logger.info(f"🔍 [ClusterDiscovery] 扫描模式已开启，正在搜寻局域网房间...")

    def _scan_loop(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('', self.port))
                logger.info(f"👂 [ClusterDiscovery] 扫描已绑定到端口 {self.port}")
            except Exception as bind_e:
                logger.warning(f"端口{self.port}被占用，尝试随机端口监听: {bind_e}")
                s.bind(('', 0))
            s.settimeout(2.0)
            duplicate_filter = {}  # 用于秒级时间戳+room_id去重，防止Windows收到多次同一广播包
            while self.scanning:
                try:
                    data, addr = s.recvfrom(4096)
                    msg = json.loads(data.decode('utf-8'))
                    if msg.get("type") == "ROOM_ADVERTISEMENT":
                        sender_ip = addr[0]
                        # 【关键优化】优先用消息里显式附带的 source_ip，解决跨平台/多网卡场景下的sender不准确问题
                        explicit_source_ip = msg.get("source_ip")
                        if explicit_source_ip and not self._is_ip_local(explicit_source_ip):
                            sender_ip = explicit_source_ip
                        
                        # 1️⃣ 关键修复：过滤掉来自本机IP的回环广播包（这是Windows出现重复房间的根本原因）
                        if self._is_ip_local(sender_ip):
                            logger.debug(f"🚫 [ClusterDiscovery] 过滤本机回环广播包，跳过: {sender_ip}")
                            continue
                        
                        room_id = msg.get('room_id', 'unknown')
                        msg_timestamp = int(msg.get("timestamp", time.time()))  # 按秒级粒度去重
                        
                        # 2️⃣ 秒级去重：同一房间+同一秒内多次收到的消息，只处理一次
                        dedup_key = f"{sender_ip}:{room_id}:{msg_timestamp}"
                        if dedup_key in duplicate_filter:
                            logger.debug(f"🔁 [ClusterDiscovery] 重复广播包已跳过: {dedup_key}")
                            continue
                        duplicate_filter[dedup_key] = True
                        
                        # 3️⃣ 清理过期的去重记录（超过5秒的自动清理）
                        expired_keys = [k for k, v in duplicate_filter.items() 
                                       if int(k.split(':')[-1]) < int(time.time()) - 5]
                        for ek in expired_keys:
                            del duplicate_filter[ek]
                        
                        room_key = f"{sender_ip}:{room_id}"
                        self.found_rooms[room_key] = {
                            "ip": sender_ip,
                            "room_name": msg.get("room_name", "Unnamed-Room"),
                            "room_id": room_id,
                            "manager_port": msg.get("manager_port", 30001),
                            "web_port": msg.get("web_port", 30000),
                            "owner_name": msg.get("owner_name", "Unknown"),
                            "owner_model": msg.get("owner_model") or "unknown",
                            "password_required": msg.get("password_required", False),
                            "timestamp": msg.get("timestamp", time.time())
                        }
                        safe_model = msg.get('owner_model') or "unknown"
                        logger.info(f"✨ [ClusterDiscovery] 发现局域网房间: {msg.get('room_name', 'Unnamed-Room')} @ {sender_ip}, 模型: {safe_model}")
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.debug(f"扫描接收异常: {e}")
            s.close()
        except Exception as e:
            logger.error(f"扫描循环失败: {e}")

    def get_available_rooms(self) -> List[Dict[str, Any]]:
        """获取当前发现的所有房间（过滤掉5秒内未更新的房间 - 解散房间后快速消失）"""
        now = time.time()
        result = []
        expired_keys = []
        for room_key, room in self.found_rooms.items():
            ts = room.get("timestamp", 0)
            if now - ts < 5: # 只保留5秒内收到过广播的房间，让解散的房间快速消失
                result.append(room)
            else:
                expired_keys.append(room_key)
        # 清理过期的房间，避免内存占用
        for key in expired_keys:
            del self.found_rooms[key]
        return result

    def stop_hosting(self):
        """停止广播（不停止扫描）"""
        self.broadcasting = False
        logger.info("[ClusterDiscovery] 房主广播已停止")

    def stop_scanning(self):
        """停止扫描（不停止广播）"""
        self.scanning = False
        logger.info("[ClusterDiscovery] 局域网扫描已停止")

    def stop(self):
        """停止所有广播和扫描线程"""
        self.broadcasting = False
        self.scanning = False
        self.running = False
        logger.info("[ClusterDiscovery] 已停止发现服务")
