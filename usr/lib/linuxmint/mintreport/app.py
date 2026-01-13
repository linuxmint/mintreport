#!/usr/bin/python3
import apt
import argparse
import datetime
import gi
import json
import os
import platform
import setproctitle
import shutil
import subprocess
import sys
import threading
import xapp.SettingsWidgets as Xs
import xapp.threading as xt
import xapp.util

gi.require_version("Gtk", "3.0")
gi.require_version('GtkSource', '3.0')
gi.require_version('XApp', '1.0')
from gi.repository import Gtk, Gdk, GtkSource, Gio

from common import InfoReportContainer, DATA_DIR, INFO_DIR, prefix_version, read_dmi, clean_brand
from bios import BIOSListWidget
from pci import PCIListWidget
from usb import USBListWidget
from gpu import GPUListWidget
from sensors import SensorsListWidget


setproctitle.setproctitle("mintreport")
_ = xapp.util.l10n("mintreport")

TMP_DIR = "/tmp/mintreport"
TMP_INFO_DIR = os.path.join(TMP_DIR, "reports")
TMP_INXI_FILE = os.path.join(TMP_DIR, "inxi")

UNPACK_DIR = os.path.join(TMP_DIR, "crash")
CRASH_ARCHIVE = os.path.join(TMP_DIR, "crash.tar.gz")

COL_CRASH_DAY, COL_CRASH_DATE, COL_CRASH_TIME, COL_CRASH_TIMEZONE, COL_CRASH_PID, COL_CRASH_EXE, COL_CRASH_OBJECT = range(7)

COL_INFO_ICON, COL_INFO_TITLE, COL_INFO_REPORT = range(3)

class CrashReport():

    def __init__(self, timestamp, pid, sig, executable):
        self.timestamp = timestamp
        self.pid = pid
        self.sig = sig
        self.executable = executable

class MyApplication(Gtk.Application):
    # Main initialization routine
    def __init__(self, application_id, flags):
        Gtk.Application.__init__(self, application_id=application_id, flags=flags)
        self.connect("activate", self.activate)
        self.connect("command-line", self.on_command_line)
        self.report_window = None
        self.page = None

    def on_command_line(self, app, command_line):
        # Parse fresh args each time
        parser = argparse.ArgumentParser(add_help=False)
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--reports", action="store_const", dest="page", const="reports")
        group.add_argument("--crashes", action="store_const", dest="page", const="crashes")
        group.add_argument("--usb", action="store_const", dest="page", const="usb")
        group.add_argument("--info", action="store_const", dest="page", const="info")
        group.add_argument("--bios", action="store_const", dest="page", const="bios")
        group.add_argument("--pci", action="store_const", dest="page", const="pci")
        group.add_argument("--gpu", action="store_const", dest="page", const="gpu")
        group.add_argument("--sensors", action="store_const", dest="page", const="sensors")
        argv = command_line.get_arguments()[1:]
        args, _ = parser.parse_known_args(argv)
        if args.page is None:
            args.page = "info"
        self.page = args.page
        self.activate(app)
        return 0

    def activate(self, application):
        if self.report_window is None:
            self.report_window = MintReportWindow(self)
            self.add_window(self.report_window.window)
        window = self.report_window.window
        window = self.get_windows()[0]
        window.present()
        window.show_all()
        self.report_window.show_page(self.page)

def kill_process(process):
    process.kill()

def get_process_output(command):
    timeout = 2.0  # Timeout for any subprocess before aborting it

    lines = []
    p = subprocess.Popen(command, stdout=subprocess.PIPE)
    timer = threading.Timer(timeout, kill_process, [p])
    timer.start()
    while True:
        line = p.stdout.readline()
        if not line:
            break
        if line != '':
            lines.append(line.decode('utf-8'))
    timer.cancel()
    return lines


def get_graphic_cards():
    cards = {}
    count = 0
    envpath = os.environ["PATH"]
    os.environ["PATH"] = envpath + ":/usr/local/sbin:/usr/sbin:/sbin"
    for card in get_process_output("lspci"):
        for prefix in ["VGA compatible controller:", "3D controller:", "Display controller:"]:
            if prefix in card:
                cardName = card.split(prefix)[1].split("(rev")[0].strip()
                cards[count] = cardName
                count += 1
    os.environ["PATH"] = envpath
    return cards


