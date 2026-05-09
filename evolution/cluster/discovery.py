
import socket
import threading
import json
import time
import uuid
from typing import List, Dict, Any, Optional
from logger import logger
from config import PORT_CLUSTER_MANAGER, PORT_WEB

class ClusterDiscovery:
    """局域网房间发现机制 (基于 UDP 广播) - 完全跨平台兼容"""
    
    def __init__(self, port: int = 50005, room_name: str = "Default-Agent-Room", room_id: str = None, host_port: int = 30001):
        self.port = port
        self.room_name = room_name
        self.room_id = room_id or str(uuid.uuid4())[:8]
        self.host_port = host_port
        self.running = False
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

    def start_hosting(self, extra_info: Dict[str, Any] = None):
        """开启房主模式：持续广播房间信息"""
        if self.running:
            return
        self.running = True
        threading.Thread(target=self._broadcast_loop, args=(extra_info or {},), daemon=True).start()
        logger.info(f"🚀 [ClusterDiscovery] 房主广播已开启，房间: {self.room_name}, UDP端口: {self.port}")

    def _broadcast_loop(self, extra_info: Dict[str, Any]):
        broadcast_ips = self._get_local_broadcast_ips()
        while self.running:
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
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    for bcast_ip in broadcast_ips:
                        try:
                            s.sendto(data, (bcast_ip, self.port))
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"广播循环异常: {e}")
            time.sleep(3) # 更频繁一点，3秒发一次

    def start_scanning(self):
        """开启扫描模式：监听局域网内的房间"""
        if self.running:
            return
        self.running = True
        threading.Thread(target=self._scan_loop, daemon=True).start()
        logger.info(f"🔍 [ClusterDiscovery] 扫描模式已开启，正在搜寻局域网房间...")

    def _scan_loop(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind(('', self.port))
                except Exception as bind_e:
                    logger.warning(f"端口{self.port}被占用，尝试随机端口监听: {bind_e}")
                    s.bind(('', 0))
                s.settimeout(2.0)
                while self.running:
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
                                "timestamp": msg.get("timestamp", time.time())
                            }
                            logger.info(f"✨ [ClusterDiscovery] 发现局域网房间: {msg.get('room_name')} @ {addr[0]}")
                    except socket.timeout:
                        continue
                    except Exception as e:
                        logger.debug(f"扫描接收异常: {e}")
        except Exception as e:
            logger.error(f"扫描循环失败: {e}")

    def get_available_rooms(self) -> List[Dict[str, Any]]:
        """获取当前发现的所有房间（过滤5秒内的新房间）"""
        now = time.time()
        result = []
        for room in self.found_rooms.values():
            ts = room.get("timestamp", 0)
            if now - ts < 10: # 10秒内的才保留
                result.append(room)
        return result

    def stop(self):
        """停止所有广播和扫描线程"""
        self.running = False
        logger.info("[ClusterDiscovery] 已停止发现服务")
