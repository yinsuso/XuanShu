
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
    
    def _is_valid_private_ip(self, ip: str) -> bool:
        """验证IP是否为有效的私网局域网IP（排除回环、广播、无效地址）"""
        if not ip:
            return False
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        for p in parts:
            try:
                n = int(p)
                if n < 0 or n > 255:
                    return False
            except ValueError:
                return False
        a, b, c, d = map(int, parts)
        # 排除广播地址
        if d == 255:
            return False
        # 回环地址仅保留127.0.0.1
        if a == 127:
            return ip == '127.0.0.1'
        # 私网网段判定
        return (a == 10) or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168)

    def _get_all_local_ips(self) -> List[str]:
        """获取本机所有网卡的IP地址（跨平台终极版 - 只保留真实有效的局域网IP）"""
        local_ips = ['127.0.0.1']
        
        # 方式1：标准 gethostbyname_ex
        try:
            hostname = socket.gethostname()
            host_info = socket.gethostbyname_ex(hostname)
            for ip in host_info[2]:
                if ip not in local_ips and self._is_valid_private_ip(ip):
                    local_ips.append(ip)
        except Exception as e:
            logger.debug(f"_get_all_local_ips 方式1失败: {e}")
        
        # 方式2：尝试获取能连接外网的网卡IP（这是最核心最可靠的IP）
        reliable_source_ip = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            if local_ip and self._is_valid_private_ip(local_ip):
                if local_ip not in local_ips:
                    local_ips.append(local_ip)
                reliable_source_ip = local_ip
        except Exception as e:
            logger.debug(f"_get_all_local_ips 方式2失败: {e}")
        
        # 方式3：跨平台 netifaces 替代方案（不依赖第三方库）
        import sys
        platform = sys.platform
        
        if platform.startswith('win'):
            # Windows平台：使用 ipconfig 解析，但严格过滤只保留有效IP
            try:
                import subprocess
                result = subprocess.run(['ipconfig'], capture_output=True, text=True, encoding='gbk', errors='ignore')
                if result.returncode == 0:
                    import re
                    ip_pattern = re.compile(r'IPv4.*?:\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})')
                    for match in ip_pattern.finditer(result.stdout):
                        ip = match.group(1)
                        if ip not in local_ips and self._is_valid_private_ip(ip):
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
                    if ip not in local_ips and self._is_valid_private_ip(ip):
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
                            if ip and self._is_valid_private_ip(ip):
                                if ip not in local_ips:
                                    local_ips.append(ip)
                except Exception:
                    pass
        
        logger.info(f"🏠 [ClusterDiscovery] 本机IP列表: {local_ips} (已过滤无效IP，平台: {platform})")
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

    def _get_subnet_unicast_targets(self) -> List[str]:
        """通用同网段常用IP单播目标生成 - 100%适配所有标准私网网段 (10.x.x.x / 172.16-31.x.x / 192.168.x.x)"""
        unicast_targets = []
        common_last_octets = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10,
                              11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
                              21, 22, 23, 24, 25, 30, 31, 32, 40, 50,
                              60, 100, 101, 120, 123, 160, 161, 162, 163, 200]
        
        for local_ip in self._local_ips:
            if local_ip in ('127.0.0.1',):
                continue
            parts = local_ip.split('.')
            if len(parts) == 4:
                a, b, c, d = map(int, parts)
                
                # 处理 192.168.x.x 网段（C类）
                if a == 192 and b == 168:
                    base3 = f"{a}.{b}.{c}"
                    for last_octet in common_last_octets:
                        target_ip = f"{base3}.{last_octet}"
                        if target_ip not in unicast_targets and target_ip != local_ip:
                            unicast_targets.append(target_ip)
                
                # 处理 172.16-31.x.x 网段（B类）
                elif a == 172 and 16 <= b <= 31:
                    base2 = f"{a}.{b}"
                    # 覆盖前10个可能的第三段 + 常用最后一段
                    for third_octet in range(0, 11):
                        base3 = f"{base2}.{third_octet}"
                        for last_octet in common_last_octets:
                            target_ip = f"{base3}.{last_octet}"
                            if target_ip not in unicast_targets and target_ip != local_ip:
                                unicast_targets.append(target_ip)
                
                # 处理 10.x.x.x 网段（A类）
                elif a == 10:
                    # 覆盖前10个可能的第二段 + 前10个第三段 + 常用最后一段
                    for second_octet in range(0, 11):
                        for third_octet in range(0, 11):
                            base3 = f"{a}.{second_octet}.{third_octet}"
                            for last_octet in common_last_octets[:20]:
                                target_ip = f"{base3}.{last_octet}"
                                if target_ip not in unicast_targets and target_ip != local_ip:
                                    unicast_targets.append(target_ip)
        return unicast_targets

    def _broadcast_loop(self):
        """广播主循环 - 使用持久化的_extra_broadcast_info，附带本机真实IP作为广播源标识"""
        broadcast_ips = self._get_local_broadcast_ips()
        unicast_targets = self._get_subnet_unicast_targets()
        # 获取自己的真实源IP，放到广播消息里，解决某些场景下sender不准确的问题
        my_real_source_ip = self._get_best_broadcast_source_ip()
        logger.info(f"📡 [ClusterDiscovery] 广播地址列表: {broadcast_ips}, 补充单播目标数: {len(unicast_targets)}, 本机源IP标识: {my_real_source_ip}")
        
        send_counter = 0
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
                # 每5次广播（约10秒）执行一轮单播补充发送
                if send_counter % 5 == 0:
                    for unicast_ip in unicast_targets:
                        try:
                            s.sendto(data, (unicast_ip, self.port))
                        except Exception:
                            pass
                    logger.debug(f"🎯 [ClusterDiscovery] 补充单播发送已执行，共 {len(unicast_targets)} 个目标")
                s.close()
                send_counter += 1
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
            s.settimeout(1.5)
            
            # 扫描端主动探测：生成同网段所有常用IP，定期发房间查询请求
            probe_targets = self._get_subnet_unicast_targets()
            probe_counter = 0
            duplicate_filter = {}
            
            while self.scanning:
                try:
                    data, addr = s.recvfrom(4096)
                    msg = json.loads(data.decode('utf-8'))
                    
                    # 处理房间广告
                    if msg.get("type") == "ROOM_ADVERTISEMENT":
                        sender_ip = addr[0]
                        explicit_source_ip = msg.get("source_ip")
                        if explicit_source_ip:
                            sender_ip = explicit_source_ip
                        
                        if self._is_ip_local(sender_ip):
                            logger.debug(f"🚫 [ClusterDiscovery] 过滤本机回环广播包，跳过: {sender_ip}")
                            continue
                        
                        room_id = msg.get('room_id', 'unknown')
                        msg_timestamp = int(msg.get("timestamp", time.time()))
                        dedup_key = f"{sender_ip}:{room_id}:{msg_timestamp}"
                        if dedup_key in duplicate_filter:
                            logger.debug(f"🔁 [ClusterDiscovery] 重复广播包已跳过: {dedup_key}")
                            continue
                        duplicate_filter[dedup_key] = True
                        
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
                    
                    # 处理其他节点发来的房间查询请求，直接响应回完整房间广告
                    elif msg.get("type") == "ROOM_DISCOVERY_QUERY" and self.broadcasting:
                        query_sender_ip = addr[0]
                        logger.debug(f"📥 [ClusterDiscovery] 收到来自 {query_sender_ip} 的房间查询请求，正在回复...")
                        reply_msg = {
                            "type": "ROOM_ADVERTISEMENT",
                            "room_name": self.room_name,
                            "room_id": self.room_id,
                            "manager_port": PORT_CLUSTER_MANAGER,
                            "web_port": PORT_WEB,
                            "timestamp": time.time(),
                            "source_ip": self._get_best_broadcast_source_ip(),
                            **self._extra_broadcast_info
                        }
                        reply_data = json.dumps(reply_msg, ensure_ascii=False).encode('utf-8')
                        try:
                            s.sendto(reply_data, (query_sender_ip, self.port))
                        except Exception:
                            pass
                            
                except socket.timeout:
                    # 超时期间主动发送探测请求，每3个超时周期约4.5秒发一轮
                    probe_counter += 1
                    if probe_counter % 3 == 0 and probe_targets:
                        query_msg = json.dumps({"type": "ROOM_DISCOVERY_QUERY"}, ensure_ascii=False).encode('utf-8')
                        for probe_ip in probe_targets:
                            try:
                                s.sendto(query_msg, (probe_ip, self.port))
                            except Exception:
                                pass
                        logger.debug(f"🔍 [ClusterDiscovery] 主动局域网探测已执行，共 {len(probe_targets)} 个目标")
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
