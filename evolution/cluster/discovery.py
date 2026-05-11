
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
    
    def __init__(self, port: int = UDP_DISCOVERY_PORT, room_name: str = "Default-Agent-Room", room_id: str = None, host_port: int = 30001):
        self.port = port
        self.room_name = room_name
        self.room_id = room_id or str(uuid.uuid4())[:8]
        self.host_port = host_port
        self.running = False
        self.broadcasting = False  # 单独标记广播是否在运行
        self.scanning = False       # 单独标记扫描是否在运行
        self.found_rooms = {} # {ip: room_info}
        self._broadcast_thread = None
        self._scan_thread = None

    def _get_local_broadcast_ips(self) -> List[str]:
        """获取所有可能的广播地址（跨平台兼容）"""
        broadcast_addrs = ['255.255.255.255']
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            parts = local_ip.split('.')
            if len(parts) == 4:
                broadcast_addrs.append(f"{parts[0]}.{parts[1]}.{parts[2]}.255")
        except Exception:
            pass
        return list(set(broadcast_addrs))

    def update_room_info(self, room_name: str, room_id: str, extra_info: Dict[str, Any] = None):
        """更新要广播的房间信息（创建房间后调用）"""
        self.room_name = room_name
        self.room_id = room_id
        logger.info(f"📢 [ClusterDiscovery] 房间信息已更新: {room_name} (ID: {room_id})")

    def start_hosting(self, extra_info: Dict[str, Any] = None):
        """开启房主模式：持续广播房间信息"""
        if self.broadcasting:
            logger.warning("[ClusterDiscovery] 广播已在运行，跳过重复启动")
            return
        self.broadcasting = True
        self.running = True  # 确保running标志正确设置
        threading.Thread(target=self._broadcast_loop, args=(extra_info or {},), daemon=True).start()
        logger.info(f"🚀 [ClusterDiscovery] 房主广播已开启，房间: {self.room_name}, UDP端口: {self.port}")

    def _broadcast_loop(self, extra_info: Dict[str, Any]):
        broadcast_ips = self._get_local_broadcast_ips()
        logger.info(f"📡 [ClusterDiscovery] 广播地址列表: {broadcast_ips}")
        while self.broadcasting:
            try:
                msg = {
                    "type": "ROOM_ADVERTISEMENT",
                    "room_name": self.room_name,
                    "room_id": self.room_id,
                    "manager_port": PORT_CLUSTER_MANAGER,
                    "web_port": PORT_WEB,
                    "timestamp": time.time(),
                    **extra_info
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
            time.sleep(3) # 更频繁一点，3秒发一次

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
            while self.scanning:
                try:
                    data, addr = s.recvfrom(4096)
                    msg = json.loads(data.decode('utf-8'))
                    if msg.get("type") == "ROOM_ADVERTISEMENT":
                        room_key = f"{addr[0]}:{msg.get('room_id', 'unknown')}"
                        self.found_rooms[room_key] = {
                            "ip": addr[0],
                            "room_name": msg.get("room_name"),
                            "room_id": msg.get("room_id"),
                            "manager_port": msg.get("manager_port", 30001),
                            "web_port": msg.get("web_port", 30000),
                            "owner_name": msg.get("owner_name"),
                            "owner_model": msg.get("owner_model"),
                            "timestamp": msg.get("timestamp", time.time())
                        }
                        logger.info(f"✨ [ClusterDiscovery] 发现局域网房间: {msg.get('room_name')} @ {addr[0]}, 模型: {msg.get('owner_model')}")
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
