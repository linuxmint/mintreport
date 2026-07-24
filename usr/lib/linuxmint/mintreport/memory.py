#!/usr/bin/python3
import gi
import re
import subprocess
import xapp.SettingsWidgets as Xs
import xapp.threading as xt
import xapp.util
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

_ = xapp.util.l10n("mintreport")


def get_memory_info():
    try:
        meminfo = subprocess.check_output("LANG=C inxi -mxxxc0", shell=True).decode("utf-8", errors='replace')
        meminfo_parsed = parse_memory_output(meminfo)
        return meminfo_parsed
    except Exception as e:
        subprocess.Popen(['notify-send', '-i', 'xsi-dialog-error-symbolic', _("An error occurred while gathering the system information."), str(e)])
        print (e)

def parse_system_ram(ram_text):
    # Extract total, available, and used memory.
    pattern = r'System RAM: total: (.+?) available: (.+?) used: (.+)'
    match = re.search(pattern, ram_text)

    if not match:
        return None

    return {
        'total': match.group(1),
        'available': match.group(2),
        'used': match.group(3)
    }

def parse_array_info(array_text):
    # Extract capacity, slots, modules, max module size, and error correction type.
    try:
        array_match = re.search(r'Array-\d+: capacity: (.+?) slots: (.+?) modules: (\d+) EC: (\S+)', array_text)
        if not array_match:
            return None

        capacity = array_match.group(1)
        slots = int(array_match.group(2))
        modules = int(array_match.group(3))
        ec = array_match.group(4)

        max_size_match = re.search(r'max-module-size: (.+? \S+)', array_text)
        max_module_size = max_size_match.group(1)
        if not max_size_match:
            return None

        return {
            'capacity': capacity,
            'slots': slots,
            'modules': modules,
            'max_module_size': max_module_size,
            'ec': ec
        }
    except Exception as e:
        print(f"Error parsing memory array info: {e}")
        return None

def parse_device_info(device_text):
    # Extract hardware details for a single memory device.
    device_data = {}

    device_match = re.search(r'(Device-\d+): Channel-.+? type:', device_text)
    if device_match:
        device_data['device'] = device_match.group(1)

    channel_match = re.search(r'Device-\d+: (Channel-.+?) type:', device_text)
    if channel_match:
        device_data['channel'] = channel_match.group(1)

    type_match = re.search(r'type: (.+?) detail:', device_text)
    if type_match:
        device_data['type'] = type_match.group(1)

    details_match = re.search(r'detail: ([^\n]+)\s*( \([^)]+\)) size:', device_text)
    if details_match:
        device_data['details'] = details_match.group(1) + details_match.group(2)

    size_match = re.search(r'size: ([\d.]+ [A-Z]+iB)', device_text)
    if size_match:
        device_data['size'] = size_match.group(1)

    speed_match = re.search(r'speed: (\d+ [A-Z]+/s)', device_text)
    if speed_match:
        device_data['speed'] = speed_match.group(1)

    volts_match = re.search(r'volts: ([\d.]+)', device_text)
    if volts_match:
        device_data['volts'] = volts_match.group(1)

    width_data_match = re.search(r'data: (\d+)', device_text)
    if width_data_match:
        device_data['width_data'] = width_data_match.group(1) + " bits"

    width_total_match = re.search(r'total: (\d+)', device_text)
    if width_total_match:
        device_data['width_total'] = width_total_match.group(1) + " bits"

    manufacturer_match = re.search(r'manufacturer: ([^\n]+?)(?: part-no| serial|$)', device_text)
    if manufacturer_match:
        device_data['manufacturer'] = manufacturer_match.group(1).strip()

    part_no_match = re.search(r'part-no: ([^\n]+)', device_text)
    if part_no_match:
        device_data['part_no'] = part_no_match.group(1).strip()

    serial_match = re.search(r'serial: ([^\n]+)', device_text)
    if serial_match:
        device_data['serial'] = serial_match.group(1).strip()

    return device_data

