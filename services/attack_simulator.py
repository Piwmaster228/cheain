import copy
import logging
from typing import Tuple, Optional, List

logger = logging.getLogger(__name__)


class AttackSimulator:

    def __init__(self, blockchain):
        self.bc = blockchain
        self._copy: Optional[List] = None   #копия chain

    #копия

    def make_copy(self) -> int:
        self._copy = copy.deepcopy(self.bc.chain)
        logger.info("Копия цепочки создана: %d блоков", len(self._copy))
        return len(self._copy)

    @property
    def copy_ready(self) -> bool:
        return self._copy is not None

    def copy_info(self) -> str:
        if self._copy is None:
            return "Копия не создана"
        blocks = len(self._copy)
        txs = sum(len(b.transactions) for b in self._copy)
        return f"Копия: {blocks} блоков, {txs} транзакций"

    #атака

    def tamper(self, block_index: int, tx_index: int,
               new_amount: float) -> Tuple[bool, str]:
        """
        Подделать сумму и пересчитать хеш изменённого блока.
        Следующий блок хранит СТАРЫЙ previous_hash → цепочка рвётся на нём.
        """
        ok, err = self._check_indices(block_index, tx_index)
        if not ok:
            return False, err

        block = self._copy[block_index]
        tx = block.transactions[tx_index]

        old_amount = tx.amount
        tx.amount = new_amount
        tx.net_amount = round(new_amount * (1 - tx.commission / 100), 2)
        tx.recompute_tx_hash()       # обновить хеш транзакции
        block.recompute_merkle_root()  # обновить корень Меркла

        old_hash = block.hash
        block.hash = block.calculate_hash()

        is_last = block_index == len(self._copy) - 1
        warning = ("\n  ВНИМАНИЕ: это последний блок — следующего нет, "
                   "разрыв цепи не обнаружится при проверке!") if is_last else ""

        msg = (
            f"[Подделать]  Блок #{block_index}, TX #{tx_index}\n"
            f"  Сумма: {old_amount:,.2f} -> {new_amount:,.2f}\n"
            f"  Хеш блока #{block_index} пересчитан:\n"
            f"    старый: {old_hash}\n"
            f"    новый:  {block.hash}\n"
            f"  Блок #{block_index + 1} по-прежнему хранит старый previous_hash "
            f"-> разрыв будет обнаружен на блоке #{block_index + 1}.{warning}"
        )
        logger.warning(msg)
        return True, msg

    def replace_sender(self, block_index: int, tx_index: int,
                       new_sender: str) -> Tuple[bool, str]:
        """
        Подменить отправителя транзакции (кража идентичности).
        Подпись остаётся старой — несоответствие легко обнаружить при верификации.
        """
        ok, err = self._check_indices(block_index, tx_index)
        if not ok:
            return False, err

        block = self._copy[block_index]
        tx = block.transactions[tx_index]

        old_sender = tx.sender
        tx.sender = new_sender
        tx.recompute_tx_hash()
        block.recompute_merkle_root()

        old_hash = block.hash
        block.hash = block.calculate_hash()

        msg = (
            f"[Подмена отправителя]  Блок #{block_index}, TX #{tx_index}\n"
            f"  Отправитель: «{old_sender}» -> «{new_sender}»\n"
            f"  Подпись транзакции НЕ обновлена — верификация подписи выявит подлог.\n"
            f"  Хеш блока #{block_index}:\n"
            f"    старый: {old_hash}\n"
            f"    новый:  {block.hash}\n"
            f"  Блок #{block_index + 1} хранит старый previous_hash -> разрыв на блоке #{block_index + 1}."
        )
        logger.warning(msg)
        return True, msg

    def drop_transaction(self, block_index: int, tx_index: int) -> Tuple[bool, str]:
        """
        Удалить транзакцию из блока (атака цензуры).
        Корень Меркла и хеш блока пересчитываются — разрыв виден в следующем блоке.
        """
        ok, err = self._check_indices(block_index, tx_index)
        if not ok:
            return False, err

        block = self._copy[block_index]
        tx = block.transactions.pop(tx_index)

        block.recompute_merkle_root()
        old_hash = block.hash
        block.hash = block.calculate_hash()

        msg = (
            f"[Удаление транзакции]  Блок #{block_index}\n"
            f"  Удалена TX #{tx_index}: {tx.sender} -> {tx.receiver}, "
            f"сумма {tx.amount:,.2f}\n"
            f"  В блоке #{block_index} осталось транзакций: {len(block.transactions)}\n"
            f"  Хеш блока #{block_index} пересчитан:\n"
            f"    старый: {old_hash}\n"
            f"    новый:  {block.hash}\n"
            f"  Блок #{block_index + 1} хранит старый previous_hash -> разрыв на блоке #{block_index + 1}."
        )
        logger.warning(msg)
        return True, msg

    def replay_transaction(self, src_block: int, src_tx: int,
                           dst_block: int) -> Tuple[bool, str]:
        """
        Скопировать транзакцию из src_block в dst_block (атака повторного воспроизведения / двойная трата).
        Хеш dst_block пересчитывается; следующий за ним блок хранит старый previous_hash.
        """
        if self._copy is None:
            return False, "Сначала создайте копию цепочки."
        for idx, name in ((src_block, "src_block"), (dst_block, "dst_block")):
            if idx <= 0 or idx >= len(self._copy):
                return False, f"Блок #{idx} ({name}) не существует в копии."
        if src_block == dst_block:
            return False, "Исходный и целевой блоки должны быть разными."
        src = self._copy[src_block]
        if not src.transactions:
            return False, f"Блок #{src_block} не содержит транзакций."
        if src_tx >= len(src.transactions):
            return False, f"TX #{src_tx} не существует в блоке #{src_block}."

        import copy as _copy_mod
        tx_clone = _copy_mod.deepcopy(src.transactions[src_tx])

        dst = self._copy[dst_block]
        dst.transactions.append(tx_clone)
        dst.recompute_merkle_root()

        old_hash = dst.hash
        dst.hash = dst.calculate_hash()

        is_last = dst_block == len(self._copy) - 1
        warning = ("\n  ВНИМАНИЕ: dst_block последний — разрыв не обнаружится!") if is_last else ""

        msg = (
            f"[Повторное воспроизведение]  TX #{src_tx} из блока #{src_block} -> блок #{dst_block}\n"
            f"  Транзакция: {tx_clone.sender} -> {tx_clone.receiver}, "
            f"сумма {tx_clone.amount:,.2f}\n"
            f"  В блоке #{dst_block} теперь {len(dst.transactions)} транзакций.\n"
            f"  Хеш блока #{dst_block} пересчитан:\n"
            f"    старый: {old_hash}\n"
            f"    новый:  {dst.hash}\n"
            f"  Блок #{dst_block + 1} хранит старый previous_hash -> разрыв на блоке #{dst_block + 1}.{warning}"
        )
        logger.warning(msg)
        return True, msg

    def recompute_from(self, block_index: int) -> Tuple[bool, str]:
        """
        Пересчитать хеши и previous_hash для всех блоков начиная с block_index
        (симуляция атаки 51% — злоумышленник перестраивает хвост цепи).
        После этого validate_copy() покажет цепочку как «корректную».
        """
        if self._copy is None:
            return False, "Сначала создайте копию цепочки."
        if block_index <= 0 or block_index >= len(self._copy):
            return False, f"Блок #{block_index} не существует в копии."

        updated = []
        for i in range(block_index, len(self._copy)):
            blk = self._copy[i]
            if i > 0:
                blk.previous_hash = self._copy[i - 1].hash
            old_h = blk.hash
            blk.hash = blk.calculate_hash()
            updated.append(f"  Блок #{i}: {old_h[:12]}… -> {blk.hash[:12]}…")

        msg = (
            f"[Атака 51%]  Пересчёт цепи с блока #{block_index} "
            f"по блок #{len(self._copy) - 1}\n"
            + "\n".join(updated) +
            f"\n  Цепочка в копии теперь выглядит валидной — "
            f"validate_copy() не обнаружит разрыва.\n"
            f"  Обнаружение возможно только при сравнении с оригинальной цепью."
        )
        logger.warning(msg)
        return True, msg

    #валидация копии

    def validate_copy(self) -> Tuple[bool, str]:
        """Проверить целостность КОПИИ."""
        if self._copy is None:
            return None, "Копия не создана — нажмите «Создать копию»"

        for i in range(1, len(self._copy)):
            cur  = self._copy[i]
            prev = self._copy[i - 1]

            if cur.previous_hash != prev.hash:
                return False, (
                    f"Цепочка нарушена на блоке #{cur.index}:\n"
                    f"  Хеш блока #{prev.index}:              {prev.hash}\n"
                    f"  previous_hash блока #{cur.index}: {cur.previous_hash}\n"
                    f"  Хеши не совпадают — подделка обнаружена!"
                )

        return True, f"Копия корректна — {len(self._copy)} блоков проверено"

    #вспомогательные

    def _check_indices(self, block_index: int, tx_index: int) -> Tuple[bool, str]:
        if self._copy is None:
            return False, "Сначала создайте копию цепочки."
        if block_index <= 0 or block_index >= len(self._copy):
            return False, f"Блок #{block_index} не существует в копии."
        block = self._copy[block_index]
        if not block.transactions:
            return False, f"Блок #{block_index} не содержит транзакций."
        if tx_index >= len(block.transactions):
            return False, f"TX #{tx_index} не существует (в блоке {len(block.transactions)} TX)."
        return True, ""