def get_disk_size():
    disksize = 0
    try:
        out = get_process_output(("lsblk", "--json", "--output", "size", "--bytes", "--nodeps"))
        jsonobj = json.loads(''.join(out))
    except Exception:
        return _("Unknown size"), False

    for blk in jsonobj['blockdevices']:
        disksize += int(blk['size'])

    return disksize, (len(jsonobj['blockdevices']) > 1)


def get_proc_infos():
    # For some platforms, 'model name' will no longer take effect.
    # We can try our best to detect it, but if all attempts failed just leave it to be "Unknown".
    # Source: https://github.com/dylanaraps/neofetch/blob/6dd85d67fc0d4ede9248f2df31b2cd554cca6c2f/neofetch#L2163
    cpudetect = ("model name", "Hardware", "Processor", "cpu model", "chip type", "cpu type")
    infos = [
        ("/proc/cpuinfo", [("cpu_name", cpudetect), ("cpu_siblings", ("siblings",)), ("cpu_cores", ("cpu cores",))]),
        ("/proc/meminfo", [("mem_total", ("MemTotal",))])
    ]
    result = {}
    for (proc, pairs) in infos:
        for line in get_process_output(("cat", proc)):
            for (key, start) in pairs:
                for item in start:
                    if line.startswith(item):
                        result[key] = line.split(':', 1)[1].strip()
                        break
    if "cpu_name" not in result:
        result["cpu_name"] = _("Unknown CPU")
    if "mem_total" not in result:
        result["mem_total"] = _("Unknown size")
    return result

