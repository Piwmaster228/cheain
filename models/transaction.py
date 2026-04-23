import hashlib
import json
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field


@dataclass
class Transaction:
    reference:   str    #номер перевода
    sender:      str    #отправитель
    receiver:    str    #получатель
    amount:      float  #сумма перевода
    commission:  float  #комиссия

    passport_raw: str = ""

    #автогенер
    transaction_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8].upper())
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    )

    passport_hash: str   = ""
    net_amount:    float = 0.0
    signature:     str   = ""
    tx_hash:       str   = field(init=False)

    def __post_init__(self):
        if self.passport_raw and not self.passport_hash:
            self.passport_hash = hashlib.sha256(self.passport_raw.encode()).hexdigest()
        if not self.net_amount:
            self.net_amount = round(self.amount * (1 - self.commission / 100), 2)
        if not self.signature:
            self.signature = self._make_signature()
        self.tx_hash = self._compute_tx_hash()

    def _make_signature(self) -> str:
        data = f"{self.transaction_id}{self.reference}{self.sender}{self.receiver}{self.amount}{self.net_amount}{self.timestamp}"
        return hashlib.sha256(data.encode()).hexdigest()[:16].upper()

    def _compute_tx_hash(self) -> str:
        """SHA-256 по всем полям транзакции (кроме самого tx_hash)."""
        data = json.dumps({
            "transaction_id": self.transaction_id,
            "reference":      self.reference,
            "sender":         self.sender,
            "receiver":       self.receiver,
            "passport_hash":  self.passport_hash,
            "amount":         self.amount,
            "commission":     self.commission,
            "net_amount":     self.net_amount,
            "timestamp":      self.timestamp,
            "signature":      self.signature,
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()

    def recompute_tx_hash(self):
        """Пересчитать tx_hash после изменения данных транзакции."""
        self.tx_hash = self._compute_tx_hash()

    def to_dict(self) -> dict:
        return {
            "transaction_id": self.transaction_id,
            "reference":      self.reference,
            "sender":         self.sender,
            "receiver":       self.receiver,
            "passport_hash":  self.passport_hash,
            "amount":         self.amount,
            "commission":     self.commission,
            "net_amount":     self.net_amount,
            "timestamp":      self.timestamp,
            "signature":      self.signature,
            "tx_hash":        self.tx_hash,
        }

