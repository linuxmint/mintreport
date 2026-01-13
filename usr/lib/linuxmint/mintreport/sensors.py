import os
import gi
import xapp.util

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango

_ = xapp.util.l10n("mintreport")

SYS_HWMON = "/sys/class/hwmon"

(
    COL_NAME,
    COL_VALUE,
    COL_UNIT,
    COL_SENSITIVE,
    COL_ICON,
) = range(5)


class SensorsListWidget(Gtk.ScrolledWindow):
    ICONS = {
        "root": "xsi-cpu-symbolic",
        "temp": "xsi-temperature-symbolic",
        "fan": "xsi-cpu-symbolic",
        "in": "xsi-cpu-symbolic",
        "power": "xsi-cpu-symbolic",
        "other": "xsi-cpu-symbolic",
    }

    def __init__(self):
        super().__init__()

        # TreeStore with icon, name, value, unit
        self.treestore = Gtk.TreeStore(str, str, str, bool, str)
        self.treeview = Gtk.TreeView(model=self.treestore)
        self.treeview.set_enable_tree_lines(True)
        self.treeview.set_headers_clickable(True)

        # First column: tree + icon + name
        renderer = Gtk.CellRendererPixbuf()
        column = Gtk.TreeViewColumn("", renderer, icon_name=COL_ICON)
        column.set_expand(False)
        self.treeview.append_column(column)

        renderer = Gtk.CellRendererText()
        renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        column = Gtk.TreeViewColumn(_("Sensor"), renderer, text=COL_NAME)
        column.set_expand(True)
        self.treeview.append_column(column)

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

        self.hwmon_parents = {}
        self.sensor_rows = {}

    # ------------------------------------------------------------------
    def load(self):
        self.build_tree()
        self.refresh_values()
        GLib.timeout_add_seconds(1, self.refresh_values)

    # ------------------------------------------------------------------
    def build_tree(self):
        self.treestore.clear()
        self.hwmon_parents.clear()
        self.sensor_rows.clear()

        if not os.path.isdir(SYS_HWMON):
            return

        for hwmon in sorted(os.listdir(SYS_HWMON)):
            hwmon_path = os.path.join(SYS_HWMON, hwmon)
            device_path = os.path.join(hwmon_path, "device")

            # Determine base path for sensors
            base_path = None
            if os.path.isdir(device_path):
                # Use device/ only if it contains *_input files
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
                None, [name, "", "", False, self.ICONS["root"]]
            )
            self.hwmon_parents[hwmon_path] = parent

            # Process all *_input files in base_path
            for fname in sorted(os.listdir(base_path)):
                if not fname.endswith("_input"):
                    continue

                fpath = os.path.join(base_path, fname)
                raw = self._read_file(fpath)
                if raw is None:
                    continue

                # Label
                label_file = fpath.replace("_input", "_label")
                label = self._read_file(label_file)
                label = label.strip() if label else fname.replace("_input", "")

                unit, display, stype = self.format_sensor(fname, raw)

                itr = self.treestore.append(
                    parent,
                    [label, display, unit, True, self.ICONS.get(stype, self.ICONS["other"])],
                )
                self.sensor_rows[fpath] = itr

        self.treeview.expand_all()

    # ------------------------------------------------------------------
    def refresh_values(self):
        for fpath, itr in self.sensor_rows.items():
            raw = self._read_file(fpath)
            if raw is None:
                continue

            fname = os.path.basename(fpath)
            _, display, _ = self.format_sensor(fname, raw)
            self.treestore.set_value(itr, COL_VALUE, display)

        return True

    # ------------------------------------------------------------------
    def format_sensor(self, filename, raw):
        raw = raw.strip()
        stype = "other"

        if filename.startswith("temp"):
            stype = "temp"
            return "°C", f"{int(raw)/1000:.1f}", stype

        if filename.startswith("fan"):
            stype = "fan"
            return "RPM", raw, stype

        if filename.startswith("in"):
            stype = "in"
            return "V", f"{int(raw)/1000:.3f}", stype

        if filename.startswith("power"):
            stype = "power"
            return "W", f"{int(raw)/1_000_000:.2f}", stype

        return "", raw, stype

    # ------------------------------------------------------------------
    def _read_file(self, path):
        try:
            with open(path, "r") as f:
                return f.read()
        except Exception:
            return None
