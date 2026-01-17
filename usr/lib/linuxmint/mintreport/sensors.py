import os
import gi
import xapp.util

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango

_ = xapp.util.l10n("mintreport")

SYS_HWMON = "/sys/class/hwmon"

COL_NAME, COL_VALUE, COL_UNIT, COL_SENSITIVE, COL_ICON_NAME = range(5)

def format_sensor(filename, raw):
    raw = raw.strip()

    if filename.startswith("temp"):
        return f"{int(raw)/1000:.1f}", _("°C"), "xsi-temperature-symbolic"

    if filename.startswith("fan"):
        return raw, _("RPM"), "xsi-cog-symbolic"

    if filename.startswith("pwm"):
        return f"{int(raw)*100/255:.0f}", _("%"), "xsi-cog-symbolic"

    if filename.startswith("in"):
        return f"{int(raw)/1000:.3f}", _("V"), "xsi-cog-symbolic"

    if filename.startswith("curr"):
        return f"{int(raw)/1000:.3f}", _("A"), "xsi-cog-symbolic"

    if filename.startswith("power"):
        return f"{int(raw)/1_000_000:.1f}", _("W"), "xsi-cog-symbolic"

    if filename.startswith("freq"):
        return f"{int(raw)/1_000_000_000:.3f}", _("GHz"), "xsi-cog-symbolic"

    if filename.startswith("energy"):
        return f"{int(raw)/1_000_000:.3f}", _("J"), "xsi-cog-symbolic"

    return raw, "", "xsi-cpu-symbolic"

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

    def load(self):
        self.build_tree()
        self.refresh_values()
        GLib.timeout_add_seconds(1, self.refresh_values)

    def build_tree(self):
        self.treestore.clear()
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

            device_without_sensors = True;

            # Process all *_input files in base_path
            for fname in sorted(os.listdir(base_path)):
                if not fname.endswith("_input"):
                    continue

                fpath = os.path.join(base_path, fname)
                raw = self._read_file(fpath)
                if raw is None:
                    continue

                value, unit, icon_name = format_sensor(fname, raw)

                # Label
                label_file = fpath.replace("_input", "_label")
                label = self._read_file(label_file)
                label = label.strip() if label else fname.replace("_input", "")

                itr = self.treestore.append(
                    parent,
                    [label, value, unit,  True, icon_name],
                )
                self.sensor_rows[fpath] = itr

                device_without_sensors = False;

            if (device_without_sensors):
                self.treestore.set_value(parent, COL_SENSITIVE, False)

        self.treeview.expand_all()

    def refresh_values(self):
        for fpath, itr in self.sensor_rows.items():
            raw = self._read_file(fpath)
            if raw is None:
                continue

            fname = os.path.basename(fpath)
            value, _, _ = format_sensor(fname, raw)
            self.treestore.set_value(itr, COL_VALUE, value)

        return True

    def _read_file(self, path):
        try:
            with open(path, "r") as f:
                return f.read()
        except Exception:
            return None
