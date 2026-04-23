// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
/**
 * @title PaymentChain
 * @notice Симулятор блокчейна мгновенных переводов.
 *         Демонстрирует хеш-цепочку SHA3 (keccak256) и атаку подделки транзакции.
 *
 * Логика:
 *  - Транзакции накапливаются в пуле.
 *  - Блок закрывается при достижении TRANSACTIONS_PER_BLOCK транзакций
 *    или принудительно через sealBlock().
 *  - Целостность цепочки проверяется через validateChain().
 *  - Симулятор атаки: makeCopy() -> tamper() -> validateCopy().
 */
contract PaymentChain {

    uint256 public constant TRANSACTIONS_PER_BLOCK = 5;

    // ─── Структуры ────────────────────────────────────────────────────────────

    struct TxData {
        string  txId;          // 8-символьный HEX-идентификатор
        string  reference;     // номер перевода
        string  sender;        // отправитель
        string  receiver;      // получатель
        bytes32 passportHash;  // keccak256(паспорт)
        uint256 amount;        // сумма в копейках (×100)
        uint256 commission;    // комиссия в базисных пунктах (0-9999)
        uint256 netAmount;     // к получению в копейках
        uint256 timestamp;     // unix-секунды
        bytes32 signature;     // keccak256(поля транзакции)
    }

    struct ChainBlock {
        uint256 index;
        bytes32 prevHash;
        bytes32 blockHash;
        uint256 timestamp;
        uint256 txCount;
    }

    // ─── Хранилище ────────────────────────────────────────────────────────────

    ChainBlock[]                    public chain;
    mapping(uint256 => TxData[])    private _blockTxs;
    TxData[]                        private _pool;

    // Атакованная копия
    ChainBlock[]                    private _copy;
    mapping(uint256 => TxData[])    private _copyTxs;
    bool public copyReady;

    // ─── События ─────────────────────────────────────────────────────────────

    event TransactionAdded(
        string  indexed txId,
        string  sender,
        string  receiver,
        uint256 amount
    );
    event BlockSealed(uint256 indexed idx, bytes32 blockHash, uint256 txCount);
    event CopyCreated(uint256 blockCount);
    event Tampered(uint256 blockIdx, uint256 txIdx, uint256 oldAmount, uint256 newAmount);

    // ─── Конструктор ─────────────────────────────────────────────────────────

    constructor() {
        _pushGenesisBlock();
    }

    function _pushGenesisBlock() internal {
        bytes32 h = keccak256(abi.encodePacked(
            uint256(0), bytes32(0), block.timestamp, bytes32(0), uint256(0)
        ));
        chain.push(ChainBlock({
            index:     0,
            prevHash:  bytes32(0),
            blockHash: h,
            timestamp: block.timestamp,
            txCount:   0
        }));
    }

    // ─── Добавить перевод ─────────────────────────────────────────────────────

    /**
     * @param amount     сумма в копейках (целые копейки, напр. 5000000 = 50 000,00)
     * @param commission комиссия в базисных пунктах (напр. 50 = 0.50%)
     * @return blockCreated true, если был автоматически закрыт блок
     */
    function addTransaction(
        string calldata reference,
        string calldata sender,
        string calldata receiver,
        string calldata passportRaw,
        uint256 amount,
        uint256 commission
    ) external returns (bool blockCreated) {
        require(amount > 0,          "Amount must be > 0");
        require(commission < 10000,  "Commission must be < 100%");

        uint256 net = amount * (10000 - commission) / 10000;
        bytes32 ph  = keccak256(bytes(passportRaw));

        string memory txId = _shortHex(keccak256(abi.encodePacked(
            block.timestamp, sender, receiver, amount, _pool.length
        )));

        bytes32 sig = keccak256(abi.encodePacked(
            txId, reference, sender, receiver, amount, net, block.timestamp
        ));

        _pool.push(TxData({
            txId:         txId,
            reference:    reference,
            sender:       sender,
            receiver:     receiver,
            passportHash: ph,
            amount:       amount,
            commission:   commission,
            netAmount:    net,
            timestamp:    block.timestamp,
            signature:    sig
        }));

        emit TransactionAdded(txId, sender, receiver, amount);

        if (_pool.length >= TRANSACTIONS_PER_BLOCK) {
            _seal();
            return true;
        }
        return false;
    }

    // ─── Принудительно закрыть блок ──────────────────────────────────────────

    function sealBlock() external returns (bool) {
        if (_pool.length == 0) return false;
        _seal();
        return true;
    }

    // ─── Внутренний запечатывания блока ──────────────────────────────────────

    function _seal() internal {
        uint256 idx  = chain.length;
        bytes32 prev = chain[idx - 1].blockHash;
        uint256 cnt  = _pool.length < TRANSACTIONS_PER_BLOCK
            ? _pool.length
            : TRANSACTIONS_PER_BLOCK;

        bytes32 txsHash = bytes32(0);
        for (uint256 i = 0; i < cnt; i++) {
            _blockTxs[idx].push(_pool[i]);
            txsHash = keccak256(abi.encodePacked(
                txsHash, _pool[i].txId, _pool[i].amount, _pool[i].timestamp
            ));
        }

        // Сдвинуть оставшиеся транзакции
        uint256 rem = _pool.length - cnt;
        for (uint256 i = 0; i < rem; i++) _pool[i] = _pool[cnt + i];
        for (uint256 i = 0; i < cnt;  i++) _pool.pop();

        bytes32 h = keccak256(abi.encodePacked(
            idx, prev, block.timestamp, txsHash, cnt
        ));

        chain.push(ChainBlock({
            index:     idx,
            prevHash:  prev,
            blockHash: h,
            timestamp: block.timestamp,
            txCount:   cnt
        }));

        emit BlockSealed(idx, h, cnt);
    }

    // ─── Валидация оригинальной цепочки ──────────────────────────────────────

    function validateChain()
        external view
        returns (bool ok, string memory message)
    {
        for (uint256 i = 1; i < chain.length; i++) {
            if (chain[i].prevHash != chain[i - 1].blockHash)
                return (false, string(abi.encodePacked(
                    "Chain broken at block #", _u2s(i)
                )));

            bytes32 recalc = _calcBlockHash(i, false);
            if (recalc != chain[i].blockHash)
                return (false, string(abi.encodePacked(
                    "Block #", _u2s(i), ": hash mismatch (data altered)"
                )));
        }
        return (true, string(abi.encodePacked(
            "Chain valid - ", _u2s(chain.length), " blocks verified"
        )));
    }

    // ─── Атака: создать копию ────────────────────────────────────────────────

    function makeCopy() external {
        // Очистить предыдущую копию
        for (uint256 i = 0; i < _copy.length; i++) {
            delete _copyTxs[i];
        }
        delete _copy;

        // Скопировать цепочку
        for (uint256 i = 0; i < chain.length; i++) {
            _copy.push(chain[i]);
            for (uint256 j = 0; j < _blockTxs[i].length; j++) {
                _copyTxs[i].push(_blockTxs[i][j]);
            }
        }
        copyReady = true;
        emit CopyCreated(_copy.length);
    }

    // ─── Атака: подделать транзакцию в копии ─────────────────────────────────

    function tamper(
        uint256 blockIdx,
        uint256 txIdx,
        uint256 newAmount
    ) external {
        require(copyReady,                             "Make a copy first");
        require(blockIdx > 0 && blockIdx < _copy.length, "Block does not exist");
        require(_copyTxs[blockIdx].length > 0,         "Block has no transactions");
        require(txIdx < _copyTxs[blockIdx].length,     "TX does not exist");

        TxData storage t = _copyTxs[blockIdx][txIdx];
        uint256 oldAmount = t.amount;

        t.amount    = newAmount;
        t.netAmount = newAmount * (10000 - t.commission) / 10000;

        // Пересчитать хеш только изменённого блока
        bytes32 txsHash = bytes32(0);
        for (uint256 j = 0; j < _copyTxs[blockIdx].length; j++) {
            txsHash = keccak256(abi.encodePacked(
                txsHash,
                _copyTxs[blockIdx][j].txId,
                _copyTxs[blockIdx][j].amount,
                _copyTxs[blockIdx][j].timestamp
            ));
        }
        _copy[blockIdx].blockHash = keccak256(abi.encodePacked(
            _copy[blockIdx].index,
            _copy[blockIdx].prevHash,
            _copy[blockIdx].timestamp,
            txsHash,
            _copy[blockIdx].txCount
        ));

        // Следующий блок хранит СТАРЫЙ previous_hash → разрыв цепи

        emit Tampered(blockIdx, txIdx, oldAmount, newAmount);
    }

    // ─── Валидация копии ─────────────────────────────────────────────────────

    function validateCopy()
        external view
        returns (bool ok, string memory message)
    {
        require(copyReady, "No copy created");

        for (uint256 i = 1; i < _copy.length; i++) {
            if (_copy[i].prevHash != _copy[i - 1].blockHash)
                return (false, string(abi.encodePacked(
                    "Copy broken at block #", _u2s(i),
                    ": prevHash mismatch - tampering detected!"
                )));
        }
        return (true, string(abi.encodePacked(
            "Copy valid - ", _u2s(_copy.length), " blocks verified"
        )));
    }

    // ─── View-геттеры ────────────────────────────────────────────────────────

    function chainLength()    external view returns (uint256) { return chain.length; }
    function poolSize()       external view returns (uint256) { return _pool.length; }
    function copyLength()     external view returns (uint256) { return _copy.length; }

    function getBlock(uint256 idx)
        external view returns (ChainBlock memory) { return chain[idx]; }

    function getBlockTxCount(uint256 blockIdx)
        external view returns (uint256) { return _blockTxs[blockIdx].length; }

    function getBlockTx(uint256 blockIdx, uint256 txIdx)
        external view returns (TxData memory) { return _blockTxs[blockIdx][txIdx]; }

    function getPoolTx(uint256 idx)
        external view returns (TxData memory) { return _pool[idx]; }

    function getCopyBlock(uint256 idx)
        external view returns (ChainBlock memory) { return _copy[idx]; }

    function getCopyTxCount(uint256 blockIdx)
        external view returns (uint256) { return _copyTxs[blockIdx].length; }

    function getCopyTx(uint256 blockIdx, uint256 txIdx)
        external view returns (TxData memory) { return _copyTxs[blockIdx][txIdx]; }

    // ─── Внутренние утилиты ──────────────────────────────────────────────────

    function _calcBlockHash(uint256 idx, bool useCopy)
        internal view returns (bytes32)
    {
        ChainBlock storage b   = useCopy ? _copy[idx]    : chain[idx];
        TxData[]   storage txs = useCopy ? _copyTxs[idx] : _blockTxs[idx];

        bytes32 txsHash = bytes32(0);
        for (uint256 i = 0; i < txs.length; i++) {
            txsHash = keccak256(abi.encodePacked(
                txsHash, txs[i].txId, txs[i].amount, txs[i].timestamp
            ));
        }
        return keccak256(abi.encodePacked(
            b.index, b.prevHash, b.timestamp, txsHash, b.txCount
        ));
    }

    /// @dev Первые 8 символов hex-представления bytes32 (uppercase)
    function _shortHex(bytes32 b) internal pure returns (string memory) {
        bytes memory HEX = "0123456789ABCDEF";
        bytes memory s = new bytes(8);
        for (uint256 i = 0; i < 4; i++) {
            s[i * 2]     = HEX[uint8(b[i]) >> 4];
            s[i * 2 + 1] = HEX[uint8(b[i]) & 0x0f];
        }
        return string(s);
    }

    /// @dev uint256 -> decimal string
    function _u2s(uint256 v) internal pure returns (string memory) {
        if (v == 0) return "0";
        uint256 tmp = v; uint256 len = 0;
        while (tmp != 0) { len++; tmp /= 10; }
        bytes memory b = new bytes(len);
        while (v != 0) { b[--len] = bytes1(uint8(48 + v % 10)); v /= 10; }
        return string(b);
    }
}
