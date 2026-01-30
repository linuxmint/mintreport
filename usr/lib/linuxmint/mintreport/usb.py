#!/usr/bin/python3
import gi
import pyudev
import subprocess
import threading
import xapp.threading as xt
import xapp.util
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango

_ = xapp.util.l10n("mintreport")

COL_NAME, COL_ID, COL_SPEED, COL_POWER, COL_SENSITIVE, COL_IS_CONTROLLER, COL_MA_VAL, COL_ICON_NAME, COL_VERSION, COL_POWER_ICON, COL_IS_BUS_POWERED, COL_IS_HUB = range(12)

def decode_power(device):
    mA_val = 0
    attr = "80"
    attr_val = 0x00
    try:
        with open(f"{device.sys_path}/bMaxPower") as f:
            mA_val = int(f.read().strip().lower().replace("ma", ""))
    except FileNotFoundError:
        pass
    try:
        with open(f"{device.sys_path}/bmAttributes") as f:
            attr = f.read().strip()
            attr_val = int(attr, 16) if attr.startswith("0x40") else int(attr)
    except Exception:
        attr_val = 0x80
    is_bus_powered = False if (attr_val & 0x40) else True
    return is_bus_powered, mA_val

def speed_label(speed_mbps):
    try:
        val = int(speed_mbps)
    except Exception:
        return speed_mbps
    if val >= 10000:
        return _("%d Gbps") % val
    else:
        return _("%d Mbps") % val

def usb_limit(version):
    try:
        ver = float(version)
    except Exception:
        ver = 2.0
    return 900 if ver >= 3.0 else 500

def get_device_icon(device, vid_str):
    icon_name = "xsi-drive-harddisk-usb-symbolic"

    if vid_str == "1d6b": # Controller
        return icon_name

    try:
        device_class = device.attributes.get("bDeviceClass").decode().lower()
        device_subclass = device.attributes.get("bDeviceSubClass").decode()
        device_protocol = device.attributes.get("bDeviceProtocol").decode()
        match (device_class, device_subclass):
            case ("09", _): # Hub
                icon_name = "xsi-drive-harddisk-usb-symbolic"
            case ("08", _): # Storage
                icon_name = "xsi-usb-stick-symbolic"
            case ("03", "01"):
                if device_protocol == "01": # Keyboard
                    icon_name = "xsi-input-keyboard-symbolic"
                elif device_protocol == "02": # Mouse
                    icon_name = "xsi-input-mouse-symbolic"
            case ("0e", _): # Camera
                icon_name = "xsi-camera-video-symbolic"
            case ("01", _): # Audio Interface
                icon_name = "xsi-audio-card-symbolic"
            case ("02", "06"): # Ethernet Adapter
                icon_name = "xsi-network-wired-symbolic"
            case ("e0", "01"): # Bluetooth
                icon_name = "xsi-bluetooth-symbolic"
            case ("e0", "02"): # Wi-Fi Adapter
                icon_name = "xsi-network-wireless-symbolic"
            case ("07", _): # Printer
                icon_name = "xsi-printer-symbolic"
            case ("06", _): # Scanner
                icon_name = "xsi-scanner-symbolic"
            case ("0b", _): # Smart Card Reader
                icon_name = "xsi-smartcard-symbolic"
            case ("0d", _): # Security Token
                icon_name = "xsi-smartcard-symbolic"
            case ("ef", _): # Phone / Composite
                icon_name = "xsi-phone-symbolic"
            case ("fe", _): # Firmware Loader
                pass
            case ("ff", _): # Custom Device"
                pass
            case _:
                # Fallback: check interfaces (for composite devices)
                for child in device.children:
                    if child.device_type == 'usb_interface':
                        ic = child.attributes.get('bInterfaceClass').decode().lower()
                        isc = child.attributes.get('bInterfaceSubClass').decode()
                        ip = child.attributes.get('bInterfaceProtocol').decode()
                        if (ic == "00" or isc == "00" or ip == "00"):
                            break
                        # HID boot devices
                        if ic == "03" and isc == "01" and ip == "01": # Keyboard
                            icon_name = "xsi-input-keyboard-symbolic"
                        elif ic == "03" and isc == "01" and ip == "02": # Mouse
                            icon_name = "xsi-input-mouse-symbolic"
                            break # priorize mouse over keyboard
                        elif ic == "0e": # Camera
                            icon_name = "xsi-camera-video-symbolic"
                            break
                        elif ic == "01": # Audio Interface
                            icon_name = "xsi-audio-card-symbolic"
                            break
                        elif ic == "08": # Storage
                            icon_name = "xsi-usb-stick-symbolic"
                            break
    except Exception as e:
        print("Could not find an icon for the device", str(e))

    return icon_name

