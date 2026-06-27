# QGIS Macrophyte Validator

A QGIS dock panel plugin for field validation of estuarine macrophyte habitats — seagrass, mangrove, and saltmarsh. Replicates the button-based data collection interface previously used in ArcMap, with live GPS support and persistent GeoPackage storage.

Developed for coastal habitat mapping in NSW estuaries.

---

## Features

- Dockable panel that stays visible while mapping
- Single habitat selection across Seagrass and Mangrove/Saltmarsh button groups
- Live GPS capture (primary) and map-click capture (fallback for inaccessible locations)
- Mutually exclusive GPS/map-click mode toggle with colour-blind-safe status indicators
- GPS signal status indicator (fix/no fix)
- Free-text comments with quick-insert word buttons (species, density, substrate)
- Habitat values recorded using full descriptive terms via a lookup dictionary
- Points saved immediately to a GeoPackage alongside the QGIS project file
- Layer persists across sessions — reloads automatically on subsequent field days
- Auto-labelling of points as `habitat comments` (e.g. `Posidonia Dense patch`)
- Pending point marker on the map canvas before committing a record
- Cancel Point clears the pending marker without interrupting GPS tracking
- Cursor restores to default pan tool when the panel is closed

---

## Requirements

- QGIS 3.x (tested on 3.40 LTS)
- Python 3.x (bundled with QGIS)
- A GPS device connected via the QGIS GPS Panel for live GPS mode

---

## Installation

### Method 1 — Install from ZIP

1. Download or clone this repository
2. Zip the folder contents so the zip contains these files at the root:
   - init.py
   - macrophyte_plugin.py
   - macrophyte_dock.py
   - metadata.txt
   - icon.png
3. In QGIS: **Plugins → Manage and Install Plugins → Install from ZIP**
4. Browse to the zip file and click **Install Plugin**
5. Enable the plugin in **Installed** tab

### Method 2 — Manual installation

Copy the plugin folder directly to your QGIS plugins directory:

- **Windows:** `C:\Users\<username>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\macrophyte_data\`
- **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/macrophyte_data/`
- **macOS:** `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/macrophyte_data/`

Restart QGIS and enable the plugin under **Plugins → Manage and Install Plugins → Installed**.

---

## Usage

### Setup

1. Save your QGIS project file — the plugin stores data in a GeoPackage (`Macrophyte_Data.gpkg`) created alongside the `.qgz` project file
2. For live GPS: connect your GPS device via **View → Panels → GPS Information** first
3. Click the **Macrophyte Data Collection** toolbar button to open the panel

### Capture modes

| Mode          | When to use                                                                                |
| ------------- | ------------------------------------------------------------------------------------------ |
| **Live GPS**  | Primary mode — records your current physical location. Panel lat/lon updates every second. |
| **Map-click** | Fallback for locations you can't physically reach — click the map to place a point.        |

Switching between modes is mutually exclusive — enabling one automatically disables the other.

### Recording a point

1. Enable Live GPS or click the map to set a location
2. Select a habitat type from the **Seagrass** or **Mangrove/Saltmarsh** buttons
3. Optionally add comments using the text box or quick-insert buttons
4. Click **▶ Add Record** to save the point
5. The pending marker disappears and the form clears, ready for the next point

### Buttons

| Button                       | Action                                                                                                |
| ---------------------------- | ----------------------------------------------------------------------------------------------------- |
| **Clear** (seagrass section) | Clears habitat selection only                                                                         |
| **Clear All**                | Clears habitat and comments, keeps the current location marker                                        |
| **✕ Cancel Point**           | Abandons the current point — clears everything including the location marker. GPS tracking continues. |
| **▶ Add Record**             | Saves the point to the GeoPackage layer                                                               |

---

## Data

Points are saved to `Macrophyte_Data.gpkg` in the same folder as the QGIS project file.

| Field     | Type    | Content                                            |
| --------- | ------- | -------------------------------------------------- |
| id        | Integer | Auto-incrementing record ID                        |
| habitat   | String  | Full habitat description (e.g. `Sparse Posidonia`) |
| comments  | String  | Free text and quick-insert terms                   |
| longitude | Double  | WGS84 longitude                                    |
| latitude  | Double  | WGS84 latitude                                     |
| timestamp | String  | Date and time of record (yyyy-MM-dd HH:mm:ss)      |
| source    | String  | `GPS` or `Manual`                                  |

The layer is auto-labelled with `habitat` + `comments` and reloads automatically when the project is reopened on subsequent field days.

---

## Habitat lookup

Button labels are kept short for field use. The full descriptive value recorded in the `habitat` field is defined in `HABITAT_VALUE_MAP` in `macrophyte_dock.py`. Edit this dictionary to customise habitat terminology without changing the button layout.

---

## Development

Built with PyQGIS and PyQt5. Tested on QGIS 3.40 LTS on Windows.

For development, open the repo folder in VSCode. Use the **Plugin Reloader** plugin in QGIS to reload changes without restarting QGIS.

Contributions and issues welcome via GitHub.

---

## Licence

MIT License — free to use, modify, and distribute.