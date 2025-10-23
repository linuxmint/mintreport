#!/usr/bin/python3
import gi
gi.require_version("Gtk", "3.0")
from common import clean_brand
from gi.repository import Gtk, Gdk, Pango
import pyudev
import subprocess
import xapp.threading as xt
import xapp.util

_ = xapp.util.l10n("mintreport")

COL_FULL, COL_ICON, COL_ACTIVE, COL_BUS, COL_TYPE, COL_VENDOR, COL_NAME, COL_ID, COL_DRIVER = range(9)

PCI_CLASS_MAP = {
    # 00h — Unclassified
    (0x00, 0x00): "Non-VGA unclassified device",
    (0x00, 0x01): "VGA compatible unclassified device",

    # 01h — Mass storage
    (0x01, 0x00): "SCSI storage",
    (0x01, 0x01): "IDE interface",
    (0x01, 0x02): "Floppy disk",
    (0x01, 0x03): "IPI bus",
    (0x01, 0x04): "RAID bus",
    (0x01, 0x05): "ATA",
    (0x01, 0x06): "SATA",
    (0x01, 0x07): "Serial Attached SCSI",
    (0x01, 0x08): "NVME",
    (0x01, 0x80): "Mass storage",

    # 02h — Network
    (0x02, 0x00): "Ethernet",
    (0x02, 0x01): "Token ring network",
    (0x02, 0x02): "FDDI network",
    (0x02, 0x03): "ATM network",
    (0x02, 0x04): "ISDN",
    (0x02, 0x80): "Network",

    # 03h — Display
    (0x03, 0x00): "VGA compatible",
    (0x03, 0x01): "XGA compatible",
    (0x03, 0x02): "3D",
    (0x03, 0x80): "Display",

    # 04h — Multimedia
    (0x04, 0x00): "Multimedia video",
    (0x04, 0x01): "Multimedia audio",
    (0x04, 0x02): "Computer telephony device",
    (0x04, 0x03): "Audio device",
    (0x04, 0x80): "Multimedia",

    # 05h — Memory
    (0x05, 0x00): "RAM",
    (0x05, 0x01): "Flash",
    (0x05, 0x80): "Memory",

    # 06h — Bridge device
    (0x06, 0x00): "Host bridge",
    (0x06, 0x01): "ISA bridge",
    (0x06, 0x02): "EISA bridge",
    (0x06, 0x03): "MicroChannel bridge",
    (0x06, 0x04): "PCI bridge",
    (0x06, 0x05): "PCMCIA bridge",
    (0x06, 0x06): "NuBus bridge",
    (0x06, 0x07): "CardBus bridge",
    (0x06, 0x08): "RACEway bridge",
    (0x06, 0x09): "PCI-to-PCI bridge",
    (0x06, 0x0A): "InfiniBand to PCI host bridge",
    (0x06, 0x80): "Bridge device",

    # 07h — Simple communication
    (0x07, 0x00): "Serial",
    (0x07, 0x01): "Parallel",
    (0x07, 0x02): "Multiport serial",
    (0x07, 0x03): "Modem",
    (0x07, 0x80): "Communication",

    # 08h — Base system peripheral
    (0x08, 0x00): "PIC",
    (0x08, 0x01): "DMA",
    (0x08, 0x02): "Timer",
    (0x08, 0x03): "RTC",
    (0x08, 0x04): "PCI hot-plug",
    (0x08, 0x05): "SD Host",
    (0x08, 0x06): "IOMMU",
    (0x08, 0x80): "System peripheral",

    # 09h — Input device
    (0x09, 0x00): "Keyboard",
    (0x09, 0x01): "Digitizer",
    (0x09, 0x02): "Mouse",
    (0x09, 0x03): "Scanner",
    (0x09, 0x04): "Gameport",
    (0x09, 0x80): "Input device",

    # 0Ah — Docking station
    (0x0A, 0x00): "Docking station",
    (0x0A, 0x80): "Docking station",

    # 0Bh — Processor
    (0x0B, 0x00): "386",
    (0x0B, 0x01): "486",
    (0x0B, 0x02): "Pentium",
    (0x0B, 0x03): "Pentium Pro",
    (0x0B, 0x10): "Alpha",
    (0x0B, 0x20): "PowerPC",
    (0x0B, 0x30): "MIPS",
    (0x0B, 0x40): "Co-processor",
    (0x0B, 0x80): "Processor",

    # 0Ch — Serial bus
    (0x0C, 0x00): "FireWire (IEEE 1394)",
    (0x0C, 0x01): "ACCESS bus",
    (0x0C, 0x02): "SSA",
    (0x0C, 0x03): "USB",
    (0x0C, 0x04): "Fibre Channel",
    (0x0C, 0x05): "SMBus",
    (0x0C, 0x06): "InfiniBand",
    (0x0C, 0x07): "IPMI",
    (0x0C, 0x08): "SERCOS",
    (0x0C, 0x09): "CANbus",
    (0x0C, 0x80): "Serial bus",

    # 0Dh — Wireless
    (0x0D, 0x00): "iRDA",
    (0x0D, 0x01): "Consumer IR",
    (0x0D, 0x10): "RF",
    (0x0D, 0x11): "Bluetooth",
    (0x0D, 0x12): "Broadband",
    (0x0D, 0x20): "Ethernet (802.11a/b/g)",
    (0x0D, 0x80): "Wireless",

    # 0Eh — Intelligent I/O
    (0x0E, 0x00): "I2O",

    # 0Fh — Satellite communication
    (0x0F, 0x01): "Satellite TV",
    (0x0F, 0x02): "Satellite audio",
    (0x0F, 0x03): "Satellite voice",
    (0x0F, 0x04): "Satellite data",

    # 10h — Encryption / decryption
    (0x10, 0x00): "Network and computing encr/decr",
    (0x10, 0x10): "Entertainment encr/decr",
    (0x10, 0x80): "Encryption",

    # 11h — Data acquisition / signal processing
    (0x11, 0x00): "DPIO module",
    (0x11, 0x01): "Performance counters",
    (0x11, 0x10): "Communication synchronizer",
    (0x11, 0x20): "Signal processing management",
    (0x11, 0x80): "Data acquisition",
}

