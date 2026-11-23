from dataclasses import dataclass
from typing import Any

import httpx
from eth_abi import decode, encode
from eth_abi.exceptions import DecodingError
from eth_utils import keccak

from app.config import get_settings
from app.errors import api_error


def hex_hash(data: bytes) -> str:
    return "0x" + keccak(data).hex()


def escrow_id(client: str, project_key: str) -> str:
    return hex_hash(encode(["address", "bytes32"], [client, bytes.fromhex(project_key[2:])]))


@dataclass(frozen=True)
class Event:
    name: str
    indexed: tuple[str, ...]
    data: tuple[str, ...]

    @property
    def topic(self) -> str:
        signature = f"{self.name}({','.join(self.indexed + self.data)})"
        return hex_hash(signature.encode())

    def decode(self, log: dict) -> tuple:
        words = b"".join(bytes.fromhex(word[2:]) for word in log["topics"][1:])
        payload = bytes.fromhex(log["data"][2:])
        if len(words) != 32 * len(self.indexed) or len(payload) != 32 * len(self.data):
            raise ValueError("Unexpected escrow event length")
        return decode(self.indexed, words) + decode(self.data, payload)


FUNDED = Event("EscrowFunded", ("bytes32", "bytes32", "address"),
               ("address", "uint256", "uint256", "uint64", "bytes32"))
RELEASED = Event("PaymentReleased", ("bytes32", "address"), ("uint256", "uint256"))
REFUNDED = Event("EscrowRefunded", ("bytes32", "address"), ("uint256",))
RESOLVED = Event("DisputeResolved", ("bytes32",), ("uint16", "uint256", "uint256", "uint256", "bool"))
EVENTS = {event.topic: event for event in (FUNDED, RELEASED, REFUNDED, RESOLVED)}


class EscrowChain:
    def __init__(self, client: httpx.Client, chain_id: int):
        self.client = client
        if int(self.call("eth_chainId"), 16) != chain_id:
            raise api_error(503, "ESCROW_WRONG_RPC_CHAIN", "RPC ของ Escrow อยู่คนละเครือข่าย")

    def call(self, method: str, *params: Any) -> Any:
        url = get_settings().escrow_rpc_url.get_secret_value()
        if not url:
            raise api_error(503, "ESCROW_RPC_REQUIRED", "ยังไม่ได้ตั้งค่า RPC ฝั่งเซิร์ฟเวอร์สำหรับ Escrow")
        try:
            response = self.client.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict) or body.get("error") or "result" not in body:
                raise ValueError("Invalid JSON-RPC response")
            return body["result"]
        except (httpx.HTTPError, ValueError):
            raise api_error(503, "ESCROW_RPC_UNAVAILABLE", "อ่านข้อมูลจากเครือข่าย Escrow ไม่สำเร็จ กรุณาลองใหม่") from None

    def block(self, number: str = "finalized") -> dict:
        block = self.call("eth_getBlockByNumber", number, False)
        if not block:
            raise api_error(503, "ESCROW_BLOCK_UNAVAILABLE", "เครือข่ายยังไม่ส่งข้อมูลบล็อกให้ตรวจสอบ")
        return block

    def confirmed_block(self) -> dict:
        """Return the newest block whose events the backend accepts as settled."""
        confirmations = get_settings().escrow_confirmations
        if confirmations is None:
            return self.block()
        latest = int(self.block("latest")["number"], 16)
        return self.block(hex(max(latest - confirmations, 0)))

    def contract_read(self, address: str, signature: str, args: bytes = b"", block: str = "latest") -> bytes:
        calldata = hex_hash(signature.encode())[:10] + args.hex()
        result = self.call("eth_call", {"to": address, "data": calldata}, block)
        try:
            data = bytes.fromhex(result[2:])
            if len(data) < 32 or len(data) % 32:
                raise ValueError("Invalid ABI result")
            return data
        except (ValueError, TypeError):
            raise api_error(503, "ESCROW_CONTRACT_MISMATCH", "Smart Contract ไม่ตรงกับ ABI ของ Escrow v2") from None

    def is_occupied(self, contract: str, key: str, block: str = "latest") -> bool:
        data = self.contract_read(contract, "getEscrow(bytes32)", bytes.fromhex(key[2:]), block)
        return any(data[:32])  # First field of the static v2 Escrow tuple is the client address.

    def policy(self, contract: str) -> tuple[str, int, int]:
        try:
            (arbiter,) = decode(["address"], self.contract_read(contract, "arbiter()"))
            (revisions,) = decode(["uint8"], self.contract_read(contract, "maxRevisions()"))
            (duration,) = decode(["uint64"], self.contract_read(contract, "MAX_DURATION()"))
            return arbiter, revisions, duration
        except DecodingError:
            raise api_error(503, "ESCROW_CONTRACT_MISMATCH", "Smart Contract ไม่ตรงกับ ABI ของ Escrow v2") from None
