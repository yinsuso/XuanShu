     1|
     2|import socket
     3|import threading
     4|import json
     5|import time
     6|from typing import List, Dict, Any, Optional
     7|from logger import logger
     8|
     9|class ClusterDiscovery:
    10|    """局域网房间发现机制 (基于 UDP 广播)"""
    11|    
    12|    def __init__(self, port: int = 50005, room_name: str = "Default-Agent-Room"):
    13|        self.port = port
    14|        self.room_name = room_name
    15|        self.running = False
    16|        self.found_rooms = {} # {ip: room_info}
    17|        self.socket = None
    18|
    19|    def start_hosting(self):
    20|        """开启房主模式：持续广播房间信息"""
    21|        self.running = True
    22|        threading.Thread(target=self._broadcast_loop, daemon=True).start()
    23|        logger.info(f"🚀 [Cluster] 房主模式已开启，房间名: {self.room_name}, 端口: {self.port}")
    24|
    25|    def _broadcast_loop(self):
    26|        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    27|            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    28|            while self.running:
    29|                message = json.dumps({
    30|                    "type": "ROOM_ADVERTISEMENT",
    31|                    "room_name": self.room_name,
    32|                    "host_port": 30001 # 假设 Web/API 端口
    33|                }).encode('utf-8')
    34|                s.sendto(message, ('<broadcast>', self.port))
    35|                time.sleep(5) # 每5秒广播一次
    36|
    37|    def start_scanning(self):
    38|        """开启扫描模式：监听局域网内的房间"""
    39|        self.running = True
    40|        threading.Thread(target=self._scan_loop, daemon=True).start()
    41|        logger.info(f"🔍 [Cluster] 扫描模式已开启，正在搜寻可用房间...")
    42|
    43|    def _scan_loop(self):
    44|        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    45|            s.bind(('', self.port))
    46|            while self.running:
    47|                try:
    48|                    data, addr = s.recvfrom(1024)
    49|                    msg = json.loads(data.decode('utf-8'))
    50|                    if msg.get("type") == "ROOM_ADVERTISEMENT":
    51|                        self.found_rooms[addr[0]] = msg
    52|                        logger.info(f"✨ [Cluster] 发现房间: {msg['room_name']} (Host: {addr[0]})")
    53|                except Exception as e:
    54|                    logger.error(f"扫描出错: {e}")
    55|
    56|    def get_available_rooms(self) -> List[Dict[str, Any]]:
    57|        return [{"ip": ip, **info} for ip, info in self.found_rooms.items()]
    58|
    59|    def stop(self):
    60|        self.running = False
    61|