def get_icon_for_device(info):
    """Return an XApp symbolic icon name for a PCI class string."""
    dev_class = info['class'].lower()
    dev_name = info['device'].lower()

    if "vga" in dev_class or "display" in dev_class or "gpu" in dev_class:
        return "xapp-display-symbolic"
    if "network" in dev_class and ("wifi" in dev_name or "wireless" in dev_name):
        return "xapp-network-wireless-symbolic"
    if "network" in dev_class or "ethernet" in dev_class:
        return "xapp-network-wired-symbolic"
    if "nvme" in dev_class or " nvme " in dev_name:
        return "xapp-drive-harddisk-solidstate-symbolic"
    if "storage" in dev_class or "sata" in dev_class or "ahci" in dev_class:
        return "xapp-drive-harddisk-symbolic"
    if "audio" in dev_class or "sound" in dev_class:
        return "xapp-audio-card-symbolic"
    if "serial" in dev_class and " usb " in dev_name:
        return "xapp-usb-symbolic"
    if "multimedia" in dev_class:
        return "xapp-audio-card-symbolic"
    if "thermal" in dev_name:
        return "xapp-temperature-symbolic"
    return "xapp-cpu-symbolic"


def get_pci_devices():
    """Collect PCI device information using pyudev."""
    context = pyudev.Context()
    devices = []

    def decode(v): return v.decode().strip() if hasattr(v, "decode") else v

    for dev in context.list_devices(subsystem="pci"):
        try:
            vendor_id = dev.attributes.asstring("vendor")[2:]
            device_id = dev.attributes.asstring("device")[2:]
        except Exception:
            vendor_id = device_id = None

        active = False
        power = dev.attributes.get("power/runtime_status")
        power = decode(power)
        if power == "active":
            active = True
        revision = dev.attributes.get("revision")
        revision = decode(revision)
        if revision.startswith("0x"):
            revision = revision[2:].lower()
        else:
            revision = f"{int(revision):02x}"
        if revision == "00":
            revision = ""
        else:
            revision = f"(rev {revision})"

        raw_class = dev.attributes.get("class")
        class_name = None

        if raw_class:
            val = int(raw_class.decode().strip(), 16)
            base, sub = (val >> 16) & 0xFF, (val >> 8) & 0xFF
            class_name = PCI_CLASS_MAP.get((base, sub))

        info = {
            "address": dev.sys_name,
            "vendor": dev.get("ID_VENDOR_FROM_DATABASE") or "",
            "device": dev.get("ID_MODEL_FROM_DATABASE") or f"Device {device_id}",
            "class": class_name or dev.get("ID_PCI_CLASS_FROM_DATABASE") or "",
            "vendor_id": vendor_id,
            "device_id": device_id,
            "driver": dev.driver or "",
            "active": active,
            "revision": revision
        }

        info["icon"] = get_icon_for_device(info)
        info["id_string"] = f"{vendor_id}:{device_id}" if vendor_id and device_id else ""

        devices.append(info)

    return devices

