import logging
import random
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from models.blockchain import Blockchain, TRANSACTIONS_PER_BLOCK, BLOCK_TIMEOUT_SECONDS
from models.block import Block
from models.transaction import Transaction
from services.attack_simulator import AttackSimulator

logger = logging.getLogger(__name__)

_REFS      = ["ПЕР-{:04d}".format(n) for n in range(1001, 1100)]
_SENDERS   = ["КЛИЕНТ-{:04d}".format(n) for n in range(101, 200)]
_RECEIVERS = ["КЛИЕНТ-{:04d}".format(n) for n in range(201, 300)]
_PASSPORTS = [str(random.randint(100_000_000, 999_999_999)) for _ in range(60)]


class MainWindow:

    def __init__(self, root: tk.Tk, bc: Blockchain):
        self.root = root
        self.bc   = bc
        self.atk  = AttackSimulator(bc)

        self._timer_job       = None
        self._timer_running   = False
        self._timer_remaining = 0
        self._auto_running    = False
        self._auto_thread     = None
        self._auto_scenario   = 0
        self._vis_selected    = None

        root.title("Мгновенные переводы — Hash-цепочка")
        root.geometry("1200x750")
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        nb = ttk.Notebook(root)
        nb.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.nb = nb

        tab1 = ttk.Frame(nb); nb.add(tab1, text="  Перевод  ")
        tab2 = ttk.Frame(nb); nb.add(tab2, text="  Блоки  ")
        tab3 = ttk.Frame(nb); nb.add(tab3, text="  Атака и проверка  ")

        self._build_tx_tab(tab1)
        self._build_blocks_tab(tab2)
        self._build_attack_tab(tab3)

        bar = tk.Frame(root, bd=1, relief=tk.SUNKEN)
        bar.pack(fill=tk.X)
        self.status_var = tk.StringVar(value="Готово")
        tk.Label(bar, textvariable=self.status_var, anchor=tk.W, padx=6
                 ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.timer_var = tk.StringVar(value="")
        tk.Label(bar, textvariable=self.timer_var, anchor=tk.E, padx=6, fg="navy"
                 ).pack(side=tk.RIGHT)

    # Вкладка 1 — Перевод

    def _build_tx_tab(self, parent):
        form = ttk.LabelFrame(parent, text=" Новый перевод ")
        form.pack(fill=tk.X, padx=12, pady=8)

        fields = [
            ("Номер перевода:",       "reference"),
            ("Отправитель:",          "sender"),
            ("Получатель:",           "receiver"),
            ("Идентификационный номер паспорта:",       "passport"),
            ("Сумма перевода:",       "amount"),
            ("Комиссия (%):",         "commission"),
        ]
        self.entries = {}
        for row, (label, key) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky=tk.E,
                                             padx=(8, 4), pady=4)
            e = ttk.Entry(form, width=32)
            e.grid(row=row, column=1, sticky=tk.W, pady=4)
            self.entries[key] = e

        btns = ttk.Frame(parent)
        btns.pack(fill=tk.X, padx=12, pady=4)
        ttk.Button(btns, text="Добавить перевод",
                   command=self._add_tx).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btns, text="Запечатать блок",
                   command=self._force_seal).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btns, text="Демо-данные",
                   command=self._fill_demo).pack(side=tk.LEFT)

        pool_row = ttk.Frame(parent)
        pool_row.pack(fill=tk.X, padx=12, pady=2)
        self.pool_var = tk.StringVar(value=f"Пул: 0 / {TRANSACTIONS_PER_BLOCK}")
        ttk.Label(pool_row, textvariable=self.pool_var).pack(side=tk.LEFT, padx=(0, 20))
        self.scenario_var = tk.StringVar(value="")
        ttk.Label(pool_row, textvariable=self.scenario_var, foreground="blue"
                  ).pack(side=tk.LEFT)

        gen = ttk.LabelFrame(parent, text=" Авто-генератор ")
        gen.pack(fill=tk.X, padx=12, pady=4)
        gen_inner = ttk.Frame(gen)
        gen_inner.pack(pady=6, padx=8, fill=tk.X)
        self.btn_start = ttk.Button(gen_inner, text="▶ Запустить", command=self._start_auto)
        self.btn_start.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_stop = ttk.Button(gen_inner, text="■ Остановить",
                                   command=self._stop_auto, state="disabled")
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 16))
        self.auto_status = tk.StringVar(value="")
        ttk.Label(gen_inner, textvariable=self.auto_status, foreground="gray"
                  ).pack(side=tk.LEFT)
        ttk.Label(gen, foreground="gray",
                  text="Сценарий 1: 5 переводов × 9 сек  → блок по количеству\n"
                       "Сценарий 2: 3 перевода  × 22 сек → блок по таймеру (60 сек)"
                  ).pack(anchor=tk.W, padx=8, pady=(0, 6))

        ttk.Label(parent, text="Журнал:").pack(anchor=tk.W, padx=12)
        self.log = scrolledtext.ScrolledText(parent, height=9, state="disabled",
                                             font=("Courier", 9))
        self.log.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))

    # Вкладка 2 — Блоки

    # Константы отрисовки цепочки (chain canvas)
    _VIS_BW   = 240   # ширина блока
    _VIS_BH   = 108   # высота блока
    _VIS_GAP  = 46    # расстояние для стрелки
    _VIS_Y    = 18    # отступ сверху
    _VIS_X0   = 16    # отступ слева

    # Константы отрисовки дерева Меркла
    _MK_NODE_W = 250
    _MK_NODE_H = 46
    _MK_H_GAP  = 10
    _MK_V_GAP  = 56
    _MK_PAD    = 20

    def _build_blocks_tab(self, parent):
        # ── Визуализация цепочки ──────────────────────────────────────
        vis_frame = ttk.LabelFrame(parent, text=" Цепочка блоков ")
        vis_frame.pack(fill=tk.X, padx=8, pady=(8, 4))

        canvas_h = self._VIS_Y + self._VIS_BH + 30
        self.vis_canvas = tk.Canvas(vis_frame, height=canvas_h,
                                    bg="#f5f5f5", highlightthickness=0)
        hscroll = ttk.Scrollbar(vis_frame, orient="horizontal",
                                 command=self.vis_canvas.xview)
        self.vis_canvas.configure(xscrollcommand=hscroll.set)
        self.vis_canvas.pack(fill=tk.X, expand=False)
        hscroll.pack(fill=tk.X)

        # ── Таблица блоков ────────────────────────────────────────────
        top = ttk.Frame(parent)
        top.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        cols = ("Блок", "Хеш", "Пред. хеш", "TX", "Время")
        self.tree = ttk.Treeview(top, columns=cols, show="headings", height=5)
        for col, width in zip(cols, (60, 200, 200, 40, 175)):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=width, anchor=tk.CENTER if col == "TX" else tk.W)

        vsb = ttk.Scrollbar(top, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.LEFT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self._show_block_details)

        ttk.Label(parent, text="Переводы выбранного блока:").pack(anchor=tk.W, padx=8)
        self.detail_text = scrolledtext.ScrolledText(parent, height=10, state="disabled",
                                                     font=("Courier", 9))
        self.detail_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))
        btn_row = ttk.Frame(parent)
        btn_row.pack(pady=(0, 6))
        ttk.Button(btn_row, text="Обновить",
                   command=self.refresh_blocks).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Дерево Меркла",
                   command=self._open_merkle_window).pack(side=tk.LEFT)
        self.refresh_blocks()

    # Вкладка 3 — Атака и проверка

    def _build_attack_tab(self, parent):
        # ── Секция 1: работа с копией
        copy_lf = ttk.LabelFrame(parent, text=" Копия цепочки для атаки ")
        copy_lf.pack(fill=tk.X, padx=12, pady=(8, 4))

        copy_row = ttk.Frame(copy_lf)
        copy_row.pack(pady=6, padx=8, fill=tk.X)

        ttk.Button(copy_row, text="Создать копию",
                   command=self._make_copy).pack(side=tk.LEFT, padx=(0, 12))

        self.copy_info_var = tk.StringVar(value="Копия не создана")
        ttk.Label(copy_row, textvariable=self.copy_info_var, foreground="gray"
                  ).pack(side=tk.LEFT)

        ttk.Label(copy_lf, foreground="gray",
                  text="Атака применяется к копии — оригинальная цепочка не изменяется."
                  ).pack(anchor=tk.W, padx=8, pady=(0, 6))

        # ── Секция 2: типы атак (Notebook)
        atk_lf = ttk.LabelFrame(parent, text=" Тип атаки ")
        atk_lf.pack(fill=tk.X, padx=12, pady=4)

        atk_nb = ttk.Notebook(atk_lf)
        atk_nb.pack(fill=tk.X, padx=6, pady=6)

        def _le(parent_row, text, default, width=5):
            ttk.Label(parent_row, text=text).pack(side=tk.LEFT, padx=(0, 2))
            e = ttk.Entry(parent_row, width=width)
            e.insert(0, default)
            e.pack(side=tk.LEFT, padx=(0, 10))
            return e

        # ── Вкладка: Подделать сумму ──────────────────────────────────
        tab_tamper = ttk.Frame(atk_nb)
        atk_nb.add(tab_tamper, text="  Подделать сумму  ")

        row1 = ttk.Frame(tab_tamper)
        row1.pack(pady=8, padx=8, fill=tk.X)
        self.atk_block  = _le(row1, "Блок №:", "1", 4)
        self.atk_tx     = _le(row1, "TX №:", "0", 4)
        self.atk_amount = _le(row1, "Новая сумма:", "999999", 10)
        ttk.Button(row1, text="Применить",
                   command=self._attack).pack(side=tk.LEFT)
        ttk.Label(tab_tamper, foreground="gray",
                  text="Изменяет сумму транзакции. Хеш блока пересчитывается,\n"
                       "следующий блок хранит старый previous_hash → разрыв."
                  ).pack(anchor=tk.W, padx=8, pady=(0, 6))

        # ── Вкладка: Подмена отправителя ─────────────────────────────
        tab_sender = ttk.Frame(atk_nb)
        atk_nb.add(tab_sender, text="  Подмена отправителя  ")

        row2 = ttk.Frame(tab_sender)
        row2.pack(pady=8, padx=8, fill=tk.X)
        self.atk_rs_block  = _le(row2, "Блок №:", "1", 4)
        self.atk_rs_tx     = _le(row2, "TX №:", "0", 4)
        self.atk_rs_sender = _le(row2, "Новый отправитель:", "ЗЛОУМЫШЛЕННИК", 16)
        ttk.Button(row2, text="Применить",
                   command=self._attack_replace_sender).pack(side=tk.LEFT)
        ttk.Label(tab_sender, foreground="gray",
                  text="Подменяет поле sender. Подпись транзакции остаётся старой —\n"
                       "несоответствие выявится при верификации подписи."
                  ).pack(anchor=tk.W, padx=8, pady=(0, 6))

        # ── Вкладка: Удалить транзакцию ───────────────────────────────
        tab_drop = ttk.Frame(atk_nb)
        atk_nb.add(tab_drop, text="  Удалить TX  ")

        row3 = ttk.Frame(tab_drop)
        row3.pack(pady=8, padx=8, fill=tk.X)
        self.atk_drop_block = _le(row3, "Блок №:", "1", 4)
        self.atk_drop_tx    = _le(row3, "TX №:", "0", 4)
        ttk.Button(row3, text="Применить",
                   command=self._attack_drop_tx).pack(side=tk.LEFT)
        ttk.Label(tab_drop, foreground="gray",
                  text="Удаляет транзакцию из блока (атака цензуры).\n"
                       "Корень Меркла и хеш пересчитываются → разрыв на следующем блоке."
                  ).pack(anchor=tk.W, padx=8, pady=(0, 6))

        # ── Вкладка: Повторное воспроизведение ────────────────────────
        tab_replay = ttk.Frame(atk_nb)
        atk_nb.add(tab_replay, text="  Повторное воспроизведение  ")

        row4 = ttk.Frame(tab_replay)
        row4.pack(pady=8, padx=8, fill=tk.X)
        self.atk_rp_src_block = _le(row4, "Блок-источник №:", "1", 4)
        self.atk_rp_src_tx    = _le(row4, "TX №:", "0", 4)
        self.atk_rp_dst_block = _le(row4, "Блок-цель №:", "2", 4)
        ttk.Button(row4, text="Применить",
                   command=self._attack_replay).pack(side=tk.LEFT)
        ttk.Label(tab_replay, foreground="gray",
                  text="Дублирует транзакцию в другой блок (двойная трата).\n"
                       "Одни и те же средства оказываются списанными дважды."
                  ).pack(anchor=tk.W, padx=8, pady=(0, 6))

        # ── Вкладка: Атака 51% ────────────────────────────────────────
        tab_51 = ttk.Frame(atk_nb)
        atk_nb.add(tab_51, text="  Атака 51%  ")

        row5 = ttk.Frame(tab_51)
        row5.pack(pady=8, padx=8, fill=tk.X)
        self.atk_51_block = _le(row5, "Начальный блок №:", "1", 4)
        ttk.Button(row5, text="Применить",
                   command=self._attack_51).pack(side=tk.LEFT)
        ttk.Label(tab_51, foreground="gray",
                  text="Пересчитывает previous_hash и хеши всей цепи начиная с блока.\n"
                       "После этого validate_copy() покажет цепочку как корректную.\n"
                       "Обнаружить подлог можно только сравнив с оригинальной цепью."
                  ).pack(anchor=tk.W, padx=8, pady=(0, 6))

        # ── Секция 3: проверка
        check_lf = ttk.LabelFrame(parent, text=" Проверка ")
        check_lf.pack(fill=tk.X, padx=12, pady=4)

        check_row = ttk.Frame(check_lf)
        check_row.pack(pady=8, padx=8, fill=tk.X)

        ttk.Button(check_row, text="Проверить оригинал",
                   command=self._validate_original).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(check_row, text="Проверить копию",
                   command=self._validate_copy).pack(side=tk.LEFT)

        self.val_orig = tk.StringVar(value="")
        self.val_copy = tk.StringVar(value="")
        self.lbl_val_orig = ttk.Label(check_lf, textvariable=self.val_orig,
                                      font=("TkDefaultFont", 10, "bold"))
        self.lbl_val_orig.pack(anchor=tk.W, padx=8)
        ttk.Label(check_lf, textvariable=self.val_copy,
                  font=("TkDefaultFont", 10, "bold")).pack(anchor=tk.W, padx=8, pady=(0, 6))

        # ── Журнал
        ttk.Label(parent, text="Журнал атак:").pack(anchor=tk.W, padx=12)
        self.atk_log = scrolledtext.ScrolledText(parent, height=8, state="disabled",
                                                 font=("Courier", 9))
        self.atk_log.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))

    # Логика — переводы

    def _add_tx(self, scenario_tag="") -> bool:
        try:
            tx = Transaction(
                reference  = self.entries["reference"].get().strip(),
                sender     = self.entries["sender"].get().strip(),
                receiver   = self.entries["receiver"].get().strip(),
                passport_raw = self.entries["passport"].get().strip(),
                amount     = float(self.entries["amount"].get()),
                commission = float(self.entries["commission"].get()),
            )
            pool_was_empty = len(self.bc.pending_transactions) == 0
            block_created  = self.bc.add_transaction(tx)
        except ValueError as e:
            messagebox.showerror("Ошибка ввода", str(e))
            return False

        tag = f"  [{scenario_tag}]" if scenario_tag else ""
        self._log(
            f"TX {tx.transaction_id}{tag}  |  Перевод: {tx.reference}\n"
            f"  {tx.sender} -> {tx.receiver}\n"
            f"  Сумма: {tx.amount:,.2f}  |  К получению: {tx.net_amount:,.2f}"
            f"  (комиссия {tx.commission}%)\n"
            f"  Хеш паспорта: {tx.passport_hash[:40]}..."
        )

        if block_created:
            self._cancel_timer()
            n = len(self.bc.chain) - 1
            self._log(f">>> БЛОК #{n} закрыт по количеству  |  хеш: {self.bc.chain[-1].hash[:24]}...")
            self.status_var.set(f"Блок #{n} закрыт по количеству переводов")
            self.refresh_blocks()
        elif pool_was_empty:
            self._start_timer()

        self.pool_var.set(f"Пул: {len(self.bc.pending_transactions)} / {TRANSACTIONS_PER_BLOCK}")
        for e in self.entries.values():
            e.delete(0, tk.END)
        return True

    def _force_seal(self):
        if not self.bc.pending_transactions:
            messagebox.showinfo("Пул пуст", "Нет переводов для закрытия блока.")
            return
        self._cancel_timer()
        self.bc.seal_block()
        n = len(self.bc.chain) - 1
        self.pool_var.set(f"Пул: 0 / {TRANSACTIONS_PER_BLOCK}")
        self._log(f">>> БЛОК #{n} закрыт принудительно  |  хеш: {self.bc.chain[-1].hash[:24]}...")
        self.refresh_blocks()
        self.status_var.set(f"Блок #{n} закрыт принудительно")

    def _fill_demo(self):
        for key, val in {
            "reference": "ПЕР-1042",
            "sender":    "КЛИЕНТ-0101",
            "receiver":  "КЛИЕНТ-0202",
            "passport":  "123456789",
            "amount":    "50000",
            "commission":"0.5",
        }.items():
            self.entries[key].delete(0, tk.END)
            self.entries[key].insert(0, val)

    def _log(self, msg: str):
        self.log.config(state="normal")
        self.log.insert(tk.END, msg + "\n" + "-" * 60 + "\n")
        self.log.see(tk.END)
        self.log.config(state="disabled")

    # Логика — блоки

    def refresh_visualization(self):
        """Перерисовать canvas-цепочку блоков."""
        c     = self.vis_canvas
        chain = self.bc.chain
        BW, BH, GAP, Y0, X0 = (
            self._VIS_BW, self._VIS_BH, self._VIS_GAP,
            self._VIS_Y,  self._VIS_X0,
        )
        c.delete("all")

        n         = len(chain)
        total_w   = X0 + n * (BW + GAP) + 20
        scroll_h  = Y0 + BH + 30
        c.configure(scrollregion=(0, 0, total_w, scroll_h))

        for i, block in enumerate(chain):
            x = X0 + i * (BW + GAP)
            y = Y0
            tag = f"blk{i}"

            # цвет фона
            if i == self._vis_selected:
                bg = "#1ecad3"   # выбранный — жёлтый
                outline_w = 3
            elif i == 0:
                bg = "#a92e49"   # генезис — голубой
                outline_w = 2
            else:
                bg = "#bbc846"   # обычный — зелёный
                outline_w = 2

            # прямоугольник
            c.create_rectangle(
                x, y, x + BW, y + BH,
                fill=bg, outline="#444", width=outline_w, tags=tag,
            )

            # заголовок
            title = f"Блок #{block.index}" + (" (genesis)" if i == 0 else "")
            c.create_text(
                x + BW // 2, y + 13,
                text=title, font=("TkDefaultFont", 9, "bold"), tags=tag,
            )
            c.create_line(x + 6, y + 24, x + BW - 6, y + 24,
                          fill="#666", tags=tag)

            # поля
            lines = [
                f"Hash:   {block.hash[:16]}…",
                f"Merkle: {block.merkle_root[:16]}…",
                f"TX: {len(block.transactions)}"
                + (f"  •  {block.timestamp[11:19]}" if block.timestamp else ""),
            ]
            for j, line in enumerate(lines):
                c.create_text(
                    x + 8, y + 36 + j * 20,
                    anchor="w", text=line,
                    font=("Courier", 8), tags=tag,
                )

            # номер под блоком
            c.create_text(
                x + BW // 2, y + BH + 12,
                text=f"#{block.index}",
                font=("TkDefaultFont", 8), fill="#777", tags=tag,
            )

            # стрелка к следующему блоку
            if i < n - 1:
                ax, ay = x + BW, y + BH // 2
                c.create_line(
                    ax, ay, ax + GAP, ay,
                    arrow=tk.LAST, fill="#555", width=2,
                )
                # подпись «prev_hash»
                c.create_text(
                    ax + GAP // 2, ay - 8,
                    text="prev", font=("TkDefaultFont", 7), fill="#888",
                )

            # клик
            c.tag_bind(tag, "<Button-1>",
                       lambda _e, idx=i: self._on_vis_click(idx))

    def _on_vis_click(self, block_idx: int):
        self._vis_selected = block_idx
        self.refresh_visualization()
        # синхронизировать таблицу и детали
        iid = str(block_idx)
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.see(iid)
            self._show_block_details()

    def refresh_blocks(self):
        self.tree.delete(*self.tree.get_children())
        for b in self.bc.chain:
            label = f"#{b.index}" + (" (нач.)" if b.index == 0 else "")
            self.tree.insert("", tk.END, iid=str(b.index), values=(
                label,
                b.hash[:22] + "…",
                b.previous_hash[:22] + "…",
                len(b.transactions),
                b.timestamp,
            ))
        self.refresh_visualization()

    def _show_block_details(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        block = self.bc.chain[int(sel[0])]

        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.insert(tk.END,
            f"Блок #{block.index}\n"
            f"  Хеш:          {block.hash}\n"
            f"  Пред. хеш:    {block.previous_hash}\n"
            f"  Корень Меркла:{block.merkle_root}\n"
            f"  Время:        {block.timestamp}\n"
        )
        if block.transactions:
            self.detail_text.insert(tk.END, f"\nПереводы ({len(block.transactions)}):\n")
            for tx in block.transactions:
                self.detail_text.insert(tk.END,
                    f"\n  TX {tx.transaction_id}  |  Перевод: {tx.reference}\n"
                    f"  {tx.sender} -> {tx.receiver}\n"
                    f"  Сумма: {tx.amount:,.2f}  |  К получению: {tx.net_amount:,.2f}"
                    f"  (комиссия {tx.commission}%)\n"
                    f"  Хеш паспорта: {tx.passport_hash}\n"
                    f"  Подпись:      {tx.signature}\n"
                    f"  Хеш TX:       {tx.tx_hash}\n"
                    f"  Время:        {tx.timestamp}\n"
                )

            # ── Дерево Меркла ──────────────────────────────────────────
            self.detail_text.insert(tk.END, "\n" + "─" * 60 + "\n")
            self.detail_text.insert(tk.END, "Дерево Меркла:\n\n")

            tx_hashes = [tx.tx_hash for tx in block.transactions]
            n_real    = len(tx_hashes)
            levels    = Block.build_merkle_tree(tx_hashes)

            # Отображаем от корня вниз к листьям
            for lvl_idx in range(len(levels) - 1, -1, -1):
                lvl = levels[lvl_idx]
                if lvl_idx == len(levels) - 1:
                    header = "Корень:"
                elif lvl_idx == 0:
                    header = f"Листья (хеши {n_real} транзакций):"
                else:
                    header = f"Уровень {lvl_idx}:"
                self.detail_text.insert(tk.END, f"  {header}\n")

                if lvl_idx == 0:
                    for i, h in enumerate(lvl):
                        if i < n_real:
                            tx = block.transactions[i]
                            self.detail_text.insert(tk.END,
                                f"    [{i}] {h[:24]}…"
                                f"  TX-{tx.transaction_id}"
                                f"  {tx.sender} → {tx.receiver}\n"
                            )
                        else:
                            self.detail_text.insert(tk.END,
                                f"    [{i}] {h[:24]}…  (дубль [{i - 1}])\n"
                            )
                else:
                    for i, h in enumerate(lvl):
                        self.detail_text.insert(tk.END,
                            f"    [{i}] {h[:24]}…\n"
                        )
                self.detail_text.insert(tk.END, "\n")
        else:
            self.detail_text.insert(tk.END, "\n  (блок не содержит переводов)\n")
        self.detail_text.config(state="disabled")

    # Логика — дерево Меркла

    def _open_merkle_window(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Нет выбора", "Выберите блок в таблице.")
            return
        block = self.bc.chain[int(sel[0])]
        if not block.transactions:
            messagebox.showinfo("Нет транзакций",
                                f"Блок #{block.index} не содержит транзакций.")
            return

        win = tk.Toplevel(self.root)
        win.title(f"Дерево Меркла — Блок #{block.index}")
        win.resizable(True, True)

        ttk.Label(
            win,
            text=(f"Блок #{block.index}  •  {len(block.transactions)} транзакций  •  "
                  f"Корень: {block.merkle_root[:36]}…"),
            font=("Courier", 9), padding=(8, 4),
        ).pack(fill=tk.X)

        frm = ttk.Frame(win)
        frm.pack(fill=tk.BOTH, expand=True)

        c  = tk.Canvas(frm, bg="white")
        hs = ttk.Scrollbar(frm, orient="horizontal", command=c.xview)
        vs = ttk.Scrollbar(frm, orient="vertical",   command=c.yview)
        c.configure(xscrollcommand=hs.set, yscrollcommand=vs.set)
        hs.pack(side=tk.BOTTOM, fill=tk.X)
        vs.pack(side=tk.RIGHT,  fill=tk.Y)
        c.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        c.bind("<MouseWheel>",
               lambda e: c.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        cw, ch = self._draw_merkle_canvas(c, block)
        win.geometry(f"{min(cw + 24, 1100)}x{min(ch + 56, 680)}")

    def _draw_merkle_canvas(self, c: tk.Canvas, block) -> tuple:
        """Отрисовать дерево Меркла на canvas. Возвращает (canvas_w, canvas_h)."""
        NW, NH = self._MK_NODE_W, self._MK_NODE_H
        HG, VG = self._MK_H_GAP,  self._MK_V_GAP
        PAD    = self._MK_PAD

        tx_hashes  = [tx.tx_hash for tx in block.transactions]
        n_real_tx  = len(tx_hashes)
        levels     = Block.build_merkle_tree(tx_hashes)
        n_lvl      = len(levels)
        n_leaves   = len(levels[0])

        slot = NW + HG

        # ── Позиции узлов ──────────────────────────────────────────────
        # Листья расставляем равномерно.
        cx_map: dict = {}
        for i in range(n_leaves):
            cx_map[(0, i)] = PAD + i * slot + NW // 2

        # Для каждого уровня выше листьев:
        #   • «реальных» узлов ceil(n_children / 2) — центрируем над двумя детьми
        #   • padding-дубль (если n_children нечётное) — сдвигаем вправо от последнего
        for lvl in range(1, n_lvl):
            n_children   = len(levels[lvl - 1])
            n_real_here  = (n_children + 1) // 2   # реальных узлов на этом уровне
            n_total_here = len(levels[lvl])

            for i in range(n_real_here):
                li = 2 * i
                ri = min(2 * i + 1, n_children - 1)  # правый ребёнок (или дубль левого)
                cx_map[(lvl, i)] = (cx_map[(lvl - 1, li)] + cx_map[(lvl - 1, ri)]) // 2

            # Padding-дубли на этом уровне — смещаем правее последнего реального
            for i in range(n_real_here, n_total_here):
                cx_map[(lvl, i)] = cx_map[(lvl, i - 1)] + slot

        def node_y(lvl: int) -> int:
            row = n_lvl - 1 - lvl   # корень → row 0 (верх), листья → row n_lvl-1
            return PAD + row * (NH + VG)

        # canvas_w считаем по реально занятым позициям
        canvas_w = max(cx_map.values()) + NW // 2 + PAD
        canvas_h = PAD + n_lvl * (NH + VG) + 24
        c.configure(scrollregion=(0, 0, canvas_w, canvas_h))
        c.delete("all")

        # ── Рёбра ──────────────────────────────────────────────────────
        for lvl in range(1, n_lvl):
            n_children  = len(levels[lvl - 1])
            n_real_here = (n_children + 1) // 2

            for i in range(n_real_here):   # только от реальных узлов
                px = cx_map[(lvl, i)]
                py = node_y(lvl) + NH
                li = 2 * i
                ri = min(2 * i + 1, n_children - 1)
                for ci in (li, ri):
                    chx = cx_map[(lvl - 1, ci)]
                    chy = node_y(lvl - 1)
                    # пунктир, если правый ребёнок — дубль левого
                    dash = (4, 3) if (ci == ri and li != ri - 1) else ()
                    c.create_line(px, py, chx, chy,
                                  fill="#bbb", width=1, dash=dash)

        # ── Узлы ───────────────────────────────────────────────────────
        COL_ROOT  = "#c86726"
        COL_INNER = "#d126bd"
        COL_LEAF  = "#0ad2c1"
        COL_DUP   = "#bae521"

        for lvl in range(n_lvl):
            n_children  = len(levels[lvl - 1]) if lvl > 0 else 0
            n_real_here = (n_children + 1) // 2 if lvl > 0 else n_real_tx

            for i, h in enumerate(levels[lvl]):
                cx = cx_map[(lvl, i)]
                y  = node_y(lvl)
                x  = cx - NW // 2

                is_root = (lvl == n_lvl - 1)
                is_leaf = (lvl == 0)
                is_dup  = (not is_root) and (i >= n_real_here)

                fill = (COL_ROOT  if is_root
                        else COL_DUP  if is_dup
                        else COL_LEAF if is_leaf
                        else COL_INNER)

                c.create_rectangle(x, y, x + NW, y + NH,
                                   fill=fill, outline="#555", width=1)

                # хеш
                c.create_text(cx, y + 15,
                               text=h[:22] + "…", font=("Courier", 8))

                # подпись
                if is_root:
                    lbl = "Корень"
                elif is_dup:
                    lbl = f"дубль [{i - 1}]"
                elif is_leaf:
                    tx  = block.transactions[i]
                    lbl = f"TX-{tx.transaction_id}  {tx.sender[:12]}→{tx.receiver[:12]}"
                else:
                    lbl = f"узел [{i}]"

                c.create_text(cx, y + 33, text=lbl,
                               font=("TkDefaultFont", 8), fill="#333")

        # ── Легенда ────────────────────────────────────────────────────
        ly = canvas_h - 18
        lx = PAD
        for fill, label in (
            (COL_ROOT,  "Корень"),
            (COL_INNER, "Внутренний узел"),
            (COL_LEAF,  "Транзакция (лист)"),
            (COL_DUP,   "Дубль листа"),
        ):
            c.create_rectangle(lx, ly, lx + 12, ly + 12,
                                fill=fill, outline="#555")
            c.create_text(lx + 16, ly + 6, text=label,
                           anchor="w", font=("TkDefaultFont", 8))
            lx += 140

        return canvas_w, canvas_h

    # Логика — атака и проверка

    def _make_copy(self):
        if self.atk.copy_ready:
            self._atk_log("[Предыдущая копия удалена — создаётся новая]")
        self.atk.make_copy()
        info = self.atk.copy_info()
        self.copy_info_var.set(info)
        self.val_copy.set("")
        self._atk_log(f"[Копия создана]  {info}")
        self.status_var.set("Копия цепочки создана")

    def _attack(self):
        try:
            block_idx  = int(self.atk_block.get())
            tx_idx     = int(self.atk_tx.get())
            new_amount = float(self.atk_amount.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Блок и TX — целые числа, сумма — число.")
            return

        ok, msg = self.atk.tamper(block_idx, tx_idx, new_amount)
        if ok:
            self._atk_log(msg)
            self.status_var.set("Атака на копию применена — нажмите «Проверить копию»")
        else:
            messagebox.showerror("Ошибка атаки", msg)

    def _attack_replace_sender(self):
        try:
            block_idx  = int(self.atk_rs_block.get())
            tx_idx     = int(self.atk_rs_tx.get())
            new_sender = self.atk_rs_sender.get().strip()
        except ValueError:
            messagebox.showerror("Ошибка", "Блок и TX — целые числа.")
            return
        if not new_sender:
            messagebox.showerror("Ошибка", "Новый отправитель не может быть пустым.")
            return
        ok, msg = self.atk.replace_sender(block_idx, tx_idx, new_sender)
        if ok:
            self._atk_log(msg)
            self.status_var.set("Подмена отправителя применена — нажмите «Проверить копию»")
        else:
            messagebox.showerror("Ошибка атаки", msg)

    def _attack_drop_tx(self):
        try:
            block_idx = int(self.atk_drop_block.get())
            tx_idx    = int(self.atk_drop_tx.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Блок и TX — целые числа.")
            return
        ok, msg = self.atk.drop_transaction(block_idx, tx_idx)
        if ok:
            self._atk_log(msg)
            self.status_var.set("Транзакция удалена из копии — нажмите «Проверить копию»")
        else:
            messagebox.showerror("Ошибка атаки", msg)

    def _attack_replay(self):
        try:
            src_block = int(self.atk_rp_src_block.get())
            src_tx    = int(self.atk_rp_src_tx.get())
            dst_block = int(self.atk_rp_dst_block.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Все три поля — целые числа.")
            return
        ok, msg = self.atk.replay_transaction(src_block, src_tx, dst_block)
        if ok:
            self._atk_log(msg)
            self.status_var.set("Replay-атака применена — нажмите «Проверить копию»")
        else:
            messagebox.showerror("Ошибка атаки", msg)

    def _attack_51(self):
        try:
            block_idx = int(self.atk_51_block.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Начальный блок — целое число.")
            return
        ok, msg = self.atk.recompute_from(block_idx)
        if ok:
            self._atk_log(msg)
            self.status_var.set(
                "Атака 51% применена — цепочка пересчитана. "
                "validate_copy() теперь не найдёт разрыва!"
            )
        else:
            messagebox.showerror("Ошибка атаки", msg)

    def _validate_original(self):
        valid, msg = self.bc.validate_chain()
        self.val_orig.set(("✔  Оригинал: " if valid else "✘  Оригинал: ") + msg)
        self.lbl_val_orig.configure(foreground="darkgreen" if valid else "red")
        self.status_var.set(msg)

    def _validate_copy(self):
        valid, msg = self.atk.validate_copy()
        if valid is None:
            self.val_copy.set("  Копия: не создана")
            return
        first_line = msg.splitlines()[0]
        prefix = "✔  Копия: " if valid else "✘  Копия: "
        self.val_copy.set(prefix + first_line)
        self._atk_log(f"[Проверка копии]\n{msg}")
        self.status_var.set("Копия: " + first_line)

    def _atk_log(self, msg: str):
        self.atk_log.config(state="normal")
        self.atk_log.insert(tk.END, msg + "\n" + "-" * 60 + "\n")
        self.atk_log.see(tk.END)
        self.atk_log.config(state="disabled")

    # Таймер блока

    def _start_timer(self):
        if self._timer_running:
            return
        self._timer_running   = True
        self._timer_remaining = BLOCK_TIMEOUT_SECONDS
        self._tick()

    def _tick(self):
        if not self._timer_running:
            return
        if not self.bc.pending_transactions:
            self._cancel_timer()
            return
        if self._timer_remaining <= 0:
            self._seal_by_timer()
            return
        self.timer_var.set(f"Таймер блока: {self._timer_remaining} сек")
        self._timer_remaining -= 1
        self._timer_job = self.root.after(1000, self._tick)

    def _seal_by_timer(self):
        self._timer_running = False
        self.timer_var.set("")
        if not self.bc.pending_transactions:
            return
        self.bc.seal_block()
        n = len(self.bc.chain) - 1
        self.pool_var.set(f"Пул: {len(self.bc.pending_transactions)} / {TRANSACTIONS_PER_BLOCK}")
        self._log(f">>> БЛОК #{n} закрыт по таймеру (60 сек)  |  хеш: {self.bc.chain[-1].hash[:24]}...")
        self.refresh_blocks()
        self.status_var.set(f"Блок #{n} закрыт по таймеру (60 сек)")

    def _cancel_timer(self):
        self._timer_running = False
        self.timer_var.set("")
        if self._timer_job:
            self.root.after_cancel(self._timer_job)
            self._timer_job = None

    # Авто-генератор

    def _start_auto(self):
        if self._auto_running:
            return
        self._auto_running  = True
        self._auto_scenario = 0
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self._auto_thread = threading.Thread(target=self._auto_loop, daemon=True)
        self._auto_thread.start()

    def _stop_auto(self):
        self._auto_running = False
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.auto_status.set("")
        self.scenario_var.set("")

    def _auto_loop(self):
        configs = [
            (5, 9,  "Сценарий 1: по количеству (5 TX × 9 сек)"),
            (3, 22, "Сценарий 2: по таймеру   (3 TX × 22 сек)"),
        ]
        while self._auto_running:
            count, interval, name = configs[self._auto_scenario]
            self.root.after(0, self.auto_status.set, name)
            self.root.after(0, self.scenario_var.set, name)

            for _ in range(count):
                if not self._auto_running:
                    return
                self.root.after(0, self._gen_random_tx)
                self._sleep(interval)

            if self._auto_scenario == 1:
                self._sleep(10)

            self._auto_scenario = (self._auto_scenario + 1) % len(configs)

    def _sleep(self, seconds: float):
        deadline = time.time() + seconds
        while time.time() < deadline and self._auto_running:
            time.sleep(0.25)

    def _gen_random_tx(self):
        if not self._auto_running:
            return
        tag = "по кол-ву" if self._auto_scenario == 0 else "по таймеру"
        for key, val in {
            "reference": random.choice(_REFS),
            "sender":    random.choice(_SENDERS),
            "receiver":  random.choice(_RECEIVERS),
            "passport":  random.choice(_PASSPORTS),
            "amount":    str(random.randint(10, 500) * 1000),
            "commission": str(random.choice([0.1, 0.2, 0.3, 0.5, 1.0])),
        }.items():
            self.entries[key].delete(0, tk.END)
            self.entries[key].insert(0, val)
        self._add_tx(scenario_tag=f"авто/{tag}")

    def _on_close(self):
        self._auto_running = False
        self._cancel_timer()
        self.root.destroy()
    