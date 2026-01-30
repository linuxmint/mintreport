import os
import gi
import xapp.util
import re
from enum import IntEnum

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango

_ = xapp.util.l10n("mintreport")

SYS_HWMON = "/sys/class/hwmon"

COL_NAME, COL_VALUE, COL_UNIT, COL_SENSITIVE, COL_ICON_NAME = range(5)

class SensorType(IntEnum):
    TEMP = 0
    FAN = 1
    PWM = 2
    FREQ = 3
    POWER = 4
    VOLTAGE = 5
    CURRENT = 6
    ENERGY = 7


SENSOR_SPECS = {
    SensorType.TEMP: {
        "prefix":"temp",
        "suffix":"_input",
        "format":lambda raw: f"{int(raw)/1000:.1f}",
        "unit":"°C",
        "icon":"xsi-temperature-symbolic"
    },
    SensorType.FAN: {
        "prefix":"fan",
        "suffix":"_input",
        "format":lambda raw: raw.strip(),
        "unit":_("RPM"),
        "icon":"xsi-cog-symbolic"
    },
    SensorType.PWM: {
        "prefix":"pwm",
        "suffix":"", # no _input suffix for pwm
        "format":lambda raw: f"{int(raw)*100/255:.0f}",
        "unit":"%",
        "icon":"xsi-cog-symbolic"
    },
    SensorType.FREQ: {
        "prefix":"freq",
        "suffix":"_input",
        "format":lambda raw: f"{int(raw)/1_000_000_000:.3f}",
        "unit":"GHz",
        "icon":"xsi-cog-symbolic"
    },
    SensorType.VOLTAGE: {
        "prefix":"in",
        "suffix":"_input",
        "format":lambda raw: f"{int(raw)/1000:.3f}",
        "unit":"V",
        "icon":"xsi-cog-symbolic"
    },
    SensorType.CURRENT: {
        "prefix":"curr",
        "suffix":"_input",
        "format":lambda raw: f"{int(raw)/1000:.3f}",
        "unit":"A",
        "icon":"xsi-cog-symbolic"
    },
    SensorType.POWER: {
        "prefix":"power",
        "suffix":"_input",
        "format":lambda raw: f"{int(raw)/1_000_000:.1f}",
        "unit":"W",
        "icon":"xsi-cog-symbolic"
    },
    SensorType.ENERGY: {
        "prefix":"energy",
        "suffix":"_input",
        "format":lambda raw: f"{int(raw)/1_000_000:.3f}",
        "unit":"J",
        "icon":"xsi-cog-symbolic"
    }
}

def sensor_spec_from_filename(filename):
    for stype, spec in SENSOR_SPECS.items():
        prefix = spec["prefix"]
        suffix = spec["suffix"]
        if filename.startswith(prefix) and filename.endswith(suffix):
            return stype, spec
    return None, None

# Helper funcs to sort sensors in correct numerical order (ex in10 after in9)
def natural_key(label):
    # Split around any digit sequence
    parts = re.split(r'(\d+)', label)
    key = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part.lower())
    return key

def sort_sensors(sensors):
    # Natural sort within each sensor type
    sensors.sort(key=lambda s: natural_key(s["label"]))
    # Group by sensor type
    sensors.sort(key=lambda s: s["type"])

