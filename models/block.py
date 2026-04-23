import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List

from models.transaction import Transaction


@dataclass
class Block:
    index: int
    previous_hash: str
    transactions: List[Transaction]
    nonce: int = 0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    )
    merkle_root: str = field(init=False)
    hash: str = field(init=False)

    def __post_init__(self):
        self.merkle_root = self._compute_merkle_root()
        self.hash = self.calculate_hash()

    # Меркл

    @staticmethod
    def build_merkle_tree(tx_hashes: List[str]) -> List[List[str]]:
        if not tx_hashes:
            return [["0" * 64]]

        current = tx_hashes[:]
        levels: List[List[str]] = []

        while len(current) > 1:
            if len(current) % 2 == 1:
                current.append(current[-1])
            levels.append(current[:])
            next_level = []
            for i in range(0, len(current), 2):
                combined = current[i] + current[i + 1]
                next_level.append(hashlib.sha256(combined.encode()).hexdigest())
            current = next_level

        levels.append(current)
        return levels

    def _compute_merkle_root(self) -> str:
        tx_hashes = [tx.tx_hash for tx in self.transactions]
        return Block.build_merkle_tree(tx_hashes)[-1][0]

    def recompute_merkle_root(self):
        """Пересчитать корень Меркла (нужно после атаки на транзакции)."""
        self.merkle_root = self._compute_merkle_root()

    # Хеш блока

    def calculate_hash(self) -> str:
        """SHA-256 по полям блока; транзакции представлены корнем Меркла."""
        raw = f"{self.index}{self.previous_hash}{self.timestamp}{self.merkle_root}{self.nonce}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
