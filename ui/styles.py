DARK_QSS = """
QWidget#appRoot {
    background: #0b1020;
    color: #e5edf7;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 14px;
}

QFrame#sidebar {
    background: #070b16;
    border-right: 1px solid #1f2a3a;
}

QLabel#brand {
    color: #f8fafc;
    font-size: 25px;
    font-weight: 800;
    letter-spacing: 0;
}

QLabel#sidebarSubtitle,
QLabel#sideHint,
QLabel#mutedLabel,
QLabel#pageCaption {
    color: #94a3b8;
}

QLabel#sideHint {
    font-size: 12px;
    line-height: 1.35;
}

QPushButton#navButton {
    background: transparent;
    color: #aeb7c5;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 12px 14px;
    text-align: left;
    font-weight: 650;
}

QPushButton#navButton:hover {
    background: #111827;
    color: #f8fafc;
    border-color: #233044;
}

QPushButton#navButton:checked {
    background: #102235;
    color: #67e8f9;
    border-color: #155e75;
}

QWidget#content {
    background: #0b1020;
}

QLabel#pageTitle {
    color: #f8fafc;
    font-size: 26px;
    font-weight: 800;
}

QFrame#statCard,
QFrame#panel {
    background: #111827;
    border: 1px solid #243044;
    border-radius: 8px;
}

QLabel[role="statTitle"] {
    color: #94a3b8;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
}

QLabel[role="statValue"] {
    color: #f8fafc;
    font-size: 22px;
    font-weight: 800;
}

QLabel#panelTitle {
    color: #f8fafc;
    font-size: 16px;
    font-weight: 750;
}

QLabel[role="fieldLabel"] {
    color: #cbd5e1;
    font-weight: 650;
}

QLineEdit,
QDoubleSpinBox,
QSpinBox,
QPlainTextEdit,
QTableWidget {
    background: #0d1424;
    color: #e5edf7;
    border: 1px solid #2b3951;
    border-radius: 7px;
    padding: 8px;
    selection-background-color: #0e7490;
    selection-color: #f8fafc;
}

QLineEdit:focus,
QDoubleSpinBox:focus,
QSpinBox:focus,
QPlainTextEdit:focus,
QTableWidget:focus {
    border-color: #22d3ee;
}

QPushButton {
    min-height: 34px;
    border-radius: 7px;
    padding: 8px 14px;
    font-weight: 700;
}

QPushButton[variant="primary"] {
    background: #0891b2;
    color: #f8fafc;
    border: 1px solid #22d3ee;
}

QPushButton[variant="primary"]:hover {
    background: #0e7490;
}

QPushButton[variant="neutral"] {
    background: #1f2937;
    color: #e5edf7;
    border: 1px solid #344256;
}

QPushButton[variant="neutral"]:hover {
    background: #293548;
}

QPushButton[variant="ghost"] {
    background: transparent;
    color: #aeb7c5;
    border: 1px solid #344256;
}

QPushButton[variant="ghost"]:hover {
    color: #f8fafc;
    background: #172033;
}

QPushButton[variant="danger"] {
    background: #991b1b;
    color: #fff7ed;
    border: 1px solid #ef4444;
}

QPushButton[variant="danger"]:hover {
    background: #b91c1c;
}

QPushButton:disabled {
    background: #161d2d;
    color: #64748b;
    border-color: #263244;
}

QHeaderView::section {
    background: #172033;
    color: #cbd5e1;
    border: none;
    border-right: 1px solid #263244;
    padding: 8px;
    font-weight: 750;
}

QTableWidget {
    gridline-color: #263244;
    alternate-background-color: #101827;
}

QTableWidget::item {
    padding: 7px;
}

QTableWidget::item:selected {
    background: #0e7490;
    color: #f8fafc;
}

QTabWidget::pane {
    border: 1px solid #263244;
    border-radius: 8px;
    background: #0d1424;
}

QTabBar::tab {
    background: #111827;
    color: #94a3b8;
    border: 1px solid #263244;
    padding: 9px 12px;
    margin-right: 4px;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
}

QTabBar::tab:selected {
    color: #67e8f9;
    background: #102235;
    border-color: #155e75;
}

QGraphicsView#graphicsView {
    background: #0d1424;
    border: 1px solid #243044;
    border-radius: 8px;
}

QLabel#resultLabel {
    color: #cbd5e1;
    padding: 8px 10px;
    border-radius: 7px;
    background: #0d1424;
}

QLabel#resultLabel[state="ok"] {
    color: #bbf7d0;
    background: #052e1b;
    border: 1px solid #15803d;
}

QLabel#resultLabel[state="bad"] {
    color: #fecaca;
    background: #3b0a0a;
    border: 1px solid #dc2626;
}

QLabel#resultLabel[state="warn"] {
    color: #fde68a;
    background: #392707;
    border: 1px solid #d97706;
}

QLabel#dialogHeader {
    color: #f8fafc;
    font-family: Consolas, monospace;
    font-size: 13px;
    font-weight: 700;
}

QStatusBar {
    background: #070b16;
    color: #94a3b8;
    border-top: 1px solid #1f2a3a;
}

QSplitter::handle {
    background: #0b1020;
}

QScrollBar:vertical,
QScrollBar:horizontal {
    background: #0b1020;
    border: none;
    margin: 0;
}

QScrollBar::handle:vertical,
QScrollBar::handle:horizontal {
    background: #334155;
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}

QScrollBar::handle:vertical:hover,
QScrollBar::handle:horizontal:hover {
    background: #475569;
}
"""
