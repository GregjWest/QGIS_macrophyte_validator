"""
Dock panel for macrophyte field data collection.
Compact layout for scaled laptop screens.
Single Habitat selection (Seagrass OR Mangrove/Saltmarsh) + free-text Comments.
Capture mode toggle: Live GPS and Map-click are side-by-side and mutually exclusive.
"""

from qgis.PyQt.QtCore import pyqtSignal, QDateTime, QTimer
from qgis.PyQt.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                 QGridLayout, QPushButton, QLabel,
                                 QTextEdit, QGroupBox, QMessageBox,
                                 QScrollArea, QFrame)

ACTIVE_STYLE = "QPushButton { background-color: #2e7d32; color: white; font-weight: bold; border: 1px solid #1b5e20; border-radius: 3px; }"
DEFAULT_STYLE = "QPushButton { background-color: #f0f0f0; border: 1px solid #aaa; border-radius: 3px; } QPushButton:hover { background-color: #dde; }"
ADD_STYLE = "QPushButton { background-color: #1565C0; color: white; font-weight: bold; border-radius: 4px; padding: 4px; }"
CLEAR_STYLE = "QPushButton { background-color: #c62828; color: white; border-radius: 4px; padding: 4px; }"

TOOL_ACTIVE_STYLE = (
    "QPushButton { background-color: #1565C0; color: white; font-weight: bold; "
    "border: 2px solid #0d47a1; border-radius: 4px; padding: 4px; }"
)
TOOL_INACTIVE_STYLE = (
    "QPushButton { background-color: #f5a623; color: #3a2a00; font-weight: bold; "
    "border: 2px solid #c8800a; border-radius: 4px; padding: 4px; }"
)

HABITAT_VALUE_MAP = {
    # Seagrass
    "Posidonia":     "Posidonia",
    "Sparse Pos":    "Sparse Posidonia",
    "Pos/Zost":      "Posidonia/Zostera",
    "Halophila":     "Halophila",
    "Zostera":       "Zostera",
    "Sparse Zos":    "Sparse Zostera",
    "Zost/Ruppia":   "Zostera/Ruppia",
    "Ruppia":        "Ruppia",
    "Caulerpa":      "Caulerpa",
    "Algae":         "Algae",
    "Sand":          "Sand",
    "Rock":          "Rock",
    "Wrack":         "Wrack",
    "Deep edge":     "Deep edge",
    "Boundary":      "Boundary",
    "Other":         "Other",
    "As mapped":     "As mapped",
    # Mangrove / Saltmarsh
    "Single Tree":    "Single mangrove tree",
    "Small group":    "Small group of mangroves",
    "Avicennia":      "Avicennia marina",
    "Aegiceras":      "Aegiceras corniculatum",
    "Scattered":      "Scattered mangroves",
    "No mangroves":   "No mangroves present",
    "Rhizophora":     "Rhizophora stylosa",
    "Exoecaria":      "Exoecaria agallocha",
    "Fringing":       "Fringing mangroves",
    "Man/SM":         "Mangrove/Saltmarsh mosaic",
    "Bruguiera":      "Bruguiera gymnorrhiza",
    "Widespread":     "Widespread mangroves",
    "Saltmarsh":      "Saltmarsh",
    "No Saltmarsh":   "No saltmarsh present",
}


