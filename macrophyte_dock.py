"""
Dock panel for macrophyte field data collection.
Single Habitat selection (Seagrass OR Mangrove/Saltmarsh) + free-text Comments.

Capture mode toggle: Live GPS (primary) and Map-click (fallback) are
mutually exclusive — selecting one always disables the other.

Button labels are short for tappability; the value actually recorded
in the Habitat field is looked up from HABITAT_VALUE_MAP and can be
more descriptive.
"""

from qgis.PyQt.QtCore import pyqtSignal, QDateTime, QTimer
from qgis.PyQt.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                  QGridLayout, QPushButton, QLabel,
                                  QTextEdit, QGroupBox, QMessageBox,
                                  QScrollArea, QFrame)

ACTIVE_STYLE  = "QPushButton { background-color: #2e7d32; color: white; font-weight: bold; border: 1px solid #1b5e20; border-radius: 3px; }"
DEFAULT_STYLE = "QPushButton { background-color: #f0f0f0; border: 1px solid #aaa; border-radius: 3px; } QPushButton:hover { background-color: #dde; }"
ADD_STYLE     = "QPushButton { background-color: #1565C0; color: white; font-weight: bold; border-radius: 4px; padding: 4px; }"
CLEAR_STYLE   = "QPushButton { background-color: #c62828; color: white; border-radius: 4px; padding: 4px; }"

# Colour-blind-safe pair (blue vs amber) for mode status, each also
# carries a distinct icon + label text so state is never colour-dependent.
TOOL_ACTIVE_STYLE = (
    "QPushButton { background-color: #1565C0; color: white; font-weight: bold; "
    "border: 2px solid #0d47a1; border-radius: 4px; padding: 6px; }"
)
TOOL_INACTIVE_STYLE = (
    "QPushButton { background-color: #f5a623; color: #3a2a00; font-weight: bold; "
    "border: 2px solid #c8800a; border-radius: 4px; padding: 6px; }"
)

