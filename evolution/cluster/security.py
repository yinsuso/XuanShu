import hmac
import hashlib
import json
import ssl
from pathlib import Path
from typing import Dict, Any

def sign_message(msg_dict: Dict[str, Any], secret_key: str) -> Dict[str, Any]:
    """对消息字典进行 HMAC‑SHA256 签名，返回附加 signature 的新字典"""
    # 排序 key 保证一致性
    payload = json.dumps(msg_dict, sort_keys=True, ensure_ascii=False).encode('utf-8')
    signature = hmac.new(secret_key.encode('utf-8'), payload, hashlib.sha256).hexdigest()
    msg_dict['signature'] = signature
    return msg_dict

def verify_signature(msg_dict: Dict[str, Any], secret_key: str) -> bool:
    """验证消息签名，无 signature 字段或验证失败返回 False"""
    sig = msg_dict.pop('signature', None)
    if sig is None:
        return False
    payload = json.dumps(msg_dict, sort_keys=True, ensure_ascii=False).encode('utf-8')
    expected = hmac.new(secret_key.encode('utf-8'), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)

def create_ssl_context(cert_path: str | Path, key_path: str | Path) -> ssl.SSLContext:
    """创建服务端/客户端共用的 SSL 上下文"""
    cert_path = Path(cert_path)
    key_path = Path(key_path)
    if not cert_path.exists() or not key_path.exists():
        raise FileNotFoundError(f"TLS 证书或密钥不存在: {cert_path} / {key_path}")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    return context
