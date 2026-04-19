from __future__ import annotations

import logging
from dataclasses import fields
from pathlib import Path

from jp_anki_builder.project_config import (
    VALID_KEYS,
    ProjectDefaults,
    load_project_config,
)

logger = logging.getLogger(__name__)

_PYSIDE6_AVAILABLE = False

# ---------------------------------------------------------------------------
# Shared style constants (same dark palette as Phase 3 widgets)
# ---------------------------------------------------------------------------

_DARK_BG = "#1C1C1E"
_FRAME_BG = "rgba(30, 30, 36, 255)"
_CARD_BG = "rgba(40, 40, 48, 255)"
_BORDER_COLOR = "rgba(255,255,255,30)"
_TEXT_PRIMARY = "#FFFFFF"
_TEXT_SECONDARY = "#AAAAAA"
_ACCENT_BLUE = "#2266CC"
_ACCENT_BLUE_HOVER = "#1A4A99"
_ACCENT_GREEN = "#22883A"
_ACCENT_GREEN_HOVER = "#185C28"

_WINDOW_STYLESHEET = f"""
QMainWindow, QWidget#central {{
    background-color: {_DARK_BG};
}}
QTabWidget::pane {{
    border: 1px solid {_BORDER_COLOR};
    background: {_DARK_BG};
}}
QTabBar::tab {{
    background: rgba(255,255,255,10);
    color: {_TEXT_SECONDARY};
    padding: 6px 18px;
    border: none;
}}
QTabBar::tab:selected {{
    background: {_FRAME_BG};
    color: {_TEXT_PRIMARY};
    border-bottom: 2px solid {_ACCENT_BLUE};
}}
QLabel {{ color: {_TEXT_PRIMARY}; background: transparent; }}
QLineEdit {{
    background: rgba(255,255,255,15);
    color: {_TEXT_PRIMARY};
    border: 1px solid {_BORDER_COLOR};
    border-radius: 4px;
    padding: 4px 8px;
}}
QComboBox {{
    background: rgba(255,255,255,15);
    color: {_TEXT_PRIMARY};
    border: 1px solid {_BORDER_COLOR};
    border-radius: 4px;
    padding: 4px 8px;
}}
QComboBox QAbstractItemView {{
    background: #2A2A32;
    color: {_TEXT_PRIMARY};
    selection-background-color: {_ACCENT_BLUE};
}}
QTextEdit {{
    background: rgba(0,0,0,120);
    color: #CCCCCC;
    border: 1px solid {_BORDER_COLOR};
    border-radius: 4px;
    font-family: monospace;
    font-size: 11px;
}}
QProgressBar {{
    background: rgba(255,255,255,15);
    border: 1px solid {_BORDER_COLOR};
    border-radius: 4px;
    text-align: center;
    color: {_TEXT_PRIMARY};
}}
QProgressBar::chunk {{
    background: {_ACCENT_BLUE};
    border-radius: 3px;
}}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: rgba(255,255,255,10); width: 6px; border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: rgba(255,255,255,60); border-radius: 3px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QStatusBar {{ background: {_FRAME_BG}; color: {_TEXT_SECONDARY}; font-size: 11px; }}
"""


def _btn_style(bg: str, hover: str) -> str:
    return (
        f"QPushButton {{ color: {_TEXT_PRIMARY}; background: {bg};"
        f" border: none; border-radius: 5px; padding: 6px 14px; font-size: 12px; }}"
        f"QPushButton:hover {{ background: {hover}; }}"
        f"QPushButton:disabled {{ background: rgba(100,100,100,80); color: #666666; }}"
    )


def _section_frame_style() -> str:
    return (
        f"QFrame {{ background-color: {_FRAME_BG}; border-radius: 8px; }}"
    )


try:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSpinBox,
        QSplitter,
        QStatusBar,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    _PYSIDE6_AVAILABLE = True

    # -----------------------------------------------------------------------
    # Drop Zone widget
    # -----------------------------------------------------------------------

    class _DropZone(QFrame):
        """Drag-and-drop target that accepts files and directories."""

        path_dropped = Signal(str)

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setAcceptDrops(True)
            self.setMinimumHeight(80)
            self.setStyleSheet(
                "QFrame {"
                f"  background: rgba(255,255,255,8);"
                f"  border: 2px dashed {_BORDER_COLOR};"
                f"  border-radius: 8px;"
                "}"
                "QFrame:hover {"
                f"  border-color: {_ACCENT_BLUE};"
                "}"
            )
            layout = QVBoxLayout(self)
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl = QLabel("Drop a directory, CBZ, PDF, EPUB, or MKV here")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {_TEXT_SECONDARY}; font-size: 12px; border: none;")
            layout.addWidget(lbl)
            browse_btn = QPushButton("Browse…")
            browse_btn.setFixedWidth(90)
            browse_btn.setStyleSheet(_btn_style("rgba(255,255,255,20)", "rgba(255,255,255,35)"))
            browse_btn.clicked.connect(self._on_browse)
            layout.addWidget(browse_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        def dragEnterEvent(self, event) -> None:  # noqa: N802
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
            else:
                event.ignore()

        def dropEvent(self, event) -> None:  # noqa: N802
            urls = event.mimeData().urls()
            if urls:
                self.path_dropped.emit(urls[0].toLocalFile())
            event.acceptProposedAction()

        def _on_browse(self) -> None:
            path = QFileDialog.getExistingDirectory(self, "Select source directory")
            if not path:
                # Also allow file selection
                path, _ = QFileDialog.getOpenFileName(
                    self,
                    "Select source file",
                    "",
                    "Supported files (*.cbz *.cbr *.pdf *.epub *.mkv *.mp4);;All files (*)",
                )
            if path:
                self.path_dropped.emit(path)

    # -----------------------------------------------------------------------
    # Individual tab builders
    # -----------------------------------------------------------------------

    def _build_batch_tab(window: "MainWindow") -> QWidget:
        tab = QWidget()
        tab.setObjectName("batchTab")
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        # --- Source section ---
        source_frame = QFrame()
        source_frame.setStyleSheet(_section_frame_style())
        source_inner = QVBoxLayout(source_frame)
        source_inner.setContentsMargins(12, 10, 12, 10)
        source_inner.setSpacing(8)

        drop_zone = _DropZone()
        drop_zone.path_dropped.connect(window._on_path_dropped)
        window._drop_zone = drop_zone
        source_inner.addWidget(drop_zone)

        # Path display label (shown under drop zone when a path is selected)
        window._path_label = QLabel("")
        window._path_label.setStyleSheet(
            f"color: {_TEXT_SECONDARY}; font-size: 11px; font-family: monospace;"
            " padding: 2px 4px; border: none;"
        )
        window._path_label.setWordWrap(True)
        window._path_label.hide()
        source_inner.addWidget(window._path_label)

        fields_row = QHBoxLayout()
        fields_row.setSpacing(10)

        source_lbl = QLabel("Source:")
        source_lbl.setFixedWidth(55)
        source_lbl.setStyleSheet(f"color: {_TEXT_SECONDARY}; font-size: 12px;")
        fields_row.addWidget(source_lbl)
        window._source_field = QLineEdit()
        window._source_field.setPlaceholderText("e.g. manga_name")
        fields_row.addWidget(window._source_field)

        run_id_lbl = QLabel("Run ID:")
        run_id_lbl.setFixedWidth(50)
        run_id_lbl.setStyleSheet(f"color: {_TEXT_SECONDARY}; font-size: 12px;")
        fields_row.addWidget(run_id_lbl)
        window._run_id_field = QLineEdit()
        window._run_id_field.setPlaceholderText("e.g. vol01")
        fields_row.addWidget(window._run_id_field)

        source_inner.addLayout(fields_row)
        outer.addWidget(source_frame)

        # --- Deck & OCR config ---
        config_frame = QFrame()
        config_frame.setStyleSheet(_section_frame_style())
        config_inner = QHBoxLayout(config_frame)
        config_inner.setContentsMargins(12, 10, 12, 10)
        config_inner.setSpacing(16)

        form_left = QFormLayout()
        form_left.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_left.setSpacing(6)
        window._volume_field = QLineEdit()
        window._volume_field.setPlaceholderText("optional, e.g. 02")
        window._chapter_field = QLineEdit()
        window._chapter_field.setPlaceholderText("optional, e.g. 07")
        _form_label_style = f"color: {_TEXT_SECONDARY}; font-size: 12px;"
        vol_lbl = QLabel("Volume:")
        vol_lbl.setStyleSheet(_form_label_style)
        ch_lbl = QLabel("Chapter:")
        ch_lbl.setStyleSheet(_form_label_style)
        form_left.addRow(vol_lbl, window._volume_field)
        form_left.addRow(ch_lbl, window._chapter_field)
        config_inner.addLayout(form_left)

        form_right = QFormLayout()
        form_right.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_right.setSpacing(6)
        window._ocr_combo = QComboBox()
        window._ocr_combo.addItems(["manga-ocr", "tesseract", "sidecar"])
        window._detector_combo = QComboBox()
        window._detector_combo.addItems(["none", "paddleocr"])
        ocr_lbl = QLabel("OCR Engine:")
        ocr_lbl.setStyleSheet(_form_label_style)
        det_lbl = QLabel("Detector:")
        det_lbl.setStyleSheet(_form_label_style)
        form_right.addRow(ocr_lbl, window._ocr_combo)
        form_right.addRow(det_lbl, window._detector_combo)
        config_inner.addLayout(form_right)

        outer.addWidget(config_frame)

        # --- Action buttons ---
        btn_frame = QFrame()
        btn_frame.setStyleSheet(_section_frame_style())
        btn_inner = QHBoxLayout(btn_frame)
        btn_inner.setContentsMargins(12, 8, 12, 8)
        btn_inner.setSpacing(8)

        window._scan_btn = QPushButton("Scan")
        window._scan_btn.setStyleSheet(_btn_style("rgba(255,255,255,20)", "rgba(255,255,255,35)"))
        window._review_btn = QPushButton("Review")
        window._review_btn.setStyleSheet(_btn_style("rgba(255,255,255,20)", "rgba(255,255,255,35)"))
        window._build_btn = QPushButton("Build")
        window._build_btn.setStyleSheet(_btn_style("rgba(255,255,255,20)", "rgba(255,255,255,35)"))
        window._run_all_btn = QPushButton("Run All")
        window._run_all_btn.setStyleSheet(_btn_style(_ACCENT_BLUE, _ACCENT_BLUE_HOVER))

        for btn in (window._scan_btn, window._review_btn, window._build_btn, window._run_all_btn):
            btn_inner.addWidget(btn)

        btn_inner.addStretch()

        window._clear_btn = QPushButton("Clear")
        window._clear_btn.setStyleSheet(_btn_style("#883322", "#5C2216"))
        btn_inner.addWidget(window._clear_btn)
        outer.addWidget(btn_frame)

        # --- Progress bar ---
        window._progress_bar = QProgressBar()
        window._progress_bar.setRange(0, 100)
        window._progress_bar.setValue(0)
        window._progress_bar.setFixedHeight(14)
        window._progress_bar.setTextVisible(False)
        outer.addWidget(window._progress_bar)

        # --- Review panel (hidden until scan completes) ---
        from jp_anki_builder.gui.review_panel import ReviewPanel  # noqa: PLC0415
        window._review_panel = ReviewPanel(data_dir=window._data_dir)
        window._review_panel.hide()
        window._review_panel.review_completed.connect(window._on_review_completed)
        outer.addWidget(window._review_panel, stretch=2)

        # --- Log output ---
        log_frame = QFrame()
        log_frame.setStyleSheet(_section_frame_style())
        log_inner = QVBoxLayout(log_frame)
        log_inner.setContentsMargins(8, 8, 8, 8)
        log_inner.setSpacing(4)
        log_hdr = QLabel("Log")
        log_hdr.setStyleSheet(f"color: {_TEXT_SECONDARY}; font-size: 11px; font-weight: bold;")
        log_inner.addWidget(log_hdr)
        window._log_view = QTextEdit()
        window._log_view.setReadOnly(True)
        window._log_view.setMinimumHeight(120)
        log_inner.addWidget(window._log_view)
        outer.addWidget(log_frame, stretch=1)

        return tab

    def _build_realtime_tab(window: "MainWindow") -> QWidget:
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        # --- Launch controls ---
        launch_frame = QFrame()
        launch_frame.setStyleSheet(_section_frame_style())
        launch_inner = QVBoxLayout(launch_frame)
        launch_inner.setContentsMargins(16, 14, 16, 14)
        launch_inner.setSpacing(12)

        launch_title = QLabel("Real-Time Screen OCR Overlay")
        launch_title.setStyleSheet(f"color: {_TEXT_PRIMARY}; font-size: 14px; font-weight: bold;")
        launch_inner.addWidget(launch_title)

        launch_btn_row = QHBoxLayout()
        window._launch_overlay_btn = QPushButton("Launch Overlay")
        window._launch_overlay_btn.setStyleSheet(_btn_style(_ACCENT_GREEN, _ACCENT_GREEN_HOVER))
        window._stop_overlay_btn = QPushButton("Stop Overlay")
        window._stop_overlay_btn.setStyleSheet(_btn_style("#883322", "#5C2216"))
        window._stop_overlay_btn.setEnabled(False)
        launch_btn_row.addWidget(window._launch_overlay_btn)
        launch_btn_row.addWidget(window._stop_overlay_btn)
        launch_btn_row.addStretch()
        launch_inner.addLayout(launch_btn_row)

        outer.addWidget(launch_frame)

        # --- Capture config ---
        cap_frame = QFrame()
        cap_frame.setStyleSheet(_section_frame_style())
        cap_inner = QFormLayout(cap_frame)
        cap_inner.setContentsMargins(16, 12, 16, 12)
        cap_inner.setSpacing(8)
        cap_inner.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        _lbl_style = f"color: {_TEXT_SECONDARY}; font-size: 12px;"
        window._capture_backend_combo = QComboBox()
        window._capture_backend_combo.addItems(["dxcam", "mss"])
        cap_lbl = QLabel("Capture Backend:")
        cap_lbl.setStyleSheet(_lbl_style)
        cap_inner.addRow(cap_lbl, window._capture_backend_combo)

        window._roi_size_spin = QSpinBox()
        window._roi_size_spin.setRange(50, 1000)
        window._roi_size_spin.setValue(80)
        window._roi_size_spin.setSuffix(" px")
        window._roi_size_spin.setStyleSheet(
            f"QSpinBox {{ background: rgba(255,255,255,15); color: {_TEXT_PRIMARY};"
            f" border: 1px solid {_BORDER_COLOR}; border-radius: 4px; padding: 3px 6px; }}"
        )
        roi_lbl = QLabel("ROI Size:")
        roi_lbl.setStyleSheet(_lbl_style)
        cap_inner.addRow(roi_lbl, window._roi_size_spin)

        outer.addWidget(cap_frame)

        # --- Hotkey display ---
        hk_frame = QFrame()
        hk_frame.setStyleSheet(_section_frame_style())
        hk_inner = QFormLayout(hk_frame)
        hk_inner.setContentsMargins(16, 12, 16, 12)
        hk_inner.setSpacing(8)
        hk_inner.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        hk_title = QLabel("Hotkeys (configure in Settings)")
        hk_title.setStyleSheet(f"color: {_TEXT_PRIMARY}; font-size: 13px; font-weight: bold;")
        hk_inner.addRow(hk_title)

        cfg = window._config
        window._hk_scan_lbl = QLabel(cfg.hotkey_scan or "shift")
        window._hk_export_lbl = QLabel(cfg.hotkey_export or "shift+e")

        for lbl in (window._hk_scan_lbl, window._hk_export_lbl):
            lbl.setStyleSheet(
                f"color: #FFD700; font-family: monospace; font-size: 12px;"
                f" background: rgba(90,70,0,120); border-radius: 3px; padding: 1px 6px;"
            )

        scan_lbl = QLabel("Scan:")
        scan_lbl.setStyleSheet(_lbl_style)
        exp_lbl = QLabel("Export:")
        exp_lbl.setStyleSheet(_lbl_style)
        hk_inner.addRow(scan_lbl, window._hk_scan_lbl)

        select_lbl = QLabel("Select Word:")
        select_lbl.setStyleSheet(_lbl_style)
        select_val = QLabel("shift+1…9")
        select_val.setStyleSheet(
            f"color: #4FC3F7; font-family: monospace; font-size: 12px;"
            f" background: rgba(30,80,120,120); border-radius: 3px; padding: 1px 6px;"
        )
        hk_inner.addRow(select_lbl, select_val)

        hk_inner.addRow(exp_lbl, window._hk_export_lbl)

        outer.addWidget(hk_frame)

        # --- Embedded buffer panel (word list for current session) ---
        from jp_anki_builder.realtime.buffer_panel import BufferPanel  # noqa: PLC0415
        buf_frame = QFrame()
        buf_frame.setStyleSheet(_section_frame_style())
        buf_inner = QVBoxLayout(buf_frame)
        buf_inner.setContentsMargins(0, 0, 0, 0)
        buf_inner.setSpacing(0)

        window._buffer_panel = BufferPanel(parent=buf_frame)
        buf_inner.addWidget(window._buffer_panel)

        outer.addWidget(buf_frame, stretch=1)

        return tab

    def _build_settings_tab(window: "MainWindow") -> QWidget:
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(10)
        scroll_layout.setContentsMargins(0, 0, 4, 0)

        # --- General config keys ---
        cfg_frame = QFrame()
        cfg_frame.setStyleSheet(_section_frame_style())
        cfg_inner = QFormLayout(cfg_frame)
        cfg_inner.setContentsMargins(16, 12, 16, 12)
        cfg_inner.setSpacing(8)
        cfg_inner.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        cfg_title = QLabel("Project Defaults")
        cfg_title.setStyleSheet(f"color: {_TEXT_PRIMARY}; font-size: 13px; font-weight: bold;")
        cfg_inner.addRow(cfg_title)

        _lbl_style = f"color: {_TEXT_SECONDARY}; font-size: 12px;"
        window._settings_fields: dict[str, QWidget] = {}
        cfg = window._config
        bool_keys = {
            "no_preprocess", "exclude_sfx", "exclude_stray_furigana",
            "save_debug_overlays", "ankiconnect_enabled",
        }
        int_keys = {"ankiconnect_port"}

        for key in sorted(VALID_KEYS):
            current_val = getattr(cfg, key, None)
            lbl = QLabel(key.replace("_", " ").title() + ":")
            lbl.setStyleSheet(_lbl_style)
            if key in bool_keys:
                widget: QWidget = QCheckBox()
                widget.setChecked(bool(current_val))
                widget.setStyleSheet(f"color: {_TEXT_PRIMARY};")
            elif key in int_keys:
                widget = QSpinBox()
                widget.setRange(1, 65535)
                widget.setValue(int(current_val) if current_val is not None else 8765)
                widget.setStyleSheet(
                    f"QSpinBox {{ background: rgba(255,255,255,15); color: {_TEXT_PRIMARY};"
                    f" border: 1px solid {_BORDER_COLOR}; border-radius: 4px; padding: 3px 6px; }}"
                )
            else:
                widget = QLineEdit()
                widget.setText(str(current_val) if current_val is not None else "")
                widget.setPlaceholderText("(not set)")
            cfg_inner.addRow(lbl, widget)
            window._settings_fields[key] = widget

        scroll_layout.addWidget(cfg_frame)

        # --- Dictionary management ---
        dict_frame = QFrame()
        dict_frame.setStyleSheet(_section_frame_style())
        dict_inner = QVBoxLayout(dict_frame)
        dict_inner.setContentsMargins(16, 12, 16, 12)
        dict_inner.setSpacing(8)

        dict_title = QLabel("Dictionary Management")
        dict_title.setStyleSheet(f"color: {_TEXT_PRIMARY}; font-size: 13px; font-weight: bold;")
        dict_inner.addWidget(dict_title)

        dict_info = QLabel(
            "JMdict: installed via 'install-dictionary' command.\n"
            "Yomichan: install ZIP files via 'install-yomichan-dict' command."
        )
        dict_info.setStyleSheet(f"color: {_TEXT_SECONDARY}; font-size: 11px;")
        dict_info.setWordWrap(True)
        dict_inner.addWidget(dict_info)

        dict_btn_row = QHBoxLayout()
        window._install_jmdict_btn = QPushButton("Install JMdict")
        window._install_jmdict_btn.setStyleSheet(
            _btn_style("rgba(255,255,255,20)", "rgba(255,255,255,35)")
        )
        window._install_yomichan_btn = QPushButton("Install Yomichan Dict…")
        window._install_yomichan_btn.setStyleSheet(
            _btn_style("rgba(255,255,255,20)", "rgba(255,255,255,35)")
        )
        dict_btn_row.addWidget(window._install_jmdict_btn)
        dict_btn_row.addWidget(window._install_yomichan_btn)
        dict_btn_row.addStretch()
        dict_inner.addLayout(dict_btn_row)

        scroll_layout.addWidget(dict_frame)
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        outer.addWidget(scroll, stretch=1)

        # --- Save / Reset buttons ---
        save_row = QHBoxLayout()
        window._settings_save_btn = QPushButton("Save")
        window._settings_save_btn.setStyleSheet(_btn_style(_ACCENT_BLUE, _ACCENT_BLUE_HOVER))
        window._settings_reset_btn = QPushButton("Reset to Defaults")
        window._settings_reset_btn.setStyleSheet(
            _btn_style("rgba(255,255,255,15)", "rgba(255,255,255,30)")
        )
        window._settings_save_btn.clicked.connect(window._on_settings_save)
        window._settings_reset_btn.clicked.connect(window._on_settings_reset)
        save_row.addStretch()
        save_row.addWidget(window._settings_reset_btn)
        save_row.addWidget(window._settings_save_btn)
        outer.addLayout(save_row)

        return tab

    # -----------------------------------------------------------------------
    # Main window
    # -----------------------------------------------------------------------

    class MainWindow(QMainWindow):
        """Main application window with tabs for batch processing, realtime overlay, and settings."""

        def __init__(self, data_dir: str = "data") -> None:
            super().__init__()
            self._data_dir = data_dir
            self._config = load_project_config(data_dir=data_dir)

            # Runtime state
            self._images_path: str = ""
            self._active_worker = None
            self._overlay_app = None
            self._approved_words: list[str] = []

            self.setWindowTitle("JP Anki Builder")
            self.resize(780, 620)
            self.setMinimumSize(600, 480)
            self.setStyleSheet(_WINDOW_STYLESHEET)

            central = QWidget()
            central.setObjectName("central")
            self.setCentralWidget(central)
            main_layout = QVBoxLayout(central)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(0)

            self._tabs = QTabWidget()
            self._tabs.addTab(_build_batch_tab(self), "Batch Processing")
            self._tabs.addTab(_build_realtime_tab(self), "Real-Time Overlay")
            self._tabs.addTab(_build_settings_tab(self), "Settings")
            main_layout.addWidget(self._tabs)

            # Status bar
            self._status_bar = QStatusBar()
            self.setStatusBar(self._status_bar)
            self._status_bar.showMessage("Ready")

            # Wire batch action buttons
            self._scan_btn.clicked.connect(self._on_scan_clicked)
            self._build_btn.clicked.connect(self._on_build_clicked)
            self._run_all_btn.clicked.connect(self._on_run_all_clicked)
            self._clear_btn.clicked.connect(self._on_clear_clicked)

            # Wire realtime buttons
            self._launch_overlay_btn.clicked.connect(self._on_launch_overlay)
            self._stop_overlay_btn.clicked.connect(self._on_stop_overlay)

            # Wire settings dictionary buttons
            self._install_jmdict_btn.clicked.connect(self._on_install_jmdict)
            self._install_yomichan_btn.clicked.connect(self._on_install_yomichan)

        # ------------------------------------------------------------------
        # Public helpers (for wiring in Task 4.06)
        # ------------------------------------------------------------------

        def append_log(self, text: str) -> None:
            """Append a line to the log output area."""
            self._log_view.append(text)

        def set_progress(self, value: int) -> None:
            """Set the progress bar value (0–100)."""
            self._progress_bar.setValue(max(0, min(100, value)))

        def set_status(self, message: str) -> None:
            """Update the status bar message."""
            self._status_bar.showMessage(message)

        def closeEvent(self, event) -> None:  # noqa: N802
            """Clean up worker threads and overlay before closing."""
            if self._active_worker is not None and self._active_worker.isRunning():
                self._active_worker.requestInterruption()
                self._active_worker.wait(3000)
            worker = getattr(self, "_dict_install_worker", None)
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.wait(3000)
            if self._overlay_app is not None:
                try:
                    self._overlay_app.shutdown()
                except Exception:
                    pass
                self._overlay_app = None
            super().closeEvent(event)

        # ------------------------------------------------------------------
        # Slot stubs (wired in Task 4.06)
        # ------------------------------------------------------------------

        def _on_path_dropped(self, path: str) -> None:
            """Populate source/run_id fields from a dropped path."""
            from jp_anki_builder.path_inference import infer_source_and_run_id
            self._images_path = path
            p = Path(path)
            if p.is_file():
                # Video/container: source = parent dir, run_id = stem
                source = p.parent.name
                run_id = p.stem
            else:
                source, run_id = infer_source_and_run_id(path)
                source = source or ""
                run_id = run_id or ""
            self._source_field.setText(source)
            self._run_id_field.setText(run_id)
            self._path_label.setText(path)
            self._path_label.show()
            self.set_status("Ready")

        def _on_clear_clicked(self) -> None:
            """Reset the batch tab to its initial state."""
            self._images_path = ""
            self._approved_words = []
            self._source_field.clear()
            self._run_id_field.clear()
            self._volume_field.clear()
            self._chapter_field.clear()
            self._path_label.setText("")
            self._path_label.hide()
            self._review_panel.hide()
            self._log_view.clear()
            self.set_progress(0)
            self.set_status("Ready")

        # ------------------------------------------------------------------
        # Pipeline helper
        # ------------------------------------------------------------------

        def _get_pipeline(self):
            from jp_anki_builder.pipeline import Pipeline
            return Pipeline(data_dir=self._data_dir)

        # ------------------------------------------------------------------
        # Batch pipeline slots
        # ------------------------------------------------------------------

        def _set_buttons_enabled(self, enabled: bool) -> None:
            for btn in (self._scan_btn, self._build_btn, self._run_all_btn):
                btn.setEnabled(enabled)

        def _on_scan_clicked(self) -> None:
            from jp_anki_builder.gui.workers import ScanWorker, SubScanWorker

            source = self._source_field.text().strip()
            run_id = self._run_id_field.text().strip()
            if not source or not run_id:
                self.set_status("Set Source and Run ID before scanning.")
                return
            if not self._images_path:
                self.set_status("Drop or browse a source path first.")
                return

            self._set_buttons_enabled(False)
            self.set_progress(0)

            suffix = Path(self._images_path).suffix.lower()
            if suffix in {".mkv", ".mp4", ".avi", ".mov"}:
                worker = SubScanWorker(
                    video=self._images_path,
                    source=source,
                    run_id=run_id,
                    data_dir=self._data_dir,
                )
            else:
                worker = ScanWorker(
                    pipeline=self._get_pipeline(),
                    images=self._images_path,
                    source=source,
                    run_id=run_id,
                    ocr_mode=self._ocr_combo.currentText(),
                    detector_mode=self._detector_combo.currentText(),
                )

            worker.log_message.connect(self.append_log)
            worker.scan_finished.connect(self._on_scan_finished)
            worker.error.connect(self._on_worker_error)
            self._active_worker = worker
            worker.start()
            self.set_status("Scanning…")

        def _on_scan_finished(self, result: dict) -> None:
            self.set_progress(50)
            source = self._source_field.text().strip()

            from jp_anki_builder.config import RunPaths
            run_id = result.get("run_id") or self._run_id_field.text().strip()
            paths = RunPaths(
                base_dir=self._data_dir,
                source_id=source,
                run_id=run_id,
            )
            scan_path = paths.scan_artifact
            if scan_path.exists():
                self._review_panel.load_candidates(scan_path, source)
                self._review_panel.show()

            self._set_buttons_enabled(True)
            self.set_status(
                f"Scan complete — {result.get('candidate_count', 0)} candidates. "
                "Review then click Build."
            )

        def _on_build_clicked(self) -> None:
            from jp_anki_builder.gui.workers import BuildWorker

            source = self._source_field.text().strip()
            run_id = self._run_id_field.text().strip()
            if not source or not run_id:
                self.set_status("Set Source and Run ID before building.")
                return

            approved = self._approved_words or self._review_panel.approved_lemmas()
            if not approved:
                self.set_status("No approved words to build.")
                return

            self._set_buttons_enabled(False)
            worker = BuildWorker(
                pipeline=self._get_pipeline(),
                source=source,
                run_id=run_id,
                approved_words=approved,
                volume=self._volume_field.text().strip() or None,
                chapter=self._chapter_field.text().strip() or None,
            )
            worker.log_message.connect(self.append_log)
            worker.build_finished.connect(self._on_build_finished)
            worker.error.connect(self._on_worker_error)
            self._active_worker = worker
            worker.start()
            self.set_status("Building deck…")

        def _on_build_finished(self, result: dict) -> None:
            self.set_progress(100)
            self._set_buttons_enabled(True)
            pkg = result.get("package_path", "")
            count = result.get("buildable_word_count", 0)
            self.set_status(f"Build complete — {count} cards. Package: {pkg}")

        def _on_run_all_clicked(self) -> None:
            from jp_anki_builder.gui.workers import RunAllWorker

            source = self._source_field.text().strip()
            run_id = self._run_id_field.text().strip()
            if not source or not run_id:
                self.set_status("Set Source and Run ID before running.")
                return
            if not self._images_path:
                self.set_status("Drop or browse a source path first.")
                return

            self._set_buttons_enabled(False)
            self.set_progress(0)
            worker = RunAllWorker(
                pipeline=self._get_pipeline(),
                images=self._images_path,
                source=source,
                run_id=run_id,
                ocr_mode=self._ocr_combo.currentText(),
                detector_mode=self._detector_combo.currentText(),
                volume=self._volume_field.text().strip() or None,
                chapter=self._chapter_field.text().strip() or None,
            )
            worker.log_message.connect(self.append_log)
            worker.run_finished.connect(self._on_run_all_finished)
            worker.error.connect(self._on_worker_error)
            self._active_worker = worker
            worker.start()
            self.set_status("Running full pipeline…")

        def _on_run_all_finished(self, result: dict) -> None:
            self.set_progress(100)
            self._set_buttons_enabled(True)
            build = result.get("build", {})
            pkg = build.get("package_path", "")
            count = build.get("buildable_word_count", 0)
            self.set_status(f"Run complete — {count} cards. Package: {pkg}")

        def _on_worker_error(self, message: str) -> None:
            self.append_log(f"[ERROR] {message}")
            self.set_progress(0)
            self._set_buttons_enabled(True)
            self.set_status(f"Error: {message}")

        def _on_review_completed(self, approved: list) -> None:
            """Called when ReviewPanel emits review_completed — auto-trigger build."""
            self._approved_words = list(approved)
            self.append_log(f"[REVIEW] {len(approved)} words approved. Starting build…")
            self._on_build_clicked()

        # ------------------------------------------------------------------
        # Realtime overlay slots
        # ------------------------------------------------------------------

        def _on_launch_overlay(self) -> None:
            if self._overlay_app is not None:
                self.set_status("Overlay already running.")
                return
            try:
                from jp_anki_builder.realtime.app import OverlayApp
                cfg = self._config
                self._overlay_app = OverlayApp(
                    data_dir=self._data_dir,
                    capture_backend=self._capture_backend_combo.currentText(),
                    hotkey_scan=cfg.hotkey_scan or "shift",
                    hotkey_add_word=cfg.hotkey_add_word or "shift+q",
                    hotkey_export=cfg.hotkey_export or "shift+e",
                    buffer_panel=self._buffer_panel,
                )
                # Start components without calling exec() — we're already in an event loop
                try:
                    self._overlay_app._hotkeys.start()
                except RuntimeError as exc:
                    logger.warning("hotkey manager unavailable: %s", exc)
                self._launch_overlay_btn.setEnabled(False)
                self._stop_overlay_btn.setEnabled(True)
                self.set_status("Overlay launched.")
            except Exception as exc:
                logger.exception("Failed to launch overlay")
                self.set_status(f"Overlay launch failed: {exc}")

        def _on_stop_overlay(self) -> None:
            if self._overlay_app is None:
                return
            try:
                self._overlay_app.shutdown()
            except Exception as exc:
                logger.warning("Overlay shutdown error: %s", exc)
            finally:
                self._overlay_app = None
                self._launch_overlay_btn.setEnabled(True)
                self._stop_overlay_btn.setEnabled(False)
                self.set_status("Overlay stopped.")

        # ------------------------------------------------------------------
        # Dictionary management slots
        # ------------------------------------------------------------------

        def _on_install_jmdict(self) -> None:
            from jp_anki_builder.gui.workers import DictInstallWorker

            self._install_jmdict_btn.setEnabled(False)
            self.set_status("Installing JMdict… (this may take a few minutes)")
            worker = DictInstallWorker(data_dir=self._data_dir)
            worker.log_message.connect(self.append_log)
            worker.install_finished.connect(self._on_jmdict_installed)
            worker.error.connect(self._on_jmdict_install_error)
            self._dict_install_worker = worker
            worker.start()

        def _on_jmdict_installed(self, message: str) -> None:
            self._install_jmdict_btn.setEnabled(True)
            self.set_status(message)

        def _on_jmdict_install_error(self, message: str) -> None:
            self._install_jmdict_btn.setEnabled(True)
            self.set_status(f"JMdict install failed: {message}")

        def _on_install_yomichan(self) -> None:
            from jp_anki_builder.yomichan_dict import YomichanDictionary
            import shutil

            zip_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Yomichan dictionary ZIP",
                "",
                "ZIP files (*.zip);;All files (*)",
            )
            if not zip_path:
                return
            try:
                # Validate
                YomichanDictionary.from_zip(Path(zip_path))
                dest_dir = Path(self._data_dir) / "dictionaries" / "yomichan"
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / Path(zip_path).name
                shutil.copy2(zip_path, dest)
                self.set_status(f"Yomichan dict installed: {dest.name}")
            except Exception as exc:
                logger.exception("Yomichan install failed")
                self.set_status(f"Yomichan install failed: {exc}")

        def _on_settings_save(self) -> None:
            """Persist settings field values to the project config file."""
            from jp_anki_builder.project_config import set_config
            bool_keys = {
                "no_preprocess", "exclude_sfx", "exclude_stray_furigana",
                "save_debug_overlays", "ankiconnect_enabled",
            }
            int_keys = {"ankiconnect_port"}
            saved = []
            for key, widget in self._settings_fields.items():
                try:
                    if isinstance(widget, QCheckBox):
                        set_config(key, "true" if widget.isChecked() else "false",
                                   data_dir=self._data_dir)
                    elif isinstance(widget, QSpinBox):
                        set_config(key, str(widget.value()), data_dir=self._data_dir)
                    else:
                        val = widget.text().strip()
                        if val:
                            set_config(key, val, data_dir=self._data_dir)
                    saved.append(key)
                except Exception as exc:
                    logger.warning("Could not save setting %s: %s", key, exc)
            self.set_status(f"Settings saved ({len(saved)} keys).")

        def _on_settings_reset(self) -> None:
            """Reset all settings fields to their current config-file values."""
            cfg = load_project_config(data_dir=self._data_dir)
            for key, widget in self._settings_fields.items():
                val = getattr(cfg, key, None)
                if isinstance(widget, QCheckBox):
                    widget.setChecked(bool(val))
                elif isinstance(widget, QSpinBox):
                    widget.setValue(int(val) if val is not None else 8765)
                else:
                    widget.setText(str(val) if val is not None else "")
            self.set_status("Settings reset to saved values.")

except ImportError:
    class MainWindow:  # type: ignore[no-redef]
        """Stub used when PySide6 is not installed."""

        def __init__(self, data_dir: str = "data") -> None:
            raise ImportError(
                "The GUI requires PySide6. Install with: pip install PySide6"
            )
