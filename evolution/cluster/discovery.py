
import socket
import threading
import json
import time
from typing import List, Dict, Any, Optional
from logger import logger

class ClusterDiscovery:
    """局域网房间发现机制 (基于 UDP 广播)"""
    
    def __init__(self, port: int = 50005, room_name: str = "Default-Agent-Room"):
        self.port = port
        self.room_name = room_name
        self.running = False
        self.found_rooms = {} # {ip: room_info}
        self.socket = None

    def start_hosting(self):
        """开启房主模式：持续广播房间信息"""
        self.running = True
        threading.Thread(target=self._broadcast_loop, daemon=True).start()
        logger.info(f"🚀 [Cluster] 房主模式已开启，房间名: {self.room_name}, 端口: {self.port}")

    def _broadcast_loop(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            while self.running:
                message = json.dumps({
                    "type": "ROOM_ADVERTISEMENT",
                    "room_name": self.room_name,
                    "host_port": 30001 # 假设 Web/API 端口
                }).encode('utf-8')
                s.sendto(message, ('<broadcast>', self.port))
                time.sleep(5) # 每5秒广播一次

    def start_scanning(self):
        """开启扫描模式：监听局域网内的房间"""
        self.running = True
        threading.Thread(target=self._scan_loop, daemon=True).start()
        logger.info(f"🔍 [Cluster] 扫描模式已开启，正在搜寻可用房间...")

    def _scan_loop(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.bind(('', self.port))
            while self.running:
                try:
                    data, addr = s.recvfrom(1024)
                    msg = json.loads(data.decode('utf-8'))
                    if msg.get("type") == "ROOM_ADVERTISEMENT":
                        self.found_rooms[addr[0]] = msg
                        logger.info(f"✨ [Cluster] 发现房间: {msg['room_name']} (Host: {addr[0]})")
                except Exception as e:
                    logger.error(f"扫描出错: {e}")

    def get_available_rooms(self) -> List[Dict[str, Any]]:
        return [{"ip": ip, **info} for ip, info in self.found_rooms.items()]

    def stop(self):
        self.running = False