class MacrophyteDockWidget(QWidget):

    record_requested = pyqtSignal(dict)
    activate_tool_requested = pyqtSignal()
    cancel_point_requested = pyqtSignal()
    gps_toggle_requested = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.current_habitat = ""
        self.current_habitat_label = ""
        self.longitude = None
        self.latitude = None
        self.coord_source = "GPS"
        self.capture_mode = "map_click"
        self._sg_buttons = {}
        self._mn_buttons = {}
        self._init_ui()

    # ------------------------------------------------------------------
    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(3)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(4)
        scroll.setWidget(container)
        outer.addWidget(scroll)

        # ── Capture mode — side by side in one compact group ────────
        mode_box = QGroupBox("Capture Mode")
        mode_lay = QVBoxLayout()
        mode_lay.setSpacing(3)
        mode_lay.setContentsMargins(4, 4, 4, 4)

        mode_btn_row = QHBoxLayout()
        mode_btn_row.setSpacing(4)

        self.resume_btn = QPushButton()
        self.resume_btn.setMinimumHeight(30)
        self.resume_btn.clicked.connect(self._on_resume_clicked)
        mode_btn_row.addWidget(self.resume_btn)

        self.gps_btn = QPushButton()
        self.gps_btn.setCheckable(True)
        self.gps_btn.setMinimumHeight(30)
        self.gps_btn.clicked.connect(self._on_gps_clicked)
        mode_btn_row.addWidget(self.gps_btn)

        mode_lay.addLayout(mode_btn_row)

        coord_row = QHBoxLayout()
        coord_row.setSpacing(8)
        self.lat_lbl = QLabel("Lat: —")
        self.lon_lbl = QLabel("Lon: —")
        self.lat_lbl.setStyleSheet("font-size: 9pt; color: #444;")
        self.lon_lbl.setStyleSheet("font-size: 9pt; color: #444;")
        coord_row.addWidget(self.lat_lbl)
        coord_row.addWidget(self.lon_lbl)
        coord_row.addStretch()
        mode_lay.addLayout(coord_row)

        mode_box.setLayout(mode_lay)
        layout.addWidget(mode_box)

        self._refresh_mode_buttons()

        # ── Status ───────────────────────────────────────────────────
        self.status_lbl = QLabel("No selection")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setStyleSheet(
            "QLabel { background: #e8f5e9; border: 1px solid #a5d6a7; "
            "border-radius: 3px; padding: 3px; font-size: 9pt; }")
        layout.addWidget(self.status_lbl)

        # ── Seagrass ─────────────────────────────────────────────────
        sg_box = QGroupBox("Seagrass")
        sg_grid = QGridLayout()
        sg_grid.setSpacing(2)
        sg_grid.setContentsMargins(4, 4, 4, 4)
        seagrass_rows = [
            ["Posidonia",  "Sparse Pos",  "Pos/Zost",    "Halophila"],
            ["Zostera",    "Sparse Zos",  "Zost/Ruppia", "Ruppia"],
            ["Caulerpa",   "Algae",       "Sand",        "Rock"],
            ["Wrack",      "Deep edge",   "Boundary",    "Other"],
        ]
        for r, row in enumerate(seagrass_rows):
            for c, text in enumerate(row):
                btn = QPushButton(text)
                btn.setStyleSheet(DEFAULT_STYLE)
                btn.setMaximumHeight(26)
                btn.setMinimumHeight(26)
                btn.clicked.connect(
                    lambda checked, t=text: self._habitat_clicked(t, self._sg_buttons))
                sg_grid.addWidget(btn, r, c)
                self._sg_buttons[text] = btn

        mapped_btn = QPushButton("As mapped")
        mapped_btn.setStyleSheet(DEFAULT_STYLE)
        mapped_btn.setMaximumHeight(26)
        mapped_btn.setMinimumHeight(26)
        mapped_btn.clicked.connect(
            lambda: self._habitat_clicked("As mapped", self._sg_buttons))
        self._sg_buttons["As mapped"] = mapped_btn

        sg_clear = QPushButton("Clear")
        sg_clear.setStyleSheet(CLEAR_STYLE)
        sg_clear.setMaximumHeight(26)
        sg_clear.setMinimumHeight(26)
        sg_clear.clicked.connect(self._clear_habitat)

        sg_grid.addWidget(mapped_btn, 4, 0, 1, 2)
        sg_grid.addWidget(sg_clear,   4, 2, 1, 2)
        sg_box.setLayout(sg_grid)
        layout.addWidget(sg_box)

        # ── Mangrove / Saltmarsh ─────────────────────────────────────
        mn_box = QGroupBox("Mangrove / Saltmarsh")
        mn_grid = QGridLayout()
        mn_grid.setSpacing(2)
        mn_grid.setContentsMargins(4, 4, 4, 4)
        mangrove_rows = [
            ["Single Tree",   "Small group",  "Avicennia",   "Aegiceras"],
            ["Scattered",     "No mangroves", "Rhizophora",  "Exoecaria"],
            ["Fringing",      "Man/SM",       "Bruguiera",   ""],
            ["Widespread",    "Saltmarsh",    "No Saltmarsh", ""],
        ]
        for r, row in enumerate(mangrove_rows):
            for c, text in enumerate(row):
                if not text:
                    continue
                btn = QPushButton(text)
                btn.setStyleSheet(DEFAULT_STYLE)
                btn.setMaximumHeight(26)
                btn.setMinimumHeight(26)
                btn.clicked.connect(
                    lambda checked, t=text: self._habitat_clicked(t, self._mn_buttons))
                mn_grid.addWidget(btn, r, c)
                self._mn_buttons[text] = btn

        mn_box.setLayout(mn_grid)
        layout.addWidget(mn_box)

        # ── Comments ─────────────────────────────────────────────────
        cmt_box = QGroupBox("Comments")
        cmt_lay = QVBoxLayout()
        cmt_lay.setSpacing(2)
        cmt_lay.setContentsMargins(4, 4, 4, 4)

        self.comments_edit = QTextEdit()
        self.comments_edit.setFixedHeight(50)
        self.comments_edit.setPlaceholderText("Type or use buttons below…")
        cmt_lay.addWidget(self.comments_edit)

        for word_row in [
            ["Posidonia", "Zostera",  "Halophila", "Ruppia",  "Caulerpa"],
            ["Wrack",     "Algae",    "Rock",      "Sand",    "and"],
            ["Dense",     "Medium",   "Sparse",    "with",    "Clear"],
        ]:
            row_lay = QHBoxLayout()
            row_lay.setSpacing(2)
            for w in word_row:
                btn = QPushButton(w)
                btn.setMaximumHeight(26)
                btn.setMinimumHeight(26)
                if w == "Clear":
                    btn.setStyleSheet(CLEAR_STYLE)
                    btn.clicked.connect(self.comments_edit.clear)
                else:
                    btn.setStyleSheet(DEFAULT_STYLE)
                    btn.clicked.connect(
                        lambda checked, t=w: self._append_comment(t))
                row_lay.addWidget(btn)
            cmt_lay.addLayout(row_lay)

        cmt_box.setLayout(cmt_lay)
        layout.addWidget(cmt_box)

        # ── Bottom buttons ───────────────────────────────────────────
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(4)

        clear_all_btn = QPushButton("Clear All")
        clear_all_btn.setStyleSheet(CLEAR_STYLE)
        clear_all_btn.setMaximumHeight(26)
        clear_all_btn.setMinimumHeight(26)
        clear_all_btn.clicked.connect(self.clear_all)

        cancel_point_btn = QPushButton("✕ Cancel Point")
        cancel_point_btn.setStyleSheet(CLEAR_STYLE)
        cancel_point_btn.setMaximumHeight(26)
        cancel_point_btn.setMinimumHeight(26)
        cancel_point_btn.clicked.connect(self._cancel_point)

        add_btn = QPushButton("▶  Add Record")
        add_btn.setStyleSheet(ADD_STYLE)
        add_btn.setMinimumHeight(26)
        add_btn.clicked.connect(self._add_record)

        bottom_row.addWidget(clear_all_btn)
        bottom_row.addWidget(cancel_point_btn)
        bottom_row.addStretch()
        bottom_row.addWidget(add_btn)
        layout.addLayout(bottom_row)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Capture mode
    # ------------------------------------------------------------------

    def _on_resume_clicked(self):
        self.gps_toggle_requested.emit(False)
        self.activate_tool_requested.emit()

    def _on_gps_clicked(self):
        self.gps_toggle_requested.emit(True)

    def confirm_mode(self, mode: str):
        self.capture_mode = mode
        self._refresh_mode_buttons()

    def set_map_click_armed(self, armed: bool):
        if self.capture_mode != "map_click":
            return
        if armed:
            self.resume_btn.setText("🖱 Map-click ON")
            self.resume_btn.setStyleSheet(TOOL_ACTIVE_STYLE)
        else:
            self.resume_btn.setText("⏸ Map-click OFF")
            self.resume_btn.setStyleSheet(TOOL_INACTIVE_STYLE)

    def _refresh_mode_buttons(self):
        if self.capture_mode == "gps":
            self.resume_btn.setText("🖱 Map-click")
            self.resume_btn.setStyleSheet(TOOL_INACTIVE_STYLE)
            self.gps_btn.setChecked(True)
            self.gps_btn.setText("📡 GPS: ON")
            self.gps_btn.setStyleSheet(TOOL_ACTIVE_STYLE)
        else:
            self.resume_btn.setText("🖱 Map-click ON")
            self.resume_btn.setStyleSheet(TOOL_ACTIVE_STYLE)
            self.gps_btn.setChecked(False)
            self.gps_btn.setText("📡 GPS: OFF")
            self.gps_btn.setStyleSheet(TOOL_INACTIVE_STYLE)

    # ------------------------------------------------------------------
    # Habitat selection
    # ------------------------------------------------------------------

    def _habitat_clicked(self, text, source_dict):
        for d in (self._sg_buttons, self._mn_buttons):
            for b in d.values():
                b.setStyleSheet(DEFAULT_STYLE)

        mapped_value = HABITAT_VALUE_MAP.get(text, text)

        if self.current_habitat == mapped_value:
            self.current_habitat = ""
            self.current_habitat_label = ""
        else:
            self.current_habitat = mapped_value
            self.current_habitat_label = text
            source_dict[text].setStyleSheet(ACTIVE_STYLE)

        self._update_status()

    def _clear_habitat(self):
        self.current_habitat = ""
        self.current_habitat_label = ""
        for d in (self._sg_buttons, self._mn_buttons):
            for b in d.values():
                b.setStyleSheet(DEFAULT_STYLE)
        self._update_status()

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    def _append_comment(self, text):
        cur = self.comments_edit.toPlainText().strip()
        self.comments_edit.setText((cur + " " + text).strip())

    # ------------------------------------------------------------------
    # Clear / Cancel
    # ------------------------------------------------------------------

    def clear_all(self):
        self.current_habitat = ""
        self.current_habitat_label = ""
        for d in (self._sg_buttons, self._mn_buttons):
            for b in d.values():
                b.setStyleSheet(DEFAULT_STYLE)
        self.comments_edit.clear()
        self._update_status()

    def _cancel_point(self):
        self.clear_all()
        self.longitude = None
        self.latitude = None
        self.lat_lbl.setText("Lat: —")
        self.lon_lbl.setText("Lon: —")
        self.cancel_point_requested.emit()

    def _update_status(self):
        self.status_lbl.setText(
            f"Habitat: {self.current_habitat}" if self.current_habitat else "No selection")

    # ------------------------------------------------------------------
    # Coordinates
    # ------------------------------------------------------------------

    def set_coordinates(self, lon, lat, source="GPS"):
        self.longitude = float(lon)
        self.latitude = float(lat)
        self.coord_source = source
        self.lat_lbl.setText(f"Lat: {self.latitude:.6f}")
        self.lon_lbl.setText(f"Lon: {self.longitude:.6f}")

    # ------------------------------------------------------------------
    # Save record
    # ------------------------------------------------------------------

    def _add_record(self):
        if not self.current_habitat:
            QMessageBox.warning(self, "Missing data", "Select a habitat type.")
            return
        if self.longitude is None:
            QMessageBox.warning(self, "No location",
                                "No location set — enable Live GPS or click "
                                "the map to set a location first.")
            return

        data = {
            'habitat':   self.current_habitat,
            'comments':  self.comments_edit.toPlainText(),
            'longitude': self.longitude,
            'latitude':  self.latitude,
            'timestamp': QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss"),
            'source':    self.coord_source,
        }
        self.record_requested.emit(data)

        self.status_lbl.setText("✔ Record saved!")
        self.status_lbl.setStyleSheet(
            "QLabel { background: #bbdefb; border: 1px solid #90caf9; "
            "border-radius: 3px; padding: 3px; font-size: 9pt; }")
        self.clear_all()
        QTimer.singleShot(2000, self._reset_status_style)

    def _reset_status_style(self):
        self.status_lbl.setStyleSheet(
            "QLabel { background: #e8f5e9; border: 1px solid #a5d6a7; "
            "border-radius: 3px; padding: 3px; font-size: 9pt; }")
        self.status_lbl.setText("No selection")
