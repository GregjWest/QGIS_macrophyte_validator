"""
Estuarine Habitat Validation Plugin for QGIS
Dock panel version — stays visible while mapping.

Capture mode is mutually exclusive: either Live GPS (primary) or
Map-click (fallback for locations you can't physically reach).

Data is stored in a GeoPackage saved alongside the project file, so
records persist across sessions (e.g. multiple field days on the
same estuary project).
"""

import os
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.core import (QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
                       QgsPointXY, QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform, QgsApplication,
                       QgsVectorFileWriter, QgsWkbTypes, QgsFields,
                       QgsField, QgsPalLayerSettings, QgsTextFormat,
                       QgsVectorLayerSimpleLabeling)
from qgis.gui import QgsMapToolEmitPoint, QgsDockWidget, QgsVertexMarker

from .macrophyte_dock import MacrophyteDockWidget

LAYER_NAME = "Validation_Data"
GPKG_FILENAME = "Validation_Data.gpkg"


class MacrophyteDataPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = u'&Estuarine Habitat Validation'
        self.dock = None
        self.dock_widget = None
        self.point_tool = None
        self.marker = None
        self.gps_connection = None

    # ------------------------------------------------------------------
    # Setup / teardown
    # ------------------------------------------------------------------

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        action = QAction(QIcon(icon_path),
                         u'Estuarine Habitat Validation',
                         self.iface.mainWindow())
        action.triggered.connect(self.toggle_panel)
        self.iface.addToolBarIcon(action)
        self.iface.addPluginToMenu(self.menu, action)
        self.actions.append(action)

        # Build dock
        self.dock_widget = MacrophyteDockWidget()
        self.dock = QgsDockWidget("Estuarine Habitat Validation",
                                  self.iface.mainWindow())
        self.dock.setObjectName("MacrophyteDataDock")
        self.dock.setWidget(self.dock_widget)
        self.dock.setAllowedAreas(Qt.LeftDockWidgetArea |
                                  Qt.RightDockWidgetArea)
        self.iface.mainWindow().addDockWidget(Qt.RightDockWidgetArea,
                                              self.dock)

        # Wire signals
        self.dock_widget.record_requested.connect(self.save_record)
        self.dock_widget.activate_tool_requested.connect(
            self._activate_point_tool)
        self.dock_widget.cancel_point_requested.connect(
            self._clear_pending_marker)
        self.dock_widget.gps_toggle_requested.connect(
            self._toggle_gps_tracking)

        # Map tool (manual click fallback)
        self.point_tool = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.point_tool.canvasClicked.connect(self._canvas_clicked)

        # Track external tool switches (e.g. user clicks Pan on QGIS toolbar)
        self.iface.mapCanvas().mapToolSet.connect(self._on_maptool_changed)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        try:
            self.iface.mapCanvas().mapToolSet.disconnect(
                self._on_maptool_changed)
        except TypeError:
            pass
        self._disconnect_gps()
        self._clear_pending_marker()
        if self.dock:
            self.iface.mainWindow().removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None

    # ------------------------------------------------------------------
    # Panel visibility
    # ------------------------------------------------------------------

    def toggle_panel(self):
        if self.dock.isVisible():
            self.dock.hide()
            if self.iface.mapCanvas().mapTool() == self.point_tool:
                self.iface.mapCanvas().unsetMapTool(self.point_tool)
        else:
            self.dock.show()
            # Default to Live GPS if a connection already exists; else map-click
            registry = QgsApplication.gpsConnectionRegistry()
            if registry.connectionList():
                self._toggle_gps_tracking(True)
            else:
                self._activate_point_tool()

    # ------------------------------------------------------------------
    # Capture mode: Map-click
    # ------------------------------------------------------------------

    def _activate_point_tool(self):
        """User wants map-click mode — disable GPS first, then arm the tool."""
        self._disconnect_gps()
        self.iface.mapCanvas().setMapTool(self.point_tool)
        self.dock_widget.confirm_mode("map_click")

    def _on_maptool_changed(self, new_tool, old_tool):
        """If the user switches to Pan/Zoom/etc. via QGIS's own toolbar
        while in map-click mode, show the resume button as paused —
        but only if we're not in GPS mode."""
        if self.dock_widget and self.gps_connection is None:
            is_armed = (new_tool == self.point_tool)
            self.dock_widget.set_map_click_armed(is_armed)

    def _canvas_clicked(self, point, button):
        # Show marker immediately at the clicked location (canvas CRS)
        self._show_pending_marker(point)

        # Convert to WGS84 for storage
        canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        wgs84 = QgsCoordinateReferenceSystem('EPSG:4326')
        if canvas_crs != wgs84:
            xform = QgsCoordinateTransform(canvas_crs, wgs84,
                                           QgsProject.instance())
            wgs84_point = xform.transform(point)
        else:
            wgs84_point = point

        self.dock_widget.set_coordinates(wgs84_point.x(), wgs84_point.y(),
                                         source="Manual")

    # ------------------------------------------------------------------
    # Capture mode: Live GPS
    # ------------------------------------------------------------------

    def _toggle_gps_tracking(self, enabled: bool):
        if not enabled:
            self._disconnect_gps()
            return

        registry = QgsApplication.gpsConnectionRegistry()
        connections = registry.connectionList()
        if not connections:
            QMessageBox.warning(
                self.iface.mainWindow(), "No GPS connected",
                "No active GPS connection found.\n\n"
                "Open the GPS Panel (View → Panels → GPS Information), "
                "connect your device there first, then enable Live GPS here.")
            self.dock_widget.confirm_mode("map_click")
            return

        # Switch off map-click tool while GPS drives the position
        if self.iface.mapCanvas().mapTool() == self.point_tool:
            self.iface.mapCanvas().unsetMapTool(self.point_tool)

        self._disconnect_gps()  # clean up any stale connection first
        self.gps_connection = connections[0]
        self.gps_connection.positionChanged.connect(self._on_gps_position)
        self.dock_widget.confirm_mode("gps")

    def _disconnect_gps(self):
        """Safely disconnect from the current GPS connection, if still alive."""
        if self.gps_connection is None:
            return
        try:
            self.gps_connection.positionChanged.disconnect(
                self._on_gps_position)
        except (RuntimeError, TypeError):
            pass
        finally:
            self.gps_connection = None

    def _on_gps_position(self, point):
        """Fired automatically whenever a new valid GPS fix comes in."""
        lat = point.y()
        lon = point.x()
        if lat is None or lon is None:
            return

        self.dock_widget.set_coordinates(lon, lat, source="GPS")

        canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        wgs84 = QgsCoordinateReferenceSystem('EPSG:4326')
        canvas_point = QgsPointXY(lon, lat)
        if canvas_crs != wgs84:
            xform = QgsCoordinateTransform(wgs84, canvas_crs,
                                           QgsProject.instance())
            canvas_point = xform.transform(canvas_point)
        self._show_pending_marker(canvas_point)

    # ------------------------------------------------------------------
    # Pending point marker
    # ------------------------------------------------------------------

    def _show_pending_marker(self, canvas_point):
        """Show/move a marker at the given location (must be in canvas CRS)."""
        if self.marker is None:
            self.marker = QgsVertexMarker(self.iface.mapCanvas())
            self.marker.setIconType(QgsVertexMarker.ICON_CROSS)
            self.marker.setColor(Qt.red)
            self.marker.setIconSize(14)
            self.marker.setPenWidth(3)
        self.marker.setCenter(canvas_point)
        self.marker.show()

    def _clear_pending_marker(self):
        if self.marker:
            self.iface.mapCanvas().scene().removeItem(self.marker)
            self.marker = None

    # ------------------------------------------------------------------
    # Layer management — persistent GeoPackage alongside the project file
    # ------------------------------------------------------------------

    def _get_or_create_layer(self):
        layers = QgsProject.instance().mapLayersByName(LAYER_NAME)
        if layers:
            return layers[0]

        project_path = QgsProject.instance().fileName()
        if not project_path:
            QMessageBox.warning(
                self.iface.mainWindow(), "Project not saved",
                "Please save your QGIS project first, so the macrophyte "
                "GeoPackage can be stored alongside it.")
            return None

        project_dir = os.path.dirname(project_path)
        gpkg_path = os.path.join(project_dir, GPKG_FILENAME)

        if os.path.exists(gpkg_path):
            uri = f"{gpkg_path}|layername={LAYER_NAME}"
            layer = QgsVectorLayer(uri, LAYER_NAME, "ogr")
            if layer.isValid():
                QgsProject.instance().addMapLayer(layer)
                return layer
            else:
                QMessageBox.warning(
                    self.iface.mainWindow(), "Layer load failed",
                    f"Found {GPKG_FILENAME} but couldn't load the "
                    f"'{LAYER_NAME}' layer from it. Check the file isn't "
                    "corrupted or locked by another program.")
                return None

        return self._create_new_gpkg_layer(gpkg_path)

    def _create_new_gpkg_layer(self, gpkg_path):
        fields = QgsFields()
        fields.append(QgsField("id", QVariant.Int))
        fields.append(QgsField("habitat", QVariant.String, len=50))
        fields.append(QgsField("comments", QVariant.String, len=255))
        fields.append(QgsField("longitude", QVariant.Double))
        fields.append(QgsField("latitude", QVariant.Double))
        fields.append(QgsField("timestamp", QVariant.String, len=30))
        fields.append(QgsField("source", QVariant.String, len=10))

        save_options = QgsVectorFileWriter.SaveVectorOptions()
        save_options.driverName = "GPKG"
        save_options.fileEncoding = "UTF-8"

        writer = QgsVectorFileWriter.create(
            gpkg_path,
            fields,
            QgsWkbTypes.Point,
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance().transformContext(),
            save_options
        )

        if writer.hasError() != QgsVectorFileWriter.NoError:
            QMessageBox.critical(
                self.iface.mainWindow(), "GeoPackage creation failed",
                f"Could not create {GPKG_FILENAME}:\n{writer.errorMessage()}")
            return None

        del writer

        uri = f"{gpkg_path}|layername={LAYER_NAME}"
        layer = QgsVectorLayer(uri, LAYER_NAME, "ogr")
        if not layer.isValid():
            QMessageBox.critical(
                self.iface.mainWindow(), "Layer load failed",
                f"Created {GPKG_FILENAME} but the layer failed to load.")
            return None

        self._apply_labelling(layer)
        QgsProject.instance().addMapLayer(layer)
        return layer

    def _apply_labelling(self, layer):
        """Label features as 'habitat comments', trimming cleanly when
        comments is empty."""
        settings = QgsPalLayerSettings()
        settings.fieldName = (
            "CASE WHEN \"comments\" IS NULL OR \"comments\" = '' "
            "THEN \"habitat\" "
            "ELSE \"habitat\" || ' ' || \"comments\" END"
        )
        settings.isExpression = True

        text_format = QgsTextFormat()
        text_format.setSize(9)
        settings.setFormat(text_format)

        labeling = QgsVectorLayerSimpleLabeling(settings)
        layer.setLabeling(labeling)
        layer.setLabelsEnabled(True)
        layer.triggerRepaint()

    # ------------------------------------------------------------------
    # Save record
    # ------------------------------------------------------------------

    def save_record(self, data: dict):
        layer = self._get_or_create_layer()
        if not layer:
            return False

        try:
            lon = float(data.get('longitude', 0.0))
            lat = float(data.get('latitude', 0.0))
        except (TypeError, ValueError):
            QMessageBox.critical(
                self.iface.mainWindow(), "Invalid coordinates",
                "Could not save record — longitude/latitude were not "
                "valid numbers.")
            return False

        existing_ids = []
        for f in layer.getFeatures():
            val = f['id']
            if val is not None:
                existing_ids.append(int(val))
        next_id = max(existing_ids, default=0) + 1

        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        feat.setAttribute('id', int(next_id))
        feat.setAttribute('habitat', str(data.get('habitat', '')))
        feat.setAttribute('comments', str(data.get('comments', '')))
        feat.setAttribute('longitude', lon)
        feat.setAttribute('latitude', lat)
        feat.setAttribute('timestamp', str(data.get('timestamp', '')))
        feat.setAttribute('source', str(data.get('source', '')))

        success, added = layer.dataProvider().addFeatures([feat])
        if not success:
            QMessageBox.critical(
                self.iface.mainWindow(), "Save failed",
                f"Failed to add feature to layer.\n"
                f"Provider errors: {layer.dataProvider().errors()}")
            return False

        layer.updateExtents()
        layer.triggerRepaint()
        self.iface.mapCanvas().refresh()
        self._clear_pending_marker()
        return True
