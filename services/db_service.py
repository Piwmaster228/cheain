import sqlite3
import os
from typing import List

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "blockchain.db")

SCHEMA_VERSION = 2   # увеличить при изменении схемы


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Создать таблицы. При несовпадении версии схемы — пересоздать БД."""
    with _connect() as conn:
        # Таблица версии схемы
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)")
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        current = row["version"] if row else 0

        if current != SCHEMA_VERSION:
            # Схема устарела — сбрасываем всё
            conn.execute("DROP TABLE IF EXISTS transactions")
            conn.execute("DROP TABLE IF EXISTS blocks")
            conn.execute("DELETE FROM schema_version")
            conn.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,))

        conn.execute("""
            CREATE TABLE IF NOT EXISTS blocks (
                idx           INTEGER PRIMARY KEY,
                previous_hash TEXT NOT NULL,
                timestamp     TEXT NOT NULL,
                nonce         INTEGER NOT NULL DEFAULT 0,
                hash          TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                block_idx      INTEGER NOT NULL,
                transaction_id TEXT NOT NULL,
                reference      TEXT,
                sender         TEXT,
                receiver       TEXT,
                passport_hash  TEXT,
                amount         REAL,
                commission     REAL,
                net_amount     REAL,
                timestamp      TEXT,
                signature      TEXT,
                FOREIGN KEY (block_idx) REFERENCES blocks(idx)
            )
        """)


def save_block(block) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO blocks (idx, previous_hash, timestamp, nonce, hash) "
            "VALUES (?, ?, ?, ?, ?)",
            (block.index, block.previous_hash, block.timestamp, block.nonce, block.hash),
        )
        for tx in block.transactions:
            conn.execute(
                "INSERT INTO transactions "
                "(block_idx, transaction_id, reference, sender, receiver, "
                " passport_hash, amount, commission, net_amount, timestamp, signature) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (block.index, tx.transaction_id, tx.reference,
                 tx.sender, tx.receiver, tx.passport_hash,
                 tx.amount, tx.commission, tx.net_amount,
                 tx.timestamp, tx.signature),
            )


def load_chain() -> List:
    from models.transaction import Transaction
    from models.block import Block

    with _connect() as conn:
        block_rows = conn.execute("SELECT * FROM blocks ORDER BY idx").fetchall()
        if not block_rows:
            return []

        chain = []
        for br in block_rows:
            tx_rows = conn.execute(
                "SELECT * FROM transactions WHERE block_idx = ? ORDER BY id",
                (br["idx"],)
            ).fetchall()

            transactions = [
                Transaction(
                    reference    = r["reference"],
                    sender       = r["sender"],
                    receiver     = r["receiver"],
                    amount       = r["amount"],
                    commission   = r["commission"],
                    transaction_id = r["transaction_id"],
                    timestamp    = r["timestamp"],
                    passport_hash = r["passport_hash"],
                    net_amount   = r["net_amount"],
                    signature    = r["signature"],
                )
                for r in tx_rows
            ]

            block = Block.__new__(Block)
            block.index         = br["idx"]
            block.previous_hash = br["previous_hash"]
            block.timestamp     = br["timestamp"]
            block.nonce         = br["nonce"]
            block.transactions  = transactions
            block.merkle_root   = Block.build_merkle_tree(
                [tx.tx_hash for tx in transactions]
            )[-1][0]
            block.hash          = br["hash"]
            chain.append(block)

        return chain
