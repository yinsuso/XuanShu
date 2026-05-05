import pytest
from security import sign_message, verify_signature

def test_hmac_sign_verify():
    msg = {"type": "heartbeat", "node_id": "test1"}
    signed = sign_message(msg.copy(), "secret")
    assert "signature" in signed
    assert verify_signature(signed.copy(), "secret") is True
    signed["payload"] = "tampered"
    assert verify_signature(signed, "secret") is False
