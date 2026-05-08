#!/usr/bin/env python3
"""
CLI 工具：加入协作房间。
用法: python join_room.py [--host HOST] [--port PORT] [--room-id ID] [--worker-token TOKEN] [--config CONFIG]
"""

import argparse
import json
import os
import sys
import requests
from pathlib import Path

def load_config(config_path):
    if config_path and os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def main():
    parser = argparse.ArgumentParser(description='加入协作房间')
    parser.add_argument('--host', default='localhost', help='管理器主机地址 (默认: localhost)')
    parser.add_argument('--port', type=int, default=8000, help='管理器端口 (默认: 8000)')
    parser.add_argument('--room-id', help='房间 ID')
    parser.add_argument('--worker-token', help='工作器令牌')
    parser.add_argument('--config', help='配置文件路径 (JSON)')
    args = parser.parse_args()

    config = load_config(args.config)
    host = args.host or config.get('host', 'localhost')
    port = args.port or config.get('port', 8000)
    room_id = args.room_id or config.get('room_id')
    worker_token = args.worker_token or config.get('worker_token')

    if not room_id:
        room_id = input('请输入房间 ID: ').strip()
    if not worker_token:
        worker_token = input('请输入工作器令牌: ').strip()

    url = f'http://{host}:{port}/api/rooms/join'
    payload = {'room_id': room_id, 'worker_token': worker_token}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            print('✅ 加入成功:', data)
        else:
            print(f'❌ 加入失败: {resp.status_code} {resp.text}')
            sys.exit(1)
    except requests.RequestException as e:
        print(f'❌ 请求异常: {e}')
        sys.exit(1)

if __name__ == '__main__':
    main()
