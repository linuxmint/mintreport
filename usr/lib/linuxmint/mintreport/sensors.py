import os
import gi
import xapp.util
import xapp.SettingsWidgets as Xs
import re
from enum import IntEnum

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

_ = xapp.util.l10n("mintreport")

SYS_HWMON = "/sys/class/hwmon"

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
        "pattern":re.compile(r"^(temp\d+)_input$"),
        "format":lambda raw: f"{int(raw)/1000:.1f}",
        "unit":"°C",
        "icon":"xsi-temperature-symbolic"
    },
    SensorType.FAN: {
        "pattern":re.compile(r"^(fan\d+)_input$"),
        "format":lambda raw: raw.strip(),
        "unit":_("RPM"),
        "icon":"xsi-fan-symbolic"
    },
    SensorType.PWM: {
        "pattern":re.compile(r"^(pwm\d+)$"), # no _input suffix for pwm type
        "format":lambda raw: f"{int(raw)*100/255:.0f}",
        "unit":"%",
        "icon":"xsi-fan-symbolic"
    },
    SensorType.FREQ: {
        "pattern":re.compile(r"^(freq\d+)_input$"),
        "format":lambda raw: f"{int(raw)/1_000_000_000:.2f}",
        "unit":"GHz",
        "icon":"xsi-physics-wavelength-symbolic"
    },
    SensorType.VOLTAGE: {
        "pattern":re.compile(r"^(in\d+)_input$"),
        "format":lambda raw: f"{int(raw)/1000:.2f}",
        "unit":"V",
        "icon":"xsi-physics-volts-symbolic"
    },
    SensorType.CURRENT: {
        "pattern":re.compile(r"^(curr\d+)_input$"),
        "format":lambda raw: f"{int(raw)/1000:.2f}",
        "unit":"A",
        "icon":"xsi-physics-amps-symbolic"
    },
    SensorType.POWER: {
        "pattern":re.compile(r"^(power\d+)_input$"),
        "format":lambda raw: f"{int(raw)/1_000_000:.1f}",
        "unit":"W",
        "icon":"xsi-physics-watts-symbolic"
    },
    SensorType.ENERGY: {
        "pattern":re.compile(r"^(energy\d+)_input$"),
        "format":lambda raw: f"{int(raw)/1_000_000:.1f}",
        "unit":"J",
        "icon":"xsi-power-symbolic"
    }
}

def sensor_spec_from_filename(filename):
    for stype, spec in SENSOR_SPECS.items():
        m = spec["pattern"].match(filename)
        if m:
            base = m.group(1)
            return stype, spec, base
    return None, None, None

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
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.page = Xs.SettingsPage()
        self.page.set_spacing(24)
        self.page.set_margin_left(24)
        self.page.set_margin_right(24)
        self.page.set_margin_top(12)
        self.page.set_margin_bottom(12)
        self.add(self.page)

        self.sensor_rows = {}  # fpath -> (value_label, stype)
        self.value_size_group = Gtk.SizeGroup(Gtk.SizeGroupMode.HORIZONTAL)
        self.unit_size_group = Gtk.SizeGroup(Gtk.SizeGroupMode.HORIZONTAL)

        self.timeout_id = None
        self.refresh_interval = 1 # seconds

        self.connect("map", self._on_map)
        self.connect("unmap", self._on_unmap)

    def load(self):
        # do nothing, we do everything in the _on_map() function
        pass

    def _on_map(self, *_):
        if self.timeout_id is None:
            # Refresh existing cards or build them if they don't exist yet
            if self.sensor_rows:
                self.refresh_values()
            else:
                self.build_cards()

            self.timeout_id = GLib.timeout_add_seconds(
                self.refresh_interval, self.refresh_values
            )

    def _on_unmap(self, *_):
        if self.timeout_id is not None:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = None

    def build_cards(self):
        for child in self.page.get_children():
            self.page.remove(child)
        self.sensor_rows.clear()

        if not os.path.isdir(SYS_HWMON):
            return

        # First pass: collect all chips with their sensors
        chips = []
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

            # Process all sensor files in base_path
            sensors = []
            for fname in os.listdir(base_path):
                stype, spec, base_name = sensor_spec_from_filename(fname)
                if spec is None:
                    continue    # that's not a sensor

                fpath = os.path.join(base_path, fname)
                raw = self._read_file(fpath)
                if raw is None:
                    continue    # unable to read sensor -> skip

                # Label
                labelpath = os.path.join(base_path, f"{base_name}_label")
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

            if not sensors:
                continue

            sort_sensors(sensors)
            chips.append((hwmon, name, sensors))

        # Disambiguate chips that share the same name (e.g. two RAM sticks: spd5118)
        name_counts = {}
        for _, name, _ in chips:
            name_counts[name] = name_counts.get(name, 0) + 1

        # Second pass: build cards
        for hwmon, name, sensors in chips:
            if name_counts[name] > 1:
                name = f"{name} ({hwmon})"

            section = self.page.add_section(name)

            for s in sensors:
                row = Xs.SettingsWidget()
                row.set_spacing(8)

                icon = Gtk.Image.new_from_icon_name(s["icon"], Gtk.IconSize.MENU)
                icon.set_pixel_size(16)
                row.pack_start(icon, False, False, 0)

                name_label = Gtk.Label(label=s["label"])
                name_label.set_xalign(0)
                row.pack_start(name_label, True, True, 0)

                value_label = Gtk.Label(label=s["value"])
                value_label.get_style_context().add_class("dim-label")
                value_label.set_xalign(1.0)
                unit_label = Gtk.Label(label=s["unit"])
                unit_label.get_style_context().add_class("dim-label")
                unit_label.set_xalign(0.0)
                self.value_size_group.add_widget(value_label)
                self.unit_size_group.add_widget(unit_label)
                row.pack_end(unit_label, False, False, 0)
                row.pack_end(value_label, False, False, 0)

                section.add_row(row)
                self.sensor_rows[s["path"]] = (value_label, s["type"])

        self.page.show_all()

    def refresh_values(self):
        for fpath, (value_label, stype) in self.sensor_rows.items():
            raw = self._read_file(fpath)
            if raw is None:
                continue

            spec = SENSOR_SPECS[stype]
            value = spec["format"](raw)

            if value != value_label.get_text():
                value_label.set_text(value)

        return True

    def _read_file(self, path):
        try:
            with open(path, "r") as f:
                return f.read()
        except Exception:
            return None