class MintReportWindow():

    def __init__(self, application):

        self.application = application
        self.settings = Gio.Settings(schema_id="com.linuxmint.report")

        os.system("mkdir -p %s" % TMP_DIR)
        os.system("rm -rf %s/*" % TMP_DIR)
        os.system("mkdir -p %s" % UNPACK_DIR)
        os.system("cp -R %s/* %s/" % (DATA_DIR, TMP_DIR))

        # Create a CSS provider
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            .logo-box {
                background-color: #86be43;
                border-radius: 10px;
                padding: 12px;
            }
        """)
        screen = Gdk.Screen.get_default()
        Gtk.StyleContext.add_provider_for_screen(
            screen,
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self._cache = None
        # Set the Glade file
        gladefile = "/usr/share/linuxmint/mintreport/mintreport.ui"
        self.builder = Gtk.Builder()
        self.builder.set_translation_domain("mintreport")
        self.builder.add_from_file(gladefile)
        self.window = self.builder.get_object("main_window")
        self.window.set_title(_("System Information"))
        self.window.set_icon_name("mintreport")

        self.stack = self.builder.get_object("main_stack")
        self.spinner = self.builder.get_object("crash_spinner")

        # the crashes treeview
        self.treeview_crashes = self.builder.get_object("treeview_crashes")

        def render_date(column, cell, model, i, *args):
            cell.props.text = " ".join([model[i][COL_CRASH_DAY],
                                        model[i][COL_CRASH_DATE],
                                        model[i][COL_CRASH_TIME],
                                        model[i][COL_CRASH_TIMEZONE]])

        def sort_by_date(model, a, b, *args):
            date_a = datetime.date.from_iso_format(model[a][COL_CRASH_DATE])
            date_b = datetime.date.from_iso_format(model[b][COL_CRASH_DATE])

            if date_a < date_b:
                return -1
            elif date_a > date_b:
                return 1

            time_a = datetime.time.fromisoformat(model[a][COL_CRASH_TIME])
            time_b = datetime.time.fromisoformat(model[b][COL_CRASH_TIME])

            if time_a < time_b:
                return -1
            elif time_a > time_b:
                return 1

            return 0

        cell_renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn('', cell_renderer)
        column.set_cell_data_func(cell_renderer, render_date)
        column.set_resizable(True)
        cell_renderer.set_property("ypad", 6)
        self.treeview_crashes.append_column(column)
        column = Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=COL_CRASH_PID)
        column.set_sort_column_id(COL_CRASH_PID)
        column.set_resizable(True)
        self.treeview_crashes.append_column(column)
        column = Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=COL_CRASH_EXE)
        column.set_sort_column_id(COL_CRASH_EXE)
        column.set_resizable(True)
        self.treeview_crashes.append_column(column)
        self.treeview_crashes.show()
        self.model_crashes = Gtk.ListStore(str, str, str, str, str, str, object) # timestamp, pid, exe, object
        self.model_crashes.set_sort_func(COL_CRASH_DATE, sort_by_date)
        self.treeview_crashes.set_model(self.model_crashes)

        self.buffer = GtkSource.Buffer()
        self.language_manager = GtkSource.LanguageManager()
        style_manager = GtkSource.StyleSchemeManager()
        self.buffer.set_style_scheme(style_manager.get_scheme("oblivion"))
        self.sourceview = GtkSource.View.new_with_buffer(self.buffer)
        self.builder.get_object("scrolledwindow_crash").add(self.sourceview)
        self.sourceview.show()

        self.treeview_crashes.get_selection().connect("changed", self.on_crash_selected)

        self.bugtracker = "https://bugs.launchpad.net/"

        self.localfiles_button = self.builder.get_object("button_browse_crash_report")
        self.bugtracker_button = self.builder.get_object("button_open_bugtracker")
        self.pastebin_button = self.builder.get_object("button_pastebin")
        self.localfiles_button.connect("clicked", self.on_button_browse_crash_report_clicked)
        self.bugtracker_button.connect("clicked", self.on_button_open_bugtracker_clicked)
        self.pastebin_button.connect("clicked", self.on_button_pastebin_clicked)

        # the info treeview
        self.info_button_box = self.builder.get_object("info_button_box")
        self.info_descriptions_box = self.builder.get_object("info_descriptions_box")

        self.treeview_info = self.builder.get_object("treeview_info")
        renderer = Gtk.CellRendererPixbuf()
        column = Gtk.TreeViewColumn("", renderer, icon_name=COL_INFO_ICON)
        self.treeview_info.append_column(column)

        renderer = Gtk.CellRendererText()
        renderer.set_property("ypad", 6)
        column = Gtk.TreeViewColumn("", renderer, text=COL_INFO_TITLE)
        column.set_sort_column_id(COL_INFO_TITLE)
        column.set_resizable(True)
        self.treeview_info.append_column(column)
        self.treeview_info.show()
        self.model_info = Gtk.TreeStore(str, str, object) # icon, name, report
        self.model_info.set_sort_column_id(COL_INFO_TITLE, Gtk.SortType.ASCENDING)
        self.treeview_info.set_model(self.model_info)

        self.treeview_info.get_selection().connect("changed", self.on_info_selected)

        if os.path.exists("/usr/bin/coredumpctl"):
            self.builder.get_object("crash_internal_stack").set_visible_child_name("page_reports")
            self.load_crashes()
        else:
            self.builder.get_object("crash_internal_stack").set_visible_child_name("page_error")

        page = Xs.SettingsPage()
        page.set_spacing(24)
        page.set_margin_left(0)
        page.set_margin_right(0)
        page.set_margin_top(0)
        page.set_margin_bottom(0)
        self.builder.get_object("box_info_widget").add(page)

        self.sysinfo_section = page.add_section()

        accel_group = Gtk.AccelGroup()
        self.window.add_accel_group(accel_group)

        # Menubar
        menu = self.builder.get_object("main_menu")

        refresh_button = self.builder.get_object("refresh_button")
        refresh_button.connect('clicked', self.on_menu_refresh)
        key, mod = Gtk.accelerator_parse("<Control>R")
        refresh_button.add_accelerator("activate", accel_group, key, mod, Gtk.AccelFlags.VISIBLE)

        item = Gtk.ImageMenuItem(label=_("Restore ignored reports"))
        item.connect('activate', self.on_menu_restore)
        menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())

        item = Gtk.ImageMenuItem(label=_("Quit"))
        image = Gtk.Image.new_from_icon_name("xsi-exit-symbolic", Gtk.IconSize.MENU)
        item.set_image(image)
        item.connect('activate', self.on_menu_quit)
        key, mod = Gtk.accelerator_parse("<Control>Q")
        item.add_accelerator("activate", accel_group, key, mod, Gtk.AccelFlags.VISIBLE)
        key, mod = Gtk.accelerator_parse("<Control>W")
        item.add_accelerator("activate", accel_group, key, mod, Gtk.AccelFlags.VISIBLE)
        menu.append(item)

        item = Gtk.ImageMenuItem()
        item.set_image(Gtk.Image.new_from_icon_name("xsi-help-about-symbolic", Gtk.IconSize.MENU))
        item.set_label(_("About"))
        item.connect("activate", self.open_about)
        menu.append(item)

        menu.show_all()

        # Info page
        procInfos = get_proc_infos()
        infos = []

         # Product
        version = prefix_version(read_dmi('product_version'))
        vendor = clean_brand(read_dmi('sys_vendor'))
        sku = read_dmi('product_sku')
        product = f"{vendor} {read_dmi('product_name')} {version} {sku}"
        product = " ".join(product.split()) # remove unecessary spaces
        infos.append((_("Computer"), product))

        try:
            (memsize, memunit) = procInfos['mem_total'].split(" ")
            memsize = float(memsize)
        except ValueError:
            memsize = procInfos['mem_total']
            memunit = ""
        processorName = procInfos['cpu_name'].replace("(R)", "\u00A9").replace("(TM)", "\u2122")
        if 'cpu_cores' in procInfos:
            processorName = processorName + " \u00D7 " + procInfos['cpu_cores']

        with open("/etc/linuxmint/info") as f:
            config = dict([line.strip().split("=") for line in f])
        distribution = "Linux Mint"
        if os.path.exists("/usr/share/doc/debian-system-adjustments/copyright"):
            distribution = "LMDE"
        release = config['RELEASE']
        edition = config['EDITION'].replace('"', '')
        architecture = "64-bit"
        if platform.machine() not in ["x86_64", "aarch64"]:
            architecture = "32-bit"
        infos.append((_("Operating System"), f"{distribution} {release} - {edition} {architecture}"))
        infos.append((_("Linux Kernel"), platform.release()))
        infos.append((_("Processor"), processorName))
        cards = get_graphic_cards()
        for card in cards:
            infos.append((_("Graphics Card"), cards[card]))
        if memunit == "kB":
            infos.append((_("Memory"), '%.1f %s' % ((float(memsize)/(1000**2)), _("GB"))))
        else:
            infos.append((_("Memory"), procInfos['mem_total']))

        diskSize, multipleDisks = get_disk_size()
        if multipleDisks:
            diskText = _("Hard Drives")
        else:
            diskText = _("Hard Drive")
        try:
            infos.append((diskText, '%.1f %s' % ((diskSize / (1000**3)), _("GB"))))
        except:
            infos.append((diskText, diskSize))

        desktop = os.getenv("XDG_CURRENT_DESKTOP")
        if "cinnamon" in desktop.lower():
            desktop = f"Cinnamon {os.getenv("CINNAMON_VERSION")}"
        infos.append((_("Desktop Environment"), desktop))

        display_server_name = "X11"

        if os.getenv("XDG_SESSION_TYPE") == "wayland":
            display_server_name = "Wayland"

        infos.append((_("Display Server"), display_server_name))

        for (key, value) in infos:
            self.sysinfo_section.add_row(self.create_info_row(key, value))

        self.inxi_info = ""
        self.builder.get_object("button_sysinfo_copy").connect("clicked", self.copy_inxi_info)
        self.builder.get_object("button_sysinfo_upload").connect("clicked", self.upload_inxi_info)

        # USB page
        self.usb_widget = USBListWidget()
        self.builder.get_object("box_usb_widget").pack_start(self.usb_widget, True, True, 0)

        # PCI page
        self.pci_widget = PCIListWidget()
        self.builder.get_object("box_pci_widget").pack_start(self.pci_widget, True, True, 0)

        # Sensors page
        self.sensors_widget = SensorsListWidget()
        self.builder.get_object("box_sensors_widget").pack_start(self.sensors_widget, True, True, 0)

        # BIOS page
        self.bios_widget = BIOSListWidget()
        self.builder.get_object("box_bios_widget").add(self.bios_widget)

        self.gpu_widget = GPUListWidget()
        self.builder.get_object("box_gpu_widget").add(self.gpu_widget)

        self.load_inxi_info()
        self.load_reports()
        self.load_usb()
        self.load_pci()
        self.load_bios()
        self.load_gpu()
        self.load_sensors()

    def show_page(self, page_name):
        page_name = f"page_{page_name}"
        self.stack.set_visible_child_name(page_name)

    def create_info_row(self, key, value):
        widget = Xs.SettingsWidget()
        widget.set_spacing(40)
        labelKey = Gtk.Label.new(key)
        widget.pack_start(labelKey, False, False, 0)
        labelKey.get_style_context().add_class("dim-label")
        labelValue = Gtk.Label.new(value)
        labelValue.set_selectable(True)
        labelValue.set_line_wrap(True)
        widget.pack_end(labelValue, False, False, 0)
        return widget

    @property
    def cache(self):
        """Cache data from apt"""
        if self._cache is None:
            # Lazily initialize cache data because it is only used when a crash dump is selected
            # on the 'Crash reports' page
            self._cache = apt.Cache()

        return self._cache

    def open_about(self, widget):
        dlg = Gtk.AboutDialog()
        dlg.set_transient_for(self.window)
        dlg.set_title(_("About"))
        dlg.set_program_name("mintreport")
        dlg.set_comments(_("System Information"))
        try:
            h = open('/usr/share/common-licenses/GPL', encoding="utf-8")
            s = h.readlines()
            gpl = ""
            for line in s:
                gpl += line
            h.close()
            dlg.set_license(gpl)
        except Exception as e:
            print (e)

        dlg.set_version("__DEB_VERSION__")
        dlg.set_icon_name("mintreport")
        dlg.set_logo_icon_name("mintreport")
        dlg.set_website("https://www.github.com/linuxmint/mintreport")
        def close(w, res):
            if res == Gtk.ResponseType.CANCEL or res == Gtk.ResponseType.DELETE_EVENT:
                w.destroy()
        dlg.connect("response", close)
        dlg.show()

    def on_menu_restore(self, widget):
        self.settings.reset("ignored-reports")
        self.load_reports()

    def on_menu_refresh(self, widget):
        self.load_reports()
        self.load_crashes()

    def on_menu_quit(self, widget):
        self.application.quit()

    @xt.run_async
    def load_inxi_info(self):
        try:
            sysinfo = subprocess.check_output("LANG=C inxi -Fxxxrzc0 --usb", shell=True).decode("utf-8", errors='replace')
            self.inxi_info = sysinfo
            self.enable_inxi_buttons()
            with open(TMP_INXI_FILE, "w") as f:
                f.write(sysinfo)
        except Exception as e:
            subprocess.Popen(['notify-send', '-i', 'xsi-dialog-error-symbolic', _("An error occurred while gathering the system information."), str(e)])
            print (e)

    @xt.run_idle
    def enable_inxi_buttons(self):
        self.builder.get_object("button_sysinfo_copy").set_sensitive(True)
        self.builder.get_object("button_sysinfo_upload").set_sensitive(True)

    def copy_inxi_info(self, button):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text("[code]\n%s[/code]\n" % self.inxi_info, -1)
        subprocess.Popen(['notify-send', '-i', 'xsi-dialog-information-symbolic', _("System information copied"), _("Your system information was copied into your clipboard so you can paste it on the forums.")])

    def upload_inxi_info(self, button):
        try:
            output = subprocess.check_output("pastebin %s" % TMP_INXI_FILE, shell=True).decode("UTF-8")
            link = output.rstrip('\x00').strip() # Remove ASCII null termination with \x00
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(link, -1)
            subprocess.Popen(['notify-send', '-i', 'xsi-dialog-information-symbolic', _("System information uploaded"), _("Your system information was uploaded to %s. This link was placed in your clipboard.") % link])
        except Exception as e:
            subprocess.Popen(['notify-send', '-i', 'xsi-dialog-error-symbolic', _("An error occurred while uploading the system information"), _("Copy and paste the system information manually into a pastebin site like https://pastebin.com."), str(e)])

    @xt.run_idle
    def add_report_to_treeview(self, report):
        iter = self.model_info.insert_before(None, None)
        self.model_info.set_value(iter, COL_INFO_ICON, report.instance.icon)
        self.model_info.set_value(iter, COL_INFO_TITLE, report.instance.title)
        self.model_info.set_value(iter, COL_INFO_REPORT, report)

    @xt.run_idle
    def clear_info_treeview(self):
        self.model_info.clear()
        self.builder.get_object("info_box").hide()

    @xt.run_idle
    def show_info_spinner(self):
        self.builder.get_object("box_info_stack").set_visible_child_name("spinner")
        self.builder.get_object("info_spinner").start()

    @xt.run_idle
    def show_info_reports(self):
        if self.num_info_found > 0:
            self.builder.get_object("box_info_stack").set_visible_child_name("reports")
            iter_first = self.model_info.get_iter_first()
            if iter_first is not None:
                self.treeview_info.get_selection().select_iter(iter_first)
        else:
            self.builder.get_object("box_info_stack").set_visible_child_name("done")
        self.builder.get_object("info_spinner").stop()

    @xt.run_async
    def load_reports(self):
        self.loading = True
        self.clear_info_treeview()
        self.show_info_spinner()
        self.num_info_found = 0
        if os.path.exists(INFO_DIR):
            ignored_paths = self.settings.get_strv("ignored-reports")
            for dir_name in sorted(os.listdir(INFO_DIR)):
                path = os.path.join(INFO_DIR, dir_name)
                uuid = dir_name.split("_")[-1]
                print ("Checking %s" % dir_name)
                if uuid not in ignored_paths:
                    try:
                        report = InfoReportContainer(uuid, path)
                        if report.instance.is_pertinent():
                            self.add_report_to_treeview(report)
                            self.num_info_found += 1
                    except Exception as e:
                        print("Failed to load report %s: \n%s\n" % (dir_name, e))
        self.loading = False
        self.show_info_reports()

    @xt.run_async
    def load_usb(self):
        self.usb_widget.load()

    @xt.run_async
    def load_pci(self):
        self.pci_widget.load()

    @xt.run_async
    def load_sensors(self):
        self.sensors_widget.load()

    @xt.run_async
    def load_bios(self):
        self.bios_widget.load()

    @xt.run_async
    def load_gpu(self):
        self.gpu_widget.load()

    def on_info_selected(self, selection):
        if self.loading:
            return
        model, iter = selection.get_selected()
        if iter is not None:
            report = model.get_value(iter, COL_INFO_REPORT)
            descriptions = report.instance.get_descriptions()
            actions = report.instance.get_actions()
            self.builder.get_object("info_icon_image").set_from_icon_name(report.instance.icon, Gtk.IconSize.DIALOG)
            self.builder.get_object("info_title_label").set_text(report.instance.title)
            for child in self.info_descriptions_box.get_children():
                self.info_descriptions_box.remove(child)
            for description in descriptions:
                label = Gtk.Label(label=description)
                label.set_use_markup(True)
                label.set_line_wrap(True)
                self.info_descriptions_box.add(label)
            for child in self.info_button_box.get_children():
                self.info_button_box.remove(child)
            for action in actions:
                button = Gtk.Button(label=action.label)
                button.connect("clicked", self.on_info_action_clicked, action.callback, action.data)
                if action.style is not None:
                    button.get_style_context().add_class(action.style)
                self.info_button_box.add(button)
            if report.instance.has_ignore_button:
                button = Gtk.Button(label=_("Ignore this report"))
                button.connect("clicked", self.on_ignore_button_clicked)
                self.info_button_box.add(button)
            self.builder.get_object("info_box").show_all()

    def on_info_action_clicked(self, button, callback, data):
        self.window.set_sensitive(False)
        reload_requested = callback(data)
        if reload_requested:
            self.load_reports()
        self.window.set_sensitive(True)

    def on_ignore_button_clicked(self, button):
            model, iter = self.treeview_info.get_selection().get_selected()
            if iter is not None:
                report = model.get_value(iter, COL_INFO_REPORT)
                dialog = Gtk.MessageDialog(self.window, 0, Gtk.MessageType.QUESTION, Gtk.ButtonsType.OK_CANCEL, _("Are you sure you want to ignore this report?"))
                dialog.format_secondary_text(_("The report will be permanently ignored and will no longer be visible."))
                response = dialog.run()
                dialog.destroy()
                if response == Gtk.ResponseType.OK:
                    ignored_uuids = self.settings.get_strv("ignored-reports")
                    if report.uuid not in ignored_uuids:
                        ignored_uuids.append(report.uuid)
                        self.settings.set_strv("ignored-reports", ignored_uuids)
                        self.num_info_found -= 1
                        model.remove(iter)
                        if self.num_info_found == 0:
                            self.show_info_reports()

    @xt.run_idle
    def load_crashes(self):
        self.loading = True
        self.model_crashes.clear()

        process = subprocess.run(['coredumpctl', 'list', '--no-legend', '-r', '-q'], stdout=subprocess.PIPE)
        if process.returncode != 0:
        	# in LMDE 3, coredumpctl doesn't have -r and -q options
        	process = subprocess.run(['coredumpctl', 'list', '--no-legend'], stdout=subprocess.PIPE)
        coredumps = process.stdout
        lines = coredumps.decode('utf-8').split('\n')
        for line in lines:
            # Ignore empty lines
            if not line.strip():
                continue
            line = " ".join(line.split()) # remove blank spaces between fields in the coredumpctl output
            try:
                (day, date, time, timezone, pid, uid, gid, sig, corefile, exe, *extra) = line.split(" ", 10)
            except Exception as e:
                print("coredumpctl output: '%s' could not be split: %s" % (line, e))
                continue
            # Ignore crashes for which the info isn't available
            if corefile != "present":
                continue
            timestamp = " ".join([day, date, time, timezone])
            report = CrashReport(timestamp, pid, sig, exe)
            self.model_crashes.append([day, date, time, timezone, pid, exe, report])
        self.loading = False

    def on_crash_selected(self, selection):
        if self.loading:
            return
        self.builder.get_object("crash_stack").set_visible_child_name("page0")
        self.spinner.start()
        self.spinner.show()
        self.treeview_crashes.set_sensitive(False)
        self.localfiles_button.set_sensitive(False)
        self.bugtracker_button.set_sensitive(False)
        self.pastebin_button.set_sensitive(False)
        self.buffer.set_language(self.language_manager.get_language(""))
        self.buffer.set_text("")
        os.system("rm -rf %s/*" % UNPACK_DIR)
        model, iter = selection.get_selected()
        if iter is not None:
            report = model.get_value(iter, COL_CRASH_OBJECT)
            self.dump_crash_report(report)

    @xt.run_async
    def dump_crash_report(self, report):

        os.chdir(UNPACK_DIR)
        subprocess.call(["coredumpctl", "dump", report.pid, "-o", "CoreDump"])

        # Add info about the Linux Mint release
        if os.path.exists("/etc/linuxmint/info"):
            shutil.copyfile("/etc/linuxmint/info", "LinuxMintInfo")

        # Produce a list of installed packages
        with open("Packages", "w") as f:
            subprocess.call(['dpkg', '-l'], stdout=f)

        # Produce an Inxi report
        if os.path.exists(TMP_INXI_FILE):
            os.system("cp %s Inxi" % TMP_INXI_FILE)

        executable_path = report.executable

        # Identify bug tracker
        try:
            self.bugtracker = "https://bugs.launchpad.net/"
            output = subprocess.check_output(["dpkg", "-S", executable_path]).decode("utf-8")
            if ":" in output:
                output = output.split(":")[0]
                # Check if -dbg package is missing
                dbg_name = "%s-dbg" % output
                if dbg_name in self.cache and not self.cache[dbg_name].is_installed:
                    self.buffer.set_text(_("The debug symbols are missing for %(program)s.\nPlease install %(package)s.") % {'program':output, 'package':dbg_name})
                    self.on_unpack_crash_report_finished()
                    return

                if "mate" in output or output in ["caja", "atril", "pluma", "engrampa", "eom"]:
                    self.bugtracker = "https://github.com/mate-desktop/%s/issues" % output
                elif output in self.cache:
                    pkg = self.cache[output]
                    self.bugtracker = "https://bugs.launchpad.net/%s" % output
                    for origin in pkg.installed.origins:
                        if origin.origin == "linuxmint":
                            self.bugtracker = "https://github.com/linuxmint/%s/issues" % output
                            break
        except:
            self.buffer.set_text(_("The package providing %s could not be found.\nIf you want to generate a stack trace for this crash report, please reinstall it.") % executable_path)
            self.on_unpack_crash_report_finished()
            return

        # Produce an info trace (coredumpctl info PID)
        os.system("echo '===================================================================' > StackTrace")
        os.system("echo ' Info                                                              ' >> StackTrace")
        os.system("echo '===================================================================' >> StackTrace")
        os.system("coredumpctl info %s >> StackTrace" % report.pid)

        # Produce a stack trace
        if os.path.exists("CoreDump"):
            os.system("echo '===================================================================' >> StackTrace")
            os.system("echo ' GDB Log                                                           ' >> StackTrace")
            os.system("echo '===================================================================' >> StackTrace")
            os.system("LANG=C gdb %s CoreDump --batch >> StackTrace 2>&1" % executable_path)
            os.system("echo '\n===================================================================' >> StackTrace")
            os.system("echo ' GDB Backtrace                                                     ' >> StackTrace")
            os.system("echo '===================================================================' >> StackTrace")
            os.system("LANG=C gdb %s CoreDump --batch --ex bt >> StackTrace 2>&1" % executable_path)
            os.system("echo '\n===================================================================' >> StackTrace")
            os.system("echo ' GDB Backtrace (all threads)                                       ' >> StackTrace")
            os.system("echo '===================================================================' >> StackTrace")
            os.system("LANG=C gdb %s CoreDump --batch --ex 'thread apply all bt full' --ex bt >> StackTrace 2>&1" % executable_path)

        with open("StackTrace") as f:
            text = f.read()
            if "is not at the expected address (wrong library or version mismatch" in text:
                self.buffer.set_text(_("The headers or binaries installed on your system do not match the code which was executed during the crash.\nThey probably got upgraded since.\nA stack trace is available in 'Local Files' but its content is probably inaccurate."))
            else:
                self.show_stack_info(text)

        # Archive the crash report - exclude the CoreDump as it can be very big (close to 1GB)
        os.chdir(TMP_DIR)
        subprocess.call(["tar", "caf", CRASH_ARCHIVE, "crash", "--exclude", "CoreDump"])

        self.on_unpack_crash_report_finished()

    @xt.run_idle
    def on_unpack_crash_report_finished(self):
        self.treeview_crashes.set_sensitive(True)
        self.localfiles_button.set_sensitive(True)
        self.spinner.stop()
        self.builder.get_object("crash_stack").set_visible_child_name("page1")

    @xt.run_idle
    def show_stack_info(self, text):
        self.buffer.set_language(self.language_manager.get_language("gdb-log"))
        self.buffer.set_text(text)
        self.bugtracker_button.set_sensitive(True)
        self.pastebin_button.set_sensitive(True)

    def on_button_browse_crash_report_clicked(self, button):
        os.system("xdg-open %s" % TMP_DIR)

    def on_button_open_bugtracker_clicked(self, button):
        os.system("xdg-open %s" % self.bugtracker)

    def on_button_pastebin_clicked(self, button):
        pastebin = subprocess.Popen(['/usr/bin/pastebin', os.path.join(UNPACK_DIR, "StackTrace")], stdout=subprocess.PIPE)
        output = pastebin.communicate()[0]
        output = output.split()[0] # if we have more than one URL, only use the first one
        pastebin.wait()
        subprocess.call(['xdg-open', output])

if __name__ == "__main__":
    application = MyApplication("com.linuxmint.reports", Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
    application.run(sys.argv)
