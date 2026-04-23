import logging
from typing import List, Tuple

from models.transaction import Transaction
from models.block import Block
from services.db_service import init_db, save_block, load_chain

logger = logging.getLogger(__name__)

TRANSACTIONS_PER_BLOCK = 5 
BLOCK_TIMEOUT_SECONDS  = 60

class Blockchain:

    def __init__(self):
        self.pending_transactions: List[Transaction] = []

        init_db()
        saved = load_chain()
        if saved:
            self.chain = saved
            logger.info("Цепочка загружена из БД: %d блоков", len(self.chain))
        else:
            first_block = Block(index=0, previous_hash="0" * 64, transactions=[])
            self.chain: List[Block] = [first_block]
            save_block(first_block)
            logger.info("Новая цепочка создана. Блок #0: %s", first_block.hash[:16])

    #добавление транзакции

    def add_transaction(self, tx: Transaction) -> bool:
        """Добавить транзакцию в пул. Возвращает True, если был автоматически создан блок."""
        if tx.amount <= 0:
            raise ValueError("Сумма перевода должна быть больше нуля")
        if not (0 <= tx.commission < 100):
            raise ValueError("Комиссия должна быть от 0 до 100%")

        self.pending_transactions.append(tx)
        logger.info("TX %s добавлена в пул (%d/%d)",
                    tx.transaction_id, len(self.pending_transactions), TRANSACTIONS_PER_BLOCK)

        if len(self.pending_transactions) >= TRANSACTIONS_PER_BLOCK:
            self._seal_block()
            return True
        return False

    def seal_block(self) -> bool:
        """Закрыть блок принудительно (даже если транзакций меньше порога)."""
        if not self.pending_transactions:
            return False
        self._seal_block()
        return True

    def _seal_block(self):
        txs = self.pending_transactions[:TRANSACTIONS_PER_BLOCK]
        self.pending_transactions = self.pending_transactions[TRANSACTIONS_PER_BLOCK:]
        block = Block(
            index=len(self.chain),
            previous_hash=self.chain[-1].hash,
            transactions=txs,
        )
        self.chain.append(block)
        save_block(block)
        logger.info("Блок #%d закрыт и сохранён в БД: %s", block.index, block.hash[:16])

    #проверка цепочки

    def validate_chain(self) -> Tuple[bool, str]:
        """Проверить целостность каждого блока и связность цепочки."""
        for i in range(1, len(self.chain)):
            cur  = self.chain[i]
            prev = self.chain[i - 1]

            if cur.hash != cur.calculate_hash():
                return False, f"Блок #{cur.index}: данные изменены (хеш не совпадает)"

            if cur.previous_hash != prev.hash:
                return False, f"Блок #{cur.index}: связь с блоком #{prev.index} нарушена"

        return True, f"Цепочка корректна — {len(self.chain)} блоков проверено"