# Maps the short button label (what's displayed on the button) to the
# full value that actually gets recorded in the Habitat field and shown
# in the status panel. Buttons not listed here record their label text
# unchanged. Edit this freely — button layout/logic doesn't need to change.
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
        self.current_habitat = ""          # full recorded value (saved to layer)
        self.current_habitat_label = ""    # short button label (which button is active)
        self.longitude = None
        self.latitude  = None
        self.coord_source = "GPS"
        self.capture_mode = "map_click"   # "map_click" or "gps" — single source of truth
        self._sg_buttons = {}
        self._mn_buttons = {}
        self._init_ui()

    # ------------------------------------------------------------------
    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(6)
        scroll.setWidget(container)
        outer.addWidget(scroll)

        # ── Capture mode buttons (mutually exclusive) ───────────────
        self.resume_btn = QPushButton()
        self.resume_btn.setMinimumHeight(40)
        self.resume_btn.clicked.connect(self._on_resume_clicked)
        layout.addWidget(self.resume_btn)

        coord_box = QGroupBox("GPS Location")
        coord_lay = QVBoxLayout()

        self.gps_btn = QPushButton()
        self.gps_btn.setCheckable(True)
        self.gps_btn.setMinimumHeight(36)
        self.gps_btn.clicked.connect(self._on_gps_clicked)
        coord_lay.addWidget(self.gps_btn)

        coord_row = QHBoxLayout()
        self.lat_lbl = QLabel("Lat: —")
        self.lon_lbl = QLabel("Lon: —")
        coord_row.addWidget(self.lat_lbl)
        coord_row.addWidget(self.lon_lbl)
        coord_lay.addLayout(coord_row)

        hint_lbl = QLabel("GPS is primary. Use map click only for locations "
                          "you can't physically reach.")
        hint_lbl.setWordWrap(True)
        hint_lbl.setStyleSheet("color: #777; font-size: 8.5pt;")
        coord_lay.addWidget(hint_lbl)

        coord_box.setLayout(coord_lay)
        layout.addWidget(coord_box)

        self._refresh_mode_buttons()  # initialise both buttons' appearance

        # ── Seagrass ─────────────────────────────────────────────────
        sg_box = QGroupBox("Seagrass")
        sg_grid = QGridLayout()
        sg_grid.setSpacing(3)
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
                btn.setMaximumHeight(32)
                btn.setMinimumHeight(22)
                btn.clicked.connect(
                    lambda checked, t=text: self._habitat_clicked(t, self._sg_buttons))
                sg_grid.addWidget(btn, r, c)
                self._sg_buttons[text] = btn

        mapped_btn = QPushButton("As mapped")
        mapped_btn.setStyleSheet(DEFAULT_STYLE)
        mapped_btn.setMaximumHeight(32)
        mapped_btn.setMinimumHeight(22)
        mapped_btn.clicked.connect(
            lambda: self._habitat_clicked("As mapped", self._sg_buttons))
        self._sg_buttons["As mapped"] = mapped_btn

        sg_clear = QPushButton("Clear")
        sg_clear.setStyleSheet(CLEAR_STYLE)
        sg_clear.setMaximumHeight(32)
        sg_clear.setMinimumHeight(22)
        sg_clear.clicked.connect(self._clear_habitat)

        sg_grid.addWidget(mapped_btn, 4, 0, 1, 2)
        sg_grid.addWidget(sg_clear,   4, 2, 1, 2)
        sg_box.setLayout(sg_grid)
        layout.addWidget(sg_box)

        # ── Mangrove / Saltmarsh ─────────────────────────────────────
        mn_box = QGroupBox("Mangrove / Saltmarsh")
        mn_grid = QGridLayout()
        mn_grid.setSpacing(3)
        mangrove_rows = [
            ["Single Tree",   "Small group",  "Avicennia",   "Aegiceras"],
            ["Scattered",     "No mangroves", "Rhizophora",  "Exoecaria"],
            ["Fringing",      "Man/SM",       "Bruguiera",   ""],
            ["Widespread",    "Saltmarsh",    "No Saltmarsh",""],
        ]
        for r, row in enumerate(mangrove_rows):
            for c, text in enumerate(row):
                if not text:
                    continue
                btn = QPushButton(text)
                btn.setStyleSheet(DEFAULT_STYLE)
                btn.setMaximumHeight(32)
                btn.setMinimumHeight(22)
                btn.clicked.connect(
                    lambda checked, t=text: self._habitat_clicked(t, self._mn_buttons))
                mn_grid.addWidget(btn, r, c)
                self._mn_buttons[text] = btn

        mn_box.setLayout(mn_grid)
        layout.addWidget(mn_box)

        # ── Comments ─────────────────────────────────────────────────
        cmt_box = QGroupBox("Comments")
        cmt_lay = QVBoxLayout()
        cmt_lay.setSpacing(3)

        self.comments_edit = QTextEdit()
        self.comments_edit.setMaximumHeight(70)
        self.comments_edit.setPlaceholderText("Type comments or use buttons below…")
        cmt_lay.addWidget(self.comments_edit)

        for word_row in [
            ["Posidonia", "Zostera",  "Halophila", "Ruppia",  "Caulerpa"],
            ["Wrack",     "Algae",    "Rock",      "Sand",    "and"],
            ["Dense",     "Medium",   "Sparse",    "with",    "Clear"],
        ]:
            row_lay = QHBoxLayout()
            row_lay.setSpacing(3)
            for w in word_row:
                btn = QPushButton(w)
                btn.setMaximumHeight(32)
                btn.setMinimumHeight(22)
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

        # ── Status / selection summary ──────────────────────────────
        self.status_lbl = QLabel("No selection")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setStyleSheet(
            "QLabel { background: #e8f5e9; border: 1px solid #a5d6a7; "
            "border-radius: 3px; padding: 4px; }")
        layout.addWidget(self.status_lbl)

        # ── Bottom buttons ───────────────────────────────────────────
        btn_row = QHBoxLayout()
        clear_all_btn = QPushButton("Clear All")
        clear_all_btn.setStyleSheet(CLEAR_STYLE)
        clear_all_btn.setMaximumHeight(32)
        clear_all_btn.setMinimumHeight(22)
        clear_all_btn.clicked.connect(self.clear_all)

        cancel_point_btn = QPushButton("✕ Cancel Point")
        cancel_point_btn.setStyleSheet(CLEAR_STYLE)
        cancel_point_btn.setMaximumHeight(32)
        cancel_point_btn.setMinimumHeight(22)
        cancel_point_btn.clicked.connect(self._cancel_point)

        add_btn = QPushButton("▶  Add Record")
        add_btn.setStyleSheet(ADD_STYLE)
        add_btn.setMinimumHeight(36)
        add_btn.clicked.connect(self._add_record)

        btn_row.addWidget(clear_all_btn)
        btn_row.addWidget(cancel_point_btn)
        btn_row.addStretch()
        btn_row.addWidget(add_btn)
        layout.addLayout(btn_row)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Capture mode (mutually exclusive: map_click <-> gps)
    # ------------------------------------------------------------------

    def _on_resume_clicked(self):
        """User explicitly wants map-click mode."""
        self.gps_toggle_requested.emit(False)
        self.activate_tool_requested.emit()

    def _on_gps_clicked(self):
        """User explicitly wants GPS mode."""
        self.gps_toggle_requested.emit(True)

    def confirm_mode(self, mode: str):
        """Called by the plugin once a mode switch has genuinely taken
        effect (GPS connected, or map tool armed)."""
        self.capture_mode = mode
        self._refresh_mode_buttons()

    def set_map_click_armed(self, armed: bool):
        """Within map-click mode, reflect whether the map-click tool is
        currently QGIS's active tool (vs. user having switched to
        Pan/Zoom via QGIS's own toolbar). Does not change capture_mode."""
        if self.capture_mode != "map_click":
            return
        if armed:
            self.resume_btn.setText("🖱  Map-click active — click map to set point")
            self.resume_btn.setStyleSheet(TOOL_ACTIVE_STYLE)
        else:
            self.resume_btn.setText("⏸  Map-click paused — click here to resume")
            self.resume_btn.setStyleSheet(TOOL_INACTIVE_STYLE)

    def _refresh_mode_buttons(self):
        """Redraw both mode buttons to reflect self.capture_mode."""
        if self.capture_mode == "gps":
            self.resume_btn.setText("🖱  Switch to Map-click")
            self.resume_btn.setStyleSheet(TOOL_INACTIVE_STYLE)
            self.gps_btn.setChecked(True)
            self.gps_btn.setText("📡 Live GPS: ON — tracking position")
            self.gps_btn.setStyleSheet(TOOL_ACTIVE_STYLE)
        else:
            self.resume_btn.setText("🖱  Map-click active — click map to set point")
            self.resume_btn.setStyleSheet(TOOL_ACTIVE_STYLE)
            self.gps_btn.setChecked(False)
            self.gps_btn.setText("📡 Switch to Live GPS")
            self.gps_btn.setStyleSheet(TOOL_INACTIVE_STYLE)

    # ------------------------------------------------------------------
    # Habitat selection (Seagrass + Mangrove/Saltmarsh share one value)
    # ------------------------------------------------------------------

    def _habitat_clicked(self, text, source_dict):
        for d in (self._sg_buttons, self._mn_buttons):
            for b in d.values():
                b.setStyleSheet(DEFAULT_STYLE)

        # text is the button's short label and dict key. The value
        # actually recorded/displayed is looked up from HABITAT_VALUE_MAP.
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
        """Clear attribute selections only — keeps marker/coordinates intact."""
        self.current_habitat = ""
        self.current_habitat_label = ""
        for d in (self._sg_buttons, self._mn_buttons):
            for b in d.values():
                b.setStyleSheet(DEFAULT_STYLE)
        self.comments_edit.clear()
        self._update_status()

    def _cancel_point(self):
        """Abandon this point entirely — clears attributes AND the marker/coords.
        Does NOT change capture_mode — GPS keeps tracking if it was on."""
        self.clear_all()
        self.longitude = None
        self.latitude  = None
        self.lat_lbl.setText("Lat: —")
        self.lon_lbl.setText("Lon: —")
        self.cancel_point_requested.emit()

    def _update_status(self):
        """Show the FULL descriptive habitat value in the status panel,
        not the short button label."""
        self.status_lbl.setText(
            f"Habitat: {self.current_habitat}" if self.current_habitat else "No selection")

    # ------------------------------------------------------------------
    # Coordinates (called from plugin — GPS feed or map click)
    # ------------------------------------------------------------------

    def set_coordinates(self, lon, lat, source="GPS"):
        self.longitude = float(lon)
        self.latitude  = float(lat)
        self.coord_source = source
        self.lat_lbl.setText(f"Lat: {self.latitude:.6f}")
        self.lon_lbl.setText(f"Lon: {self.longitude:.6f}")

    # ------------------------------------------------------------------
    # Save record
    # ------------------------------------------------------------------

    def _add_record(self):
        if not self.current_habitat:
            QMessageBox.warning(self, "Missing data",
                                "Select a habitat type.")
            return
        if self.longitude is None:
            QMessageBox.warning(self, "No location",
                                "No location set — enable Live GPS or click "
                                "the map to set a location first.")
            return

        data = {
            'habitat':   self.current_habitat,   # full mapped value
            'comments':  self.comments_edit.toPlainText(),
            'longitude': self.longitude,
            'latitude':  self.latitude,
            'timestamp': QDateTime.currentDateTime().toString(
                             "yyyy-MM-dd HH:mm:ss"),
            'source':    self.coord_source,
        }
        self.record_requested.emit(data)

        self.status_lbl.setText("✔ Record saved!")
        self.status_lbl.setStyleSheet(
            "QLabel { background: #bbdefb; border: 1px solid #90caf9; "
            "border-radius: 3px; padding: 4px; }")
        self.clear_all()
        QTimer.singleShot(2000, self._reset_status_style)

    def _reset_status_style(self):
        self.status_lbl.setStyleSheet(
            "QLabel { background: #e8f5e9; border: 1px solid #a5d6a7; "
            "border-radius: 3px; padding: 4px; }")
        self.status_lbl.setText("No selection")