class PCIListWidget(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_border_width(6)

        self.store = Gtk.ListStore(str, str, bool, str, str, str, str, str, str, str)

        self.treeview = Gtk.TreeView(model=self.store)
        self.treeview.set_headers_visible(True)
        self.treeview.set_enable_tree_lines(False)
        self.treeview.set_grid_lines(Gtk.TreeViewGridLines.NONE)
        self.treeview.set_property("expand", True)
        self.treeview.set_headers_clickable(True)

        # Bus
        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn(_("Bus"), renderer, text=COL_BUS)
        column.set_sort_column_id(COL_BUS)
        column.set_resizable(True)
        column.add_attribute(renderer, "sensitive", COL_ACTIVE)
        self.treeview.append_column(column)

        # Type
        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn(_("Type"), renderer, text=COL_TYPE)
        column.set_sort_column_id(COL_TYPE)
        column.set_resizable(True)
        column.add_attribute(renderer, "sensitive", COL_ACTIVE)
        self.treeview.append_column(column)

        # Vendor
        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn(_("Brand"), renderer, text=COL_VENDOR)
        column.set_sort_column_id(COL_VENDOR)
        column.set_resizable(True)
        column.add_attribute(renderer, "sensitive", COL_ACTIVE)
        self.treeview.append_column(column)

        # Icon + Name
        column = Gtk.TreeViewColumn(_("Device"))
        column.set_sort_column_id(COL_NAME)
        icon_renderer = Gtk.CellRendererPixbuf()
        renderer = Gtk.CellRendererText()
        renderer.set_property("ellipsize", 3)
        renderer.set_property("ypad", 6)
        icon_renderer.set_property("xpad", 2)
        column.pack_start(icon_renderer, False)
        column.pack_start(renderer, True)
        column.add_attribute(icon_renderer, "icon-name", COL_ICON)
        column.add_attribute(renderer, "text", COL_NAME)
        renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        self.treeview.append_column(column)
        column.set_expand(True)
        column.set_resizable(True)
        column.add_attribute(renderer, "sensitive", COL_ACTIVE)

        # ID
        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn(_("ID"), renderer, text=COL_ID)
        column.set_sort_column_id(COL_ID)
        column.set_resizable(True)
        column.add_attribute(renderer, "sensitive", COL_ACTIVE)
        self.treeview.append_column(column)

        # Driver
        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn(_("Driver"), renderer, text=COL_DRIVER)
        column.set_sort_column_id(COL_DRIVER)
        column.set_resizable(True)
        column.add_attribute(renderer, "sensitive", COL_ACTIVE)
        self.treeview.append_column(column)

        self.store.set_sort_column_id(COL_BUS, Gtk.SortType.ASCENDING)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_shadow_type(Gtk.ShadowType.IN)
        scrolled.add(self.treeview)
        self.pack_start(scrolled, True, True, 0)

        button_box = Gtk.Box(spacing=6)
        self.copy_id_btn = Gtk.Button(label=_("Copy the ID"))
        self.copy_row_btn = Gtk.Button(label=_("Copy the entire row"))
        self.copy_id_btn.set_sensitive(False)
        self.copy_row_btn.set_sensitive(False)
        button_box.pack_end(self.copy_id_btn, False, False, 0)
        button_box.pack_end(self.copy_row_btn, False, False, 0)
        self.pack_start(button_box, False, False, 0)

        selection = self.treeview.get_selection()
        selection.connect("changed", self.on_selection_changed)
        self.copy_id_btn.connect("clicked", self.on_copy_id_clicked)
        self.copy_row_btn.connect("clicked", self.on_copy_row_clicked)

    def load(self):
        self.populate_pci_devices()
        self.setup_monitor()

    def on_selection_changed(self, selection):
        model, treeiter = selection.get_selected()
        active = bool(treeiter)
        self.copy_id_btn.set_sensitive(active)
        self.copy_row_btn.set_sensitive(active)

    def on_copy_id_clicked(self, button):
        selection = self.treeview.get_selection()
        model, treeiter = selection.get_selected()
        if not treeiter:
            return
        device_id = model[treeiter][COL_ID]
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(device_id, -1)
        subprocess.Popen(['notify-send', '-i', 'xapp-dialog-information-symbolic', _("Device ID copied"), _("The device ID was copied into your clipboard.")])

    def on_copy_row_clicked(self, button):
        selection = self.treeview.get_selection()
        model, treeiter = selection.get_selected()
        if not treeiter:
            return
        text = f"{model[treeiter][COL_FULL]}"
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)
        subprocess.Popen(['notify-send', '-i', 'xapp-dialog-information-symbolic', _("Device information copied"), _("The device information was copied into your clipboard.")])

    @xt.run_async
    def populate_pci_devices(self):
        """Enumerate PCI devices in a background thread."""
        devices = get_pci_devices()
        self._update_pci_list(devices)

    @xt.run_idle
    def _update_pci_list(self, devices):
        """Update TreeStore safely inside GTK main loop."""
        self.store.clear()

        for d in devices:
            name = f"{d['device']} {d['revision']}"

            vendor = clean_brand(d['vendor'])
            full_info = f"{d['address']} {d['class']} {d['vendor']} {d['device']} {d['revision']} {d['driver']}"
            iter_ = self.store.append()
            self.store.set_value(iter_, COL_FULL, full_info)
            self.store.set_value(iter_, COL_ICON, d["icon"])
            self.store.set_value(iter_, COL_NAME, name)
            self.store.set_value(iter_, COL_BUS, d['address'])
            self.store.set_value(iter_, COL_TYPE, d['class'])
            self.store.set_value(iter_, COL_VENDOR, vendor)
            self.store.set_value(iter_, COL_ACTIVE, d["active"])
            self.store.set_value(iter_, COL_ID, d["id_string"])
            self.store.set_value(iter_, COL_DRIVER, d["driver"])

    def setup_monitor(self):
        """Watch for live PCI changes via udev monitor."""
        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context)
        monitor.filter_by(subsystem="pci")

        def on_event(action, device):
            # Just trigger background re-enumeration
            self.populate_pci_devices()

        self.observer = pyudev.MonitorObserver(monitor, callback=on_event, name="pci-monitor")
        self.observer.start()


# -------------------------------------------------------------------
# Standalone test window
# -------------------------------------------------------------------

if __name__ == "__main__":
    win = Gtk.Window(title="PCI Devices")
    viewer = PCIListWidget()
    viewer.load()
    win.add(viewer)
    win.set_default_size(800, 400)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