def parse_memory_output(inxi_output):
    #Parse inxi memory output into system_ram, array, and devices.
    result = {
        'system_ram': None,
        'array': None,
        'devices': []
    }

    ram_match = re.search(r'System RAM: .+?\n(?!  [A-Z])', inxi_output, re.DOTALL)
    if ram_match:
        result['system_ram'] = parse_system_ram(ram_match.group(0))

    array_match = re.search(r'Array-\d+: .+?(?=\n  Device|\Z)', inxi_output, re.DOTALL)
    if array_match:
        result['array'] = parse_array_info(array_match.group(0))

    device_matches = re.finditer(r'Device-\d+: .+?(?=\n  Device|\Z)', inxi_output, re.DOTALL)
    for match in device_matches:
        device_info = parse_device_info(match.group(0))
        if device_info:
            result['devices'].append(device_info)

    return result

class MemoryListWidget(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.page = Xs.SettingsPage()
        self.page.set_spacing(24)
        self.page.set_margin_left(0)
        self.page.set_margin_right(0)
        self.page.set_margin_top(0)
        self.page.set_margin_bottom(0)
        self.add(self.page)

        self.section_system_ram = self.page.add_section(_("System RAM"))
        self.section_memory_array = self.page.add_section(_("Memory array"))

    @xt.run_async
    def load(self):
        memory_dict = get_memory_info()
        system_ram_dict = memory_dict['system_ram']
        memory_array_dict = memory_dict['array']
        devices_dict = memory_dict['devices']
        info_system_ram = []
        info_system_ram.append([_('Total'), system_ram_dict['total']])
        info_system_ram.append([_('Available'), system_ram_dict['available']])
        info_system_ram.append([_('Used'), system_ram_dict['used']])
        info_memory_array= []
        info_memory_array.append([_('Capacity'), memory_array_dict['capacity']])
        info_memory_array.append([_('Number of slots'), str(memory_array_dict['slots'])])
        info_memory_array.append([_('Number of modules'), str(memory_array_dict['modules'])])
        info_memory_array.append([_('Maximum module size'), str(memory_array_dict['max_module_size'])])
        info_memory_array.append([_('Error Correction'), memory_array_dict['ec']])

        # Process devices — one section per device
        for device in devices_dict:
            info_memory_devices= []
            info_memory_devices.append([_('Channel'), device['channel']])
            info_memory_devices.append([_('Type'), device['type']])
            info_memory_devices.append([_('Details'), device['details']])
            info_memory_devices.append([_('Size'), device['size']])
            info_memory_devices.append([_('Speed'), device['speed']])
            info_memory_devices.append([_('Volts'), device['volts']])
            info_memory_devices.append([_('Data width'), device['width_data']])
            info_memory_devices.append([_('Total width'), device['width_total']])
            info_memory_devices.append([_('Manufacturer'), device['manufacturer']])
            info_memory_devices.append([_('Part number'), device['part_no']])
            info_memory_devices.append([_('Serial number'), device['serial']])
            section = self.page.add_section(device['device'])
            self.update_ui(info_memory_devices, section)
        self.update_ui(info_system_ram, self.section_system_ram)
        self.update_ui(info_memory_array, self.section_memory_array)


    @xt.run_idle
    def update_ui(self, info, section):
        for (key, value) in info:
            widget = Xs.SettingsWidget()
            widget.set_spacing(40)
            labelKey = Gtk.Label.new(key)
            widget.pack_start(labelKey, False, False, 0)
            labelKey.get_style_context().add_class("dim-label")
            labelValue = Gtk.Label.new(value)
            labelValue.set_selectable(True)
            labelValue.set_line_wrap(True)
            widget.pack_end(labelValue, False, False, 0)
            section.add_row(widget)
        self.page.show_all()

# -------------------------------------------------------------------
# Standalone test window
# -------------------------------------------------------------------

if __name__ == "__main__":
    win = Gtk.Window(title="Memory")
    viewer = MemoryListWidget()
    viewer.load()
    win.add(viewer)
    win.set_default_size(800, 400)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()

