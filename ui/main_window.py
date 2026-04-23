import logging
import random

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QCursor, QFont, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.block import Block
from models.blockchain import BLOCK_TIMEOUT_SECONDS, TRANSACTIONS_PER_BLOCK, Blockchain
from models.transaction import Transaction
from services.attack_simulator import AttackSimulator
from ui.styles import DARK_QSS

logger = logging.getLogger(__name__)

_REFS = ["ПЕР-{:04d}".format(n) for n in range(1001, 1100)]
_SENDERS = ["КЛИЕНТ-{:04d}".format(n) for n in range(101, 200)]
_RECEIVERS = ["КЛИЕНТ-{:04d}".format(n) for n in range(201, 300)]
_PASSPORTS = [str(random.randint(100_000_000, 999_999_999)) for _ in range(60)]


class ClickableBlockItem(QGraphicsRectItem):
    def __init__(self, rect: QRectF, block_index: int, callback):
        super().__init__(rect)
        self.block_index = block_index
        self.callback = callback
        self.setAcceptHoverEvents(True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def mousePressEvent(self, event):
        self.callback(self.block_index)
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    _VIS_BW = 260
    _VIS_BH = 118
    _VIS_GAP = 62
    _VIS_Y = 26
    _VIS_X0 = 24

    _MK_NODE_W = 270
    _MK_NODE_H = 54
    _MK_H_GAP = 18
    _MK_V_GAP = 66
    _MK_PAD = 28

    def __init__(self, bc: Blockchain):
        super().__init__()
        self.bc = bc
        self.atk = AttackSimulator(bc)

        self._timer_running = False
        self._timer_remaining = 0
        self._auto_running = False
        self._auto_scenario = 0
        self._auto_generated = 0
        self._auto_target = 0
        self._auto_interval_ms = 0
        self._auto_waiting_next = False
        self._vis_selected = None

        self.block_timer = QTimer(self)
        self.block_timer.setInterval(1000)
        self.block_timer.timeout.connect(self._tick_block_timer)

        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self._on_auto_timer)

        self.setWindowTitle("Мгновенные переводы - Hash-цепочка")
        self.resize(1280, 780)
        self.setMinimumSize(1040, 680)
        self.setStyleSheet(DARK_QSS)

        self._build_shell()
        self._update_dashboard()
        self.refresh_blocks()
        self.statusBar().showMessage("Готово")

    def _build_shell(self):
        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(224)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(18, 20, 18, 18)
        side_layout.setSpacing(12)

        brand = QLabel("CHEAIN")
        brand.setObjectName("brand")
        subtitle = QLabel("Hash-chain lab")
        subtitle.setObjectName("sidebarSubtitle")
        side_layout.addWidget(brand)
        side_layout.addWidget(subtitle)
        side_layout.addSpacing(18)

        self.nav_buttons = []
        self.nav_buttons.append(self._nav_button("Переводы", 0))
        self.nav_buttons.append(self._nav_button("Цепочка", 1))
        self.nav_buttons.append(self._nav_button("Атаки", 2))
        for button in self.nav_buttons:
            side_layout.addWidget(button)
        side_layout.addStretch()

        self.side_hint = QLabel("Локальная демонстрация блоков, хешей, Merkle root и атак на копию цепочки.")
        self.side_hint.setObjectName("sideHint")
        self.side_hint.setWordWrap(True)
        side_layout.addWidget(self.side_hint)

        content = QWidget()
        content.setObjectName("content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 18)
        content_layout.setSpacing(16)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("Мгновенные переводы")
        title.setObjectName("pageTitle")
        caption = QLabel("Темная панель управления цепочкой блоков и симуляцией атак")
        caption.setObjectName("pageCaption")
        title_box.addWidget(title)
        title_box.addWidget(caption)
        header.addLayout(title_box)
        header.addStretch()
        content_layout.addLayout(header)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.pool_card = self._stat_card("Пул", f"0 / {TRANSACTIONS_PER_BLOCK}")
        self.blocks_card = self._stat_card("Блоков", str(len(self.bc.chain)))
        self.timer_card = self._stat_card("Таймер", "ожидание")
        self.copy_card = self._stat_card("Копия", "нет")
        for card, _title, _value in (
            self.pool_card,
            self.blocks_card,
            self.timer_card,
            self.copy_card,
        ):
            cards.addWidget(card)
        content_layout.addLayout(cards)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_transfer_page())
        self.pages.addWidget(self._build_chain_page())
        self.pages.addWidget(self._build_attack_page())
        content_layout.addWidget(self.pages, 1)

        root_layout.addWidget(sidebar)
        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)
        self._switch_page(0)

    def _nav_button(self, text: str, page_index: int) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("navButton")
        button.setCheckable(True)
        button.clicked.connect(lambda _checked=False, idx=page_index: self._switch_page(idx))
        return button

    def _switch_page(self, index: int):
        self.pages.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)

    def _stat_card(self, title: str, value: str):
        frame = QFrame()
        frame.setObjectName("statCard")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setProperty("role", "statTitle")
        value_label = QLabel(value)
        value_label.setProperty("role", "statValue")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return frame, title_label, value_label

    def _panel(self, title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        if title:
            label = QLabel(title)
            label.setObjectName("panelTitle")
            layout.addWidget(label)
        return frame, layout

    def _button(self, text: str, variant: str = "neutral") -> QPushButton:
        button = QPushButton(text)
        button.setProperty("variant", variant)
        button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        return button

    def _build_transfer_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(14)

        form_panel, form_layout = self._panel("Новый перевод")
        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self.entries = {
            "reference": QLineEdit(),
            "sender": QLineEdit(),
            "receiver": QLineEdit(),
            "passport": QLineEdit(),
        }
        self.amount_input = QDoubleSpinBox()
        self.amount_input.setRange(0, 1_000_000_000)
        self.amount_input.setDecimals(2)
        self.amount_input.setSingleStep(1000)
        self.amount_input.setGroupSeparatorShown(True)
        self.commission_input = QDoubleSpinBox()
        self.commission_input.setRange(0, 99.99)
        self.commission_input.setDecimals(2)
        self.commission_input.setSingleStep(0.1)
        self.commission_input.setSuffix(" %")

        fields = [
            ("Номер перевода", self.entries["reference"]),
            ("Отправитель", self.entries["sender"]),
            ("Получатель", self.entries["receiver"]),
            ("Паспорт", self.entries["passport"]),
            ("Сумма", self.amount_input),
            ("Комиссия", self.commission_input),
        ]
        for row, (label_text, widget) in enumerate(fields):
            label = QLabel(label_text)
            label.setProperty("role", "fieldLabel")
            form.addWidget(label, row, 0)
            form.addWidget(widget, row, 1)
        form.setColumnStretch(1, 1)
        form_layout.addLayout(form)

        actions = QHBoxLayout()
        add_btn = self._button("Добавить перевод", "primary")
        add_btn.clicked.connect(self._add_tx)
        seal_btn = self._button("Запечатать блок", "neutral")
        seal_btn.clicked.connect(self._force_seal)
        demo_btn = self._button("Демо-данные", "ghost")
        demo_btn.clicked.connect(self._fill_demo)
        actions.addWidget(add_btn)
        actions.addWidget(seal_btn)
        actions.addWidget(demo_btn)
        actions.addStretch()
        form_layout.addLayout(actions)

        auto_panel, auto_layout = self._panel("Авто-генератор")
        auto_row = QHBoxLayout()
        self.btn_start = self._button("Запустить", "primary")
        self.btn_start.clicked.connect(self._start_auto)
        self.btn_stop = self._button("Остановить", "danger")
        self.btn_stop.clicked.connect(self._stop_auto)
        self.btn_stop.setEnabled(False)
        self.auto_status = QLabel("")
        self.auto_status.setObjectName("mutedLabel")
        self.auto_status.setWordWrap(True)
        auto_row.addWidget(self.btn_start)
        auto_row.addWidget(self.btn_stop)
        auto_row.addWidget(self.auto_status, 1)
        auto_layout.addLayout(auto_row)
        scenario_hint = QLabel(
            "Сценарий 1: 5 переводов x 9 сек -> блок по количеству. "
            "Сценарий 2: 3 перевода x 22 сек -> блок по таймеру."
        )
        scenario_hint.setObjectName("mutedLabel")
        scenario_hint.setWordWrap(True)
        auto_layout.addWidget(scenario_hint)

        left_layout.addWidget(form_panel)
        left_layout.addWidget(auto_panel)
        left_layout.addStretch()

        log_panel, log_layout = self._panel("Журнал переводов")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1200)
        log_layout.addWidget(self.log)

        splitter.addWidget(left)
        splitter.addWidget(log_panel)
        splitter.setSizes([470, 650])
        layout.addWidget(splitter)
        return page

    def _build_chain_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        vis_panel, vis_layout = self._panel("Визуальная цепочка")
        self.vis_scene = QGraphicsScene(self)
        self.vis_view = QGraphicsView(self.vis_scene)
        self.vis_view.setObjectName("graphicsView")
        self.vis_view.setMinimumHeight(188)
        self.vis_view.setRenderHints(self.vis_view.renderHints())
        vis_layout.addWidget(self.vis_view)
        layout.addWidget(vis_panel)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        table_panel, table_layout = self._panel("Блоки")
        self.blocks_table = QTableWidget(0, 5)
        self.blocks_table.setHorizontalHeaderLabels(["Блок", "Хеш", "Пред. хеш", "TX", "Время"])
        self.blocks_table.verticalHeader().setVisible(False)
        self.blocks_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.blocks_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.blocks_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.blocks_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.blocks_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.blocks_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.blocks_table.itemSelectionChanged.connect(self._show_block_details)
        table_layout.addWidget(self.blocks_table)

        table_actions = QHBoxLayout()
        refresh_btn = self._button("Обновить", "neutral")
        refresh_btn.clicked.connect(self.refresh_blocks)
        merkle_btn = self._button("Дерево Меркла", "primary")
        merkle_btn.clicked.connect(self._open_merkle_window)
        table_actions.addWidget(refresh_btn)
        table_actions.addWidget(merkle_btn)
        table_actions.addStretch()
        table_layout.addLayout(table_actions)

        details_panel, details_layout = self._panel("Детали выбранного блока")
        self.detail_text = QPlainTextEdit()
        self.detail_text.setReadOnly(True)
        details_layout.addWidget(self.detail_text)

        splitter.addWidget(table_panel)
        splitter.addWidget(details_panel)
        splitter.setSizes([570, 530])
        layout.addWidget(splitter, 1)
        return page

    def _build_attack_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        copy_panel, copy_layout = self._panel("Копия цепочки")
        copy_row = QHBoxLayout()
        make_copy_btn = self._button("Создать копию", "primary")
        make_copy_btn.clicked.connect(self._make_copy)
        self.copy_info_label = QLabel("Копия не создана")
        self.copy_info_label.setObjectName("mutedLabel")
        copy_row.addWidget(make_copy_btn)
        copy_row.addWidget(self.copy_info_label, 1)
        copy_layout.addLayout(copy_row)
        copy_note = QLabel("Все атаки применяются только к копии. Оригинальная цепочка остается неизменной.")
        copy_note.setObjectName("mutedLabel")
        copy_note.setWordWrap(True)
        copy_layout.addWidget(copy_note)
        layout.addWidget(copy_panel)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        attack_panel, attack_layout = self._panel("Тип атаки")
        self.attack_tabs = QTabWidget()
        self.attack_tabs.addTab(self._attack_tamper_tab(), "Подделать сумму")
        self.attack_tabs.addTab(self._attack_sender_tab(), "Подмена отправителя")
        self.attack_tabs.addTab(self._attack_drop_tab(), "Удалить TX")
        self.attack_tabs.addTab(self._attack_replay_tab(), "Повтор")
        self.attack_tabs.addTab(self._attack_51_tab(), "Атака 51%")
        attack_layout.addWidget(self.attack_tabs)

        validation_panel, validation_layout = self._panel("Проверка и журнал")
        validation_buttons = QHBoxLayout()
        val_orig_btn = self._button("Проверить оригинал", "neutral")
        val_orig_btn.clicked.connect(self._validate_original)
        val_copy_btn = self._button("Проверить копию", "primary")
        val_copy_btn.clicked.connect(self._validate_copy)
        validation_buttons.addWidget(val_orig_btn)
        validation_buttons.addWidget(val_copy_btn)
        validation_buttons.addStretch()
        validation_layout.addLayout(validation_buttons)

        self.val_orig_label = QLabel("")
        self.val_copy_label = QLabel("")
        for label in (self.val_orig_label, self.val_copy_label):
            label.setObjectName("resultLabel")
            label.setWordWrap(True)
            validation_layout.addWidget(label)

        self.atk_log = QPlainTextEdit()
        self.atk_log.setReadOnly(True)
        self.atk_log.setMaximumBlockCount(1500)
        validation_layout.addWidget(self.atk_log, 1)

        splitter.addWidget(attack_panel)
        splitter.addWidget(validation_panel)
        splitter.setSizes([560, 560])
        layout.addWidget(splitter, 1)
        return page

    def _spin(self, value: int = 0, minimum: int = 0, maximum: int = 9999) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        return spin

    def _attack_tamper_tab(self) -> QWidget:
        tab = QWidget()
        layout = self._attack_form_layout(tab)
        self.atk_block = self._spin(1)
        self.atk_tx = self._spin(0)
        self.atk_amount = QDoubleSpinBox()
        self.atk_amount.setRange(0, 1_000_000_000)
        self.atk_amount.setDecimals(2)
        self.atk_amount.setValue(999999)
        self.atk_amount.setGroupSeparatorShown(True)
        self._add_attack_row(layout, 0, "Блок N", self.atk_block)
        self._add_attack_row(layout, 1, "TX N", self.atk_tx)
        self._add_attack_row(layout, 2, "Новая сумма", self.atk_amount)
        self._add_attack_apply(layout, 3, self._attack)
        self._add_attack_hint(layout, 4, "Изменяет сумму транзакции и пересчитывает хеш блока. Следующий блок продолжает хранить старый previous_hash.")
        return tab

    def _attack_sender_tab(self) -> QWidget:
        tab = QWidget()
        layout = self._attack_form_layout(tab)
        self.atk_rs_block = self._spin(1)
        self.atk_rs_tx = self._spin(0)
        self.atk_rs_sender = QLineEdit("ЗЛОУМЫШЛЕННИК")
        self._add_attack_row(layout, 0, "Блок N", self.atk_rs_block)
        self._add_attack_row(layout, 1, "TX N", self.atk_rs_tx)
        self._add_attack_row(layout, 2, "Новый отправитель", self.atk_rs_sender)
        self._add_attack_apply(layout, 3, self._attack_replace_sender)
        self._add_attack_hint(layout, 4, "Подменяет отправителя. Подпись остается старой, поэтому проверка может обнаружить несоответствие.")
        return tab

    def _attack_drop_tab(self) -> QWidget:
        tab = QWidget()
        layout = self._attack_form_layout(tab)
        self.atk_drop_block = self._spin(1)
        self.atk_drop_tx = self._spin(0)
        self._add_attack_row(layout, 0, "Блок N", self.atk_drop_block)
        self._add_attack_row(layout, 1, "TX N", self.atk_drop_tx)
        self._add_attack_apply(layout, 2, self._attack_drop_tx)
        self._add_attack_hint(layout, 3, "Удаляет транзакцию из блока, затем пересчитывает Merkle root и хеш блока.")
        return tab

    def _attack_replay_tab(self) -> QWidget:
        tab = QWidget()
        layout = self._attack_form_layout(tab)
        self.atk_rp_src_block = self._spin(1)
        self.atk_rp_src_tx = self._spin(0)
        self.atk_rp_dst_block = self._spin(2)
        self._add_attack_row(layout, 0, "Блок-источник N", self.atk_rp_src_block)
        self._add_attack_row(layout, 1, "TX N", self.atk_rp_src_tx)
        self._add_attack_row(layout, 2, "Блок-цель N", self.atk_rp_dst_block)
        self._add_attack_apply(layout, 3, self._attack_replay)
        self._add_attack_hint(layout, 4, "Копирует транзакцию в другой блок, демонстрируя повторное воспроизведение.")
        return tab

    def _attack_51_tab(self) -> QWidget:
        tab = QWidget()
        layout = self._attack_form_layout(tab)
        self.atk_51_block = self._spin(1)
        self._add_attack_row(layout, 0, "Начальный блок N", self.atk_51_block)
        self._add_attack_apply(layout, 1, self._attack_51)
        self._add_attack_hint(layout, 2, "Пересчитывает previous_hash и хеши хвоста копии, имитируя переписывание цепочки.")
        return tab

    def _attack_form_layout(self, tab: QWidget) -> QGridLayout:
        layout = QGridLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(12)
        layout.setColumnStretch(1, 1)
        return layout

    def _add_attack_row(self, layout: QGridLayout, row: int, label_text: str, widget: QWidget):
        label = QLabel(label_text)
        label.setProperty("role", "fieldLabel")
        layout.addWidget(label, row, 0)
        layout.addWidget(widget, row, 1)

    def _add_attack_apply(self, layout: QGridLayout, row: int, callback):
        button = self._button("Применить", "danger")
        button.clicked.connect(callback)
        layout.addWidget(button, row, 1, alignment=Qt.AlignmentFlag.AlignLeft)

    def _add_attack_hint(self, layout: QGridLayout, row: int, text: str):
        hint = QLabel(text)
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint, row, 0, 1, 2)

    def _add_tx(self, scenario_tag: str = "") -> bool:
        try:
            tx = Transaction(
                reference=self.entries["reference"].text().strip(),
                sender=self.entries["sender"].text().strip(),
                receiver=self.entries["receiver"].text().strip(),
                passport_raw=self.entries["passport"].text().strip(),
                amount=float(self.amount_input.value()),
                commission=float(self.commission_input.value()),
            )
            pool_was_empty = len(self.bc.pending_transactions) == 0
            block_created = self.bc.add_transaction(tx)
        except ValueError as exc:
            QMessageBox.critical(self, "Ошибка ввода", str(exc))
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
            self.statusBar().showMessage(f"Блок #{n} закрыт по количеству переводов")
            self.refresh_blocks()
        elif pool_was_empty:
            self._start_timer()

        self._clear_transfer_form()
        self._update_dashboard()
        return True

    def _clear_transfer_form(self):
        for entry in self.entries.values():
            entry.clear()
        self.amount_input.setValue(0)
        self.commission_input.setValue(0)

    def _force_seal(self):
        if not self.bc.pending_transactions:
            QMessageBox.information(self, "Пул пуст", "Нет переводов для закрытия блока.")
            return
        self._cancel_timer()
        self.bc.seal_block()
        n = len(self.bc.chain) - 1
        self._log(f">>> БЛОК #{n} закрыт принудительно  |  хеш: {self.bc.chain[-1].hash[:24]}...")
        self.refresh_blocks()
        self._update_dashboard()
        self.statusBar().showMessage(f"Блок #{n} закрыт принудительно")

    def _fill_demo(self):
        values = {
            "reference": "ПЕР-1042",
            "sender": "КЛИЕНТ-0101",
            "receiver": "КЛИЕНТ-0202",
            "passport": "123456789",
        }
        for key, value in values.items():
            self.entries[key].setText(value)
        self.amount_input.setValue(50000)
        self.commission_input.setValue(0.5)

    def _log(self, msg: str):
        self.log.appendPlainText(msg + "\n" + "-" * 64)

    def refresh_blocks(self):
        self.blocks_table.setRowCount(len(self.bc.chain))
        for row, block in enumerate(self.bc.chain):
            values = [
                f"#{block.index}" + (" (нач.)" if block.index == 0 else ""),
                block.hash[:24] + "...",
                block.previous_hash[:24] + "...",
                str(len(block.transactions)),
                block.timestamp,
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col in (0, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.blocks_table.setItem(row, col, item)
        self.refresh_visualization()
        self._update_dashboard()

    def refresh_visualization(self):
        self.vis_scene.clear()
        chain = self.bc.chain
        total_w = self._VIS_X0 + len(chain) * (self._VIS_BW + self._VIS_GAP) + 40
        total_h = self._VIS_Y + self._VIS_BH + 48
        self.vis_scene.setSceneRect(0, 0, max(total_w, 900), total_h)

        for index, block in enumerate(chain):
            x = self._VIS_X0 + index * (self._VIS_BW + self._VIS_GAP)
            y = self._VIS_Y
            selected = index == self._vis_selected

            if selected:
                bg = QColor("#1ecad3")
                border = QColor("#d8fbff")
            elif index == 0:
                bg = QColor("#7c2d45")
                border = QColor("#ff7aa2")
            else:
                bg = QColor("#293346")
                border = QColor("#71f2b4")

            rect = ClickableBlockItem(QRectF(x, y, self._VIS_BW, self._VIS_BH), index, self._on_vis_click)
            rect.setBrush(QBrush(bg))
            rect.setPen(QPen(border, 2.5 if selected else 1.4))
            self.vis_scene.addItem(rect)

            title = f"Блок #{block.index}" + ("  genesis" if index == 0 else "")
            self._scene_text(title, x + 14, y + 10, 10, "#f8fafc", bold=True)
            self._scene_text(f"Hash    {block.hash[:18]}...", x + 14, y + 38, 8, "#d8dee9", mono=True)
            self._scene_text(f"Merkle  {block.merkle_root[:18]}...", x + 14, y + 60, 8, "#d8dee9", mono=True)
            self._scene_text(f"TX {len(block.transactions)}   {block.timestamp[11:19] if block.timestamp else ''}", x + 14, y + 84, 8, "#aeb7c5", mono=True)

            if index < len(chain) - 1:
                ax = x + self._VIS_BW
                ay = y + self._VIS_BH / 2
                pen = QPen(QColor("#5f6b7a"), 2)
                self.vis_scene.addLine(ax, ay, ax + self._VIS_GAP, ay, pen)
                self.vis_scene.addLine(ax + self._VIS_GAP - 10, ay - 6, ax + self._VIS_GAP, ay, pen)
                self.vis_scene.addLine(ax + self._VIS_GAP - 10, ay + 6, ax + self._VIS_GAP, ay, pen)
                self._scene_text("prev", ax + 16, ay - 22, 7, "#8a94a6")

    def _scene_text(self, text: str, x: float, y: float, size: int, color: str, bold: bool = False, mono: bool = False) -> QGraphicsTextItem:
        font = QFont("Consolas" if mono else "Segoe UI", size)
        font.setBold(bold)
        item = self.vis_scene.addText(text, font)
        item.setDefaultTextColor(QColor(color))
        item.setPos(x, y)
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        return item

    def _on_vis_click(self, block_idx: int):
        self._vis_selected = block_idx
        self.refresh_visualization()
        if 0 <= block_idx < self.blocks_table.rowCount():
            self.blocks_table.selectRow(block_idx)
            self._show_block_details()

    def _show_block_details(self):
        row = self.blocks_table.currentRow()
        if row < 0 or row >= len(self.bc.chain):
            return
        self._vis_selected = row
        block = self.bc.chain[row]
        lines = [
            f"Блок #{block.index}",
            f"  Хеш:           {block.hash}",
            f"  Пред. хеш:     {block.previous_hash}",
            f"  Корень Меркла: {block.merkle_root}",
            f"  Время:         {block.timestamp}",
        ]

        if block.transactions:
            lines.append("")
            lines.append(f"Переводы ({len(block.transactions)}):")
            for tx in block.transactions:
                lines.extend(
                    [
                        "",
                        f"  TX {tx.transaction_id}  |  Перевод: {tx.reference}",
                        f"  {tx.sender} -> {tx.receiver}",
                        f"  Сумма: {tx.amount:,.2f}  |  К получению: {tx.net_amount:,.2f}  (комиссия {tx.commission}%)",
                        f"  Хеш паспорта: {tx.passport_hash}",
                        f"  Подпись:      {tx.signature}",
                        f"  Хеш TX:       {tx.tx_hash}",
                        f"  Время:        {tx.timestamp}",
                    ]
                )
            lines.extend(["", "-" * 64, "Дерево Меркла:", ""])
            lines.extend(self._merkle_text(block))
        else:
            lines.extend(["", "  (блок не содержит переводов)"])

        self.detail_text.setPlainText("\n".join(lines))
        self.refresh_visualization()

    def _merkle_text(self, block) -> list[str]:
        tx_hashes = [tx.tx_hash for tx in block.transactions]
        n_real = len(tx_hashes)
        levels = Block.build_merkle_tree(tx_hashes)
        lines: list[str] = []
        for lvl_idx in range(len(levels) - 1, -1, -1):
            level = levels[lvl_idx]
            if lvl_idx == len(levels) - 1:
                header = "Корень:"
            elif lvl_idx == 0:
                header = f"Листья (хеши {n_real} транзакций):"
            else:
                header = f"Уровень {lvl_idx}:"
            lines.append(f"  {header}")
            for i, value in enumerate(level):
                if lvl_idx == 0 and i < n_real:
                    tx = block.transactions[i]
                    lines.append(f"    [{i}] {value[:24]}...  TX-{tx.transaction_id}  {tx.sender} -> {tx.receiver}")
                elif lvl_idx == 0:
                    lines.append(f"    [{i}] {value[:24]}...  (дубль [{i - 1}])")
                else:
                    lines.append(f"    [{i}] {value[:24]}...")
            lines.append("")
        return lines

    def _open_merkle_window(self):
        row = self.blocks_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Нет выбора", "Выберите блок в таблице.")
            return
        block = self.bc.chain[row]
        if not block.transactions:
            QMessageBox.information(self, "Нет транзакций", f"Блок #{block.index} не содержит транзакций.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Дерево Меркла - Блок #{block.index}")
        dialog.resize(1100, 680)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        header = QLabel(f"Блок #{block.index}  |  {len(block.transactions)} транзакций  |  Корень: {block.merkle_root[:40]}...")
        header.setObjectName("dialogHeader")
        layout.addWidget(header)

        scene = QGraphicsScene(dialog)
        view = QGraphicsView(scene)
        view.setObjectName("graphicsView")
        layout.addWidget(view, 1)
        self._draw_merkle_scene(scene, block)
        dialog.exec()

    def _draw_merkle_scene(self, scene: QGraphicsScene, block):
        tx_hashes = [tx.tx_hash for tx in block.transactions]
        n_real_tx = len(tx_hashes)
        levels = Block.build_merkle_tree(tx_hashes)
        n_levels = len(levels)
        n_leaves = len(levels[0])
        slot = self._MK_NODE_W + self._MK_H_GAP
        cx_map = {}

        for i in range(n_leaves):
            cx_map[(0, i)] = self._MK_PAD + i * slot + self._MK_NODE_W // 2

        for lvl in range(1, n_levels):
            n_children = len(levels[lvl - 1])
            n_real_here = (n_children + 1) // 2
            n_total_here = len(levels[lvl])
            for i in range(n_real_here):
                li = 2 * i
                ri = min(2 * i + 1, n_children - 1)
                cx_map[(lvl, i)] = (cx_map[(lvl - 1, li)] + cx_map[(lvl - 1, ri)]) // 2
            for i in range(n_real_here, n_total_here):
                cx_map[(lvl, i)] = cx_map[(lvl, i - 1)] + slot

        def node_y(level: int) -> int:
            row = n_levels - 1 - level
            return self._MK_PAD + row * (self._MK_NODE_H + self._MK_V_GAP)

        canvas_w = max(cx_map.values()) + self._MK_NODE_W // 2 + self._MK_PAD
        canvas_h = self._MK_PAD + n_levels * (self._MK_NODE_H + self._MK_V_GAP) + 34
        scene.setSceneRect(0, 0, canvas_w, canvas_h)
        edge_pen = QPen(QColor("#506070"), 1.5)

        for lvl in range(1, n_levels):
            n_children = len(levels[lvl - 1])
            n_real_here = (n_children + 1) // 2
            for i in range(n_real_here):
                px = cx_map[(lvl, i)]
                py = node_y(lvl) + self._MK_NODE_H
                li = 2 * i
                ri = min(2 * i + 1, n_children - 1)
                for child_index in (li, ri):
                    chx = cx_map[(lvl - 1, child_index)]
                    chy = node_y(lvl - 1)
                    scene.addLine(px, py, chx, chy, edge_pen)

        colors = {
            "root": QColor("#d97706"),
            "inner": QColor("#7c3aed"),
            "leaf": QColor("#0891b2"),
            "dup": QColor("#84cc16"),
        }
        for lvl in range(n_levels):
            n_children = len(levels[lvl - 1]) if lvl > 0 else 0
            n_real_here = (n_children + 1) // 2 if lvl > 0 else n_real_tx
            for i, value in enumerate(levels[lvl]):
                cx = cx_map[(lvl, i)]
                y = node_y(lvl)
                x = cx - self._MK_NODE_W // 2
                is_root = lvl == n_levels - 1
                is_leaf = lvl == 0
                is_dup = (not is_root) and (i >= n_real_here)
                fill = colors["root"] if is_root else colors["dup"] if is_dup else colors["leaf"] if is_leaf else colors["inner"]
                rect = scene.addRect(x, y, self._MK_NODE_W, self._MK_NODE_H, QPen(QColor("#d7deea"), 1), QBrush(fill))

                hash_text = scene.addText(value[:24] + "...", QFont("Consolas", 8))
                hash_text.setDefaultTextColor(QColor("#f8fafc"))
                hash_text.setPos(x + 12, y + 8)
                hash_text.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                label = "Корень" if is_root else f"дубль [{i - 1}]" if is_dup else f"TX-{block.transactions[i].transaction_id}" if is_leaf else f"узел [{i}]"
                label_text = scene.addText(label, QFont("Segoe UI", 8))
                label_text.setDefaultTextColor(QColor("#f8fafc"))
                label_text.setPos(x + 12, y + 30)
                label_text.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                rect.setZValue(-1)

    def _make_copy(self):
        if self.atk.copy_ready:
            self._atk_log("[Предыдущая копия удалена - создается новая]")
        self.atk.make_copy()
        info = self.atk.copy_info()
        self.copy_info_label.setText(info)
        self.val_copy_label.setText("")
        self._atk_log(f"[Копия создана]  {info}")
        self._update_dashboard()
        self.statusBar().showMessage("Копия цепочки создана")

    def _attack(self):
        ok, msg = self.atk.tamper(self.atk_block.value(), self.atk_tx.value(), float(self.atk_amount.value()))
        self._handle_attack_result(ok, msg, "Атака на копию применена - нажмите Проверить копию")

    def _attack_replace_sender(self):
        new_sender = self.atk_rs_sender.text().strip()
        if not new_sender:
            QMessageBox.critical(self, "Ошибка", "Новый отправитель не может быть пустым.")
            return
        ok, msg = self.atk.replace_sender(self.atk_rs_block.value(), self.atk_rs_tx.value(), new_sender)
        self._handle_attack_result(ok, msg, "Подмена отправителя применена - нажмите Проверить копию")

    def _attack_drop_tx(self):
        ok, msg = self.atk.drop_transaction(self.atk_drop_block.value(), self.atk_drop_tx.value())
        self._handle_attack_result(ok, msg, "Транзакция удалена из копии - нажмите Проверить копию")

    def _attack_replay(self):
        ok, msg = self.atk.replay_transaction(
            self.atk_rp_src_block.value(),
            self.atk_rp_src_tx.value(),
            self.atk_rp_dst_block.value(),
        )
        self._handle_attack_result(ok, msg, "Replay-атака применена - нажмите Проверить копию")

    def _attack_51(self):
        ok, msg = self.atk.recompute_from(self.atk_51_block.value())
        self._handle_attack_result(ok, msg, "Атака 51% применена - копия пересчитана")

    def _handle_attack_result(self, ok: bool, msg: str, status: str):
        if ok:
            self._atk_log(msg)
            self.statusBar().showMessage(status)
        else:
            QMessageBox.critical(self, "Ошибка атаки", msg)

    def _validate_original(self):
        valid, msg = self.bc.validate_chain()
        prefix = "OK  Оригинал: " if valid else "FAIL  Оригинал: "
        self.val_orig_label.setText(prefix + msg)
        self.val_orig_label.setProperty("state", "ok" if valid else "bad")
        self._refresh_widget_style(self.val_orig_label)
        self.statusBar().showMessage(msg)

    def _validate_copy(self):
        valid, msg = self.atk.validate_copy()
        if valid is None:
            self.val_copy_label.setText("Копия: не создана")
            self.val_copy_label.setProperty("state", "warn")
            self._refresh_widget_style(self.val_copy_label)
            return
        first_line = msg.splitlines()[0]
        prefix = "OK  Копия: " if valid else "FAIL  Копия: "
        self.val_copy_label.setText(prefix + first_line)
        self.val_copy_label.setProperty("state", "ok" if valid else "bad")
        self._refresh_widget_style(self.val_copy_label)
        self._atk_log(f"[Проверка копии]\n{msg}")
        self.statusBar().showMessage("Копия: " + first_line)

    def _atk_log(self, msg: str):
        self.atk_log.appendPlainText(msg + "\n" + "-" * 64)

    def _start_timer(self):
        if self._timer_running:
            return
        self._timer_running = True
        self._timer_remaining = BLOCK_TIMEOUT_SECONDS
        self.block_timer.start()
        self._update_dashboard()

    def _tick_block_timer(self):
        if not self._timer_running:
            return
        if not self.bc.pending_transactions:
            self._cancel_timer()
            return
        self._timer_remaining -= 1
        if self._timer_remaining <= 0:
            self._seal_by_timer()
            return
        self._update_dashboard()

    def _seal_by_timer(self):
        self._timer_running = False
        self.block_timer.stop()
        if not self.bc.pending_transactions:
            self._update_dashboard()
            return
        self.bc.seal_block()
        n = len(self.bc.chain) - 1
        self._log(f">>> БЛОК #{n} закрыт по таймеру ({BLOCK_TIMEOUT_SECONDS} сек)  |  хеш: {self.bc.chain[-1].hash[:24]}...")
        self.refresh_blocks()
        self._update_dashboard()
        self.statusBar().showMessage(f"Блок #{n} закрыт по таймеру ({BLOCK_TIMEOUT_SECONDS} сек)")

    def _cancel_timer(self):
        self._timer_running = False
        self.block_timer.stop()
        self._timer_remaining = 0
        self._update_dashboard()

    def _start_auto(self):
        if self._auto_running:
            return
        self._auto_running = True
        self._auto_scenario = 0
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._begin_auto_scenario()

    def _stop_auto(self):
        self._auto_running = False
        self.auto_timer.stop()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.auto_status.setText("")
        self.statusBar().showMessage("Авто-генератор остановлен")

    def _begin_auto_scenario(self):
        if not self._auto_running:
            return
        configs = [
            (5, 9, "Сценарий 1: по количеству (5 TX x 9 сек)"),
            (3, 22, "Сценарий 2: по таймеру (3 TX x 22 сек)"),
        ]
        count, interval, name = configs[self._auto_scenario]
        self._auto_target = count
        self._auto_interval_ms = interval * 1000
        self._auto_generated = 0
        self._auto_waiting_next = False
        self.auto_status.setText(name)
        self.statusBar().showMessage(name)
        self._auto_generate_once()

    def _on_auto_timer(self):
        if not self._auto_running:
            return
        if self._auto_waiting_next:
            self._auto_waiting_next = False
            self._auto_scenario = (self._auto_scenario + 1) % 2
            self._begin_auto_scenario()
            return
        self._auto_generate_once()

    def _auto_generate_once(self):
        if not self._auto_running:
            return
        tag = "авто/по кол-ву" if self._auto_scenario == 0 else "авто/по таймеру"
        self._gen_random_tx(tag)
        self._auto_generated += 1

        if self._auto_generated >= self._auto_target:
            self._auto_waiting_next = True
            delay = 10_000 if self._auto_scenario == 1 else self._auto_interval_ms
            self.auto_timer.start(delay)
            return
        self.auto_timer.start(self._auto_interval_ms)

    def _gen_random_tx(self, tag: str):
        values = {
            "reference": random.choice(_REFS),
            "sender": random.choice(_SENDERS),
            "receiver": random.choice(_RECEIVERS),
            "passport": random.choice(_PASSPORTS),
        }
        for key, value in values.items():
            self.entries[key].setText(value)
        self.amount_input.setValue(random.randint(10, 500) * 1000)
        self.commission_input.setValue(random.choice([0.1, 0.2, 0.3, 0.5, 1.0]))
        self._add_tx(scenario_tag=tag)

    def _update_dashboard(self):
        self.pool_card[2].setText(f"{len(self.bc.pending_transactions)} / {TRANSACTIONS_PER_BLOCK}")
        self.blocks_card[2].setText(str(len(self.bc.chain)))
        timer_text = f"{self._timer_remaining} сек" if self._timer_running else "ожидание"
        self.timer_card[2].setText(timer_text)
        self.copy_card[2].setText("готова" if self.atk.copy_ready else "нет")

    def _refresh_widget_style(self, widget: QWidget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def closeEvent(self, event):
        self._auto_running = False
        self.auto_timer.stop()
        self.block_timer.stop()
        super().closeEvent(event)