class USBListWidget(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__()

        self.context = pyudev.Context()
        self.monitor = pyudev.Monitor.from_netlink(self.context)
        self.monitor.filter_by(subsystem="usb")

        self.treestore = Gtk.TreeStore(
            str, str, str, str, bool, bool, int, str, str, str, bool, bool
        )

        self.treeview = Gtk.TreeView(model=self.treestore)
        self.treeview.connect("row-activated", self.on_row_activated)
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

        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn(_("ID"), renderer, text=COL_ID)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        self.treeview.append_column(column)
        column.set_expand(False)

        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn(_("Speed"), renderer, text=COL_SPEED)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        self.treeview.append_column(column)
        column.set_expand(False)

        # Power column: symbolic icon + text
        icon_renderer = Gtk.CellRendererPixbuf()
        text_renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn(_("Power"))
        column.pack_start(icon_renderer, False)
        column.pack_start(text_renderer, True)
        column.add_attribute(icon_renderer, "icon-name", COL_POWER_ICON)
        column.add_attribute(text_renderer, "markup", COL_POWER)
        column.add_attribute(text_renderer, "sensitive", COL_SENSITIVE)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        self.treeview.append_column(column)
        column.set_expand(False)

        self.add(self.treeview)
        self.set_shadow_type(Gtk.ShadowType.IN)

    def load(self):
        self.load_usb_hierarchy()
        threading.Thread(target=self.monitor_usb_events, daemon=True).start()

    def monitor_usb_events(self):
        for _ in self.monitor:
            self.refresh_view()

    def refresh_view(self):
        self.load_usb_hierarchy()
        return False

    @xt.run_idle
    def update_tree(self, rows):
        self.treestore.clear()
        iters = {}
        for row in rows:
            (sysname, parent_name, name, device_id, speed, power_markup, \
            is_controller, mA_val, icon_name, ver_str, power_icon, is_bus_powered, is_hub) = row
            parent_iter = iters.get(parent_name)
            new_iter = self.treestore.append(parent_iter)
            self.treestore.set_value(new_iter, COL_NAME, name)
            self.treestore.set_value(new_iter, COL_ID, device_id)
            self.treestore.set_value(new_iter, COL_SPEED, speed)
            self.treestore.set_value(new_iter, COL_POWER, power_markup)
            self.treestore.set_value(new_iter, COL_SENSITIVE, True)
            self.treestore.set_value(new_iter, COL_IS_CONTROLLER, is_controller)
            self.treestore.set_value(new_iter, COL_MA_VAL, mA_val)
            self.treestore.set_value(new_iter, COL_ICON_NAME, icon_name)
            self.treestore.set_value(new_iter, COL_VERSION, ver_str)
            self.treestore.set_value(new_iter, COL_POWER_ICON, power_icon)
            self.treestore.set_value(new_iter, COL_IS_BUS_POWERED, is_bus_powered)
            self.treestore.set_value(new_iter, COL_IS_HUB, is_hub)
            iters[sysname] = new_iter
        self.evaluate_power_usage()
        root = self.treestore.get_iter_first()
        self.grey_out(root)
        self.treeview.expand_all()

    def load_usb_hierarchy(self):
        devices = {}
        for device in self.context.list_devices(subsystem="usb", DEVTYPE="usb_device"):
            sysname = device.sys_name
            parent = device.find_parent("usb", "usb_device")
            parent_name = None
            if parent is not None:
                parent_name = parent.sys_name
            devices[sysname] = (device, parent_name)

        rows = []

        for sysname, (device, parent_name) in devices.items():
            vid = device.attributes.get("idVendor")
            pid = device.attributes.get("idProduct")
            version = device.attributes.get("version")
            speed = device.attributes.get("speed")
            busnum = device.attributes.get("busnum")
            device_class = device.attributes.get("bDeviceClass")

            vid_str = vid.decode() if vid else ""
            pid_str = pid.decode() if pid else ""
            ver_str = version.decode() if version else ""
            bus_str = busnum.decode() if busnum else "?"
            speed_raw = speed.decode() if speed else ""
            device_class = device_class.decode() if device_class else ""

            speed_pretty = speed_label(speed_raw)
            is_bus_powered, mA_val = decode_power(device)
            icon_name = get_device_icon(device, vid_str)
            is_controller = (vid_str == "1d6b")
            is_hub = (device_class == "09")

            device_id = ""
            speed = ""
            power_markup = ""
            power_icon = ""

            if is_controller:
                name = _("USB %(version)s controller (Bus #%(number)s) – Max speed: %(speed)s") \
                        % {"version": ver_str, 'number': bus_str, 'speed': speed_pretty}
            else:
                vendor = (
                    device.get("ID_VENDOR_FROM_DATABASE")
                    or device.get("ID_VENDOR")
                    or ""
                )
                product = (
                    device.get("ID_MODEL_FROM_DATABASE")
                    or device.get("ID_MODEL")
                    or ""
                )
                name = f"{vendor} {product}".replace("_", " ")
                if vid_str and pid_str:
                    device_id = f"{vid_str}:{pid_str}"
                speed = f"{speed_pretty}"
                if is_bus_powered:
                    power_markup = _("%d mA") % mA_val
                    power_icon = ""
                else:
                    power_markup = _("%d mA") % 0
                    power_icon = ""

            rows.append([sysname, parent_name, name, device_id, speed, power_markup, is_controller, mA_val, icon_name, ver_str, power_icon, is_bus_powered, is_hub])
            self.update_tree(rows)

    # Gray out empty controllers
    def grey_out(self, iter_):
        while iter_:
            is_ctrl = self.treestore.get_value(iter_, COL_IS_CONTROLLER)
            has_child = self.treestore.iter_has_child(iter_)
            if is_ctrl and not has_child:
                self.treestore.set_value(iter_, COL_SENSITIVE, False)
            self.grey_out(self.treestore.iter_children(iter_))
            iter_ = self.treestore.iter_next(iter_)

    # --- Power budget computation ---
    def evaluate_power_usage(self):
        def sum_children(iter_):
            total = 0
            while iter_:
                power_text = self.treestore.get_value(iter_, COL_POWER)
                mA_val = self.treestore.get_value(iter_, COL_MA_VAL)
                is_bus_powered = self.treestore.get_value(iter_, COL_IS_BUS_POWERED)
                is_ctrl = self.treestore.get_value(iter_, COL_IS_CONTROLLER)
                is_hub = self.treestore.get_value(iter_, COL_IS_HUB)
                if is_bus_powered:
                    total += mA_val
                    if is_ctrl or is_hub:
                        total += sum_children(self.treestore.iter_children(iter_))
                elif is_ctrl or is_hub:
                    pass
                else:
                    total += sum_children(self.treestore.iter_children(iter_))
                iter_ = self.treestore.iter_next(iter_)
            return total

        def update_power(iter_):
            while iter_:
                is_ctrl = self.treestore.get_value(iter_, COL_IS_CONTROLLER)
                is_hub = self.treestore.get_value(iter_, COL_IS_HUB)
                if is_ctrl:
                    ver_str = self.treestore.get_value(iter_, COL_VERSION) or "2.00"
                    limit_per_port = usb_limit(ver_str)
                    total_draw = int(sum_children(self.treestore.iter_children(iter_)))
                    max_allowed = limit_per_port * 4
                    percent_draw = int(float(total_draw) / float(max_allowed) * 100.0)
                    value_str = f"{percent_draw}% ({total_draw}/{max_allowed})"
                    text = _("%s mA max") % value_str
                    if total_draw > max_allowed:
                        icon = "dialog-warning-symbolic"
                    else:
                        icon = ""
                    self.treestore.set_value(iter_, COL_POWER, text)
                    self.treestore.set_value(iter_, COL_POWER_ICON, icon)
                update_power(self.treestore.iter_children(iter_))
                iter_ = self.treestore.iter_next(iter_)
        root = self.treestore.get_iter_first()
        update_power(root)

    def on_row_activated(self, treeview, path, column):
        model = treeview.get_model()
        iter_ = model.get_iter(path)
        device_id = model.get_value(iter_, COL_ID)
        if device_id and device_id.strip():
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(device_id, -1)
            subprocess.Popen(['notify-send', '-i', 'xsi-dialog-information-symbolic', _("Device ID copied"), _("The ID of the device was copied into your clipboard.")])

if __name__ == "__main__":
    win = Gtk.Window()
    win.set_default_size(1100, 620)
    win.set_border_width(10)
    widget = USBListWidget()
    win.add(widget)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    widget.load()
    Gtk.main()