class SensorsListWidget(Gtk.ScrolledWindow):

    def __init__(self):
        super().__init__()

        self.treestore = Gtk.TreeStore(str, str, str, bool, str)

        self.treeview = Gtk.TreeView(model=self.treestore)
        self.treeview.set_enable_tree_lines(True)
        self.treeview.set_property("expand", True)
        self.treeview.set_headers_clickable(True)

        # --- Columns ---
        # Name column with device icon
        icon_renderer = Gtk.CellRendererPixbuf()
        icon_renderer.set_property("xpad", 2)
        icon_renderer.set_property("ypad", 2)
        text_renderer = Gtk.CellRendererText()
        text_renderer.set_property("ypad", 6)
        column = Gtk.TreeViewColumn(_("Name"))
        column.pack_start(icon_renderer, False)
        column.pack_start(text_renderer, True)
        column.add_attribute(icon_renderer, "icon-name", COL_ICON_NAME)
        column.add_attribute(text_renderer, "text", COL_NAME)
        column.add_attribute(text_renderer, "sensitive", COL_SENSITIVE)
        text_renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        self.treeview.append_column(column)
        column.set_expand(True)
        column.set_resizable(True)

        # Value column
        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn(_("Value"), renderer, text=COL_VALUE)
        column.set_expand(False)
        self.treeview.append_column(column)

        # Unit column
        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn(_("Unit"), renderer, text=COL_UNIT)
        column.set_expand(False)
        self.treeview.append_column(column)

        self.add(self.treeview)
        self.set_shadow_type(Gtk.ShadowType.IN)

        self.sensor_rows = {}

        self.timeout_id = None
        self.refresh_interval = 1 # seconds

        self.connect("map", self._on_map)
        self.connect("unmap", self._on_unmap)

    def load(self):
        # do nothing, we do everything in the _on_map() function
        pass

    def _on_map(self, *arg):
        if self.timeout_id is None:
            # Refresh existing tree or build it is does not exist yet
            if self.sensor_rows:
                self.refresh_values()
            else:
                self.build_tree()

            self.timeout_id = GLib.timeout_add_seconds(
                self.refresh_interval, self.refresh_values
            )

    def _on_unmap(self, *arg):
        if self.timeout_id is not None:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = None

    def build_tree(self):
        self.treestore.clear()
        self.sensor_rows.clear()

        if not os.path.isdir(SYS_HWMON):
            return

        # sort hwmon folders by natural order, as the listdir order is random
        for hwmon in sorted(os.listdir(SYS_HWMON), key=natural_key):
            hwmon_path = os.path.join(SYS_HWMON, hwmon)
            device_path = os.path.join(hwmon_path, "device")

            # Determine base path for sensors
            base_path = None
            if os.path.isdir(device_path):
                # Use device/ only if it contains *_input files
                # This is required as some modules put sensors files in the device folder (apple-smc for example)
                inputs = [f for f in os.listdir(device_path) if f.endswith("_input")]
                if inputs:
                    base_path = device_path
            if base_path is None:
                base_path = hwmon_path

            # Root name
            name_file = os.path.join(base_path, "name")
            name = self._read_file(name_file)
            name = name.strip() if name else hwmon

            parent = self.treestore.append(
                None, [name, "", "", True, "xsi-cpu-symbolic"]
            )

            device_without_sensors = True

            # Process all *_input files in base_path
            sensors = []
            for fname in os.listdir(base_path):
                stype, spec = sensor_spec_from_filename(fname)
                if spec is None:
                    continue    # that's not a sensor

                fpath = os.path.join(base_path, fname)
                raw = self._read_file(fpath)
                if raw is None:
                    continue    # unable to read sensor -> skip

                # Label
                labelname = fname.replace(spec["suffix"], "_label")
                labelpath = os.path.join(base_path, labelname)
                label = self._read_file(labelpath)
                label = label.strip() if label else fname.replace("_input", "")

                sensors.append({
                    "label": label,
                    "path": fpath,
                    "value": spec["format"](raw),
                    "unit": spec["unit"],
                    "icon": spec["icon"],
                    "type": stype,
                })

            sort_sensors(sensors)

            # Add sorted sensors to treestore
            for s in sensors:
                itr = self.treestore.append(
                    parent,
                    [s["label"], s["value"], s["unit"],  True, s["icon"]],
                )

                # Store TreeStore itr and sensor type by path for refresh
                self.sensor_rows[s["path"]] = (itr, s["type"])
                device_without_sensors = False

            if device_without_sensors:
                self.treestore.set_value(parent, COL_SENSITIVE, False)

        self.treeview.expand_all()

    def refresh_values(self):
        self.treestore.freeze_notify()

        for fpath, (itr, stype) in self.sensor_rows.items():
            raw = self._read_file(fpath)
            if raw is None:
                continue

            spec = SENSOR_SPECS[stype]
            value = spec["format"](raw)

            if value != self.treestore.get_value(itr, COL_VALUE):
                self.treestore.set_value(itr, COL_VALUE, value)

        self.treestore.thaw_notify()
        return True

    def _read_file(self, path):
        try:
            with open(path, "r") as f:
                return f.read()
        except Exception:
            return None
