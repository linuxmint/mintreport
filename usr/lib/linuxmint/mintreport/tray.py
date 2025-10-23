#!/usr/bin/python3
import gi
import os
import psutil
import setproctitle
import subprocess
import xapp.os
import xapp.util
gi.require_version("Gtk", "3.0")
gi.require_version('XApp', '1.0')
from gi.repository import Gtk, Gdk, Gio, XApp, GLib
from common import InfoReportContainer, INFO_DIR

setproctitle.setproctitle("mintreport-tray")
_ = xapp.util.l10n("mintreport")

class GtkStatusIcon(Gtk.StatusIcon):

    def __init__(self):
        Gtk.StatusIcon.__init__(self)

    def set_secondary_menu(self, menu):
        pass

    def set_icon_name(self, icon_name):
        self.set_from_icon_name(icon_name)

class MonitoredProcess():
    def __init__(self, name, cmdline, description, is_binary=False):
        self.name = name
        self.cmdline = cmdline
        self.description = description

        self.is_binary = is_binary

    def is_running(self):
        for p in psutil.process_iter():
            try:
                if self.is_binary:
                    if p.name() == self.cmdline:
                        return True
                elif self.cmdline in ' '.join(p.cmdline()):
                    return True
            except:
                continue
        return False

class MyApplication(Gtk.Application):
    # Main initialization routine
    def __init__(self, application_id, flags):
        Gtk.Application.__init__(self, application_id=application_id, flags=flags)
        self.connect("activate", self.activate)

        self.settings = Gio.Settings(schema_id="com.linuxmint.report")

        # Status icon
        self.menu = Gtk.Menu()
        menuItem = Gtk.MenuItem.new_with_label(_("Show System Reports"))
        menuItem.connect('activate', self.on_menu_show)
        self.menu.append(menuItem)
        self.menu.append(Gtk.SeparatorMenuItem())
        menuItem = Gtk.MenuItem.new_with_label(_("Quit"))
        menuItem.connect('activate', self.on_menu_quit)
        self.menu.append(menuItem)
        self.menu.show_all()

        try:
            self.status_icon = XApp.StatusIcon()
            self.status_icon.set_name("mintreport")
            self.status_icon.connect("activate", self.on_statusicon_activated)
            self.status_icon.set_secondary_menu(self.menu)
        except Exception as e:
            print("Couldn't instantiate XApp.StatusIcon: %s" % e)
            self.status_icon = GtkStatusIcon()
            self.status_icon.connect("activate", self.on_gtk_statusicon_activated)
            self.status_icon.connect("popup-menu", self.on_gtk_statusicon_popup)
        self.status_icon.set_visible(False)

        # Monitor icon
        self.monitor_icon = XApp.StatusIcon()
        self.monitor_icon.set_name("process-monitor")
        self.monitor_icon.set_visible(False)
        self.monitoring_process = None
        self.monitor_source_id = None

    def on_statusicon_activated(self, icon, button, time):
        if button == Gdk.BUTTON_PRIMARY:
            GLib.spawn_async(["/usr/bin/mintreport", "--reports"])
            self.status_icon.set_visible(False)

    def on_gtk_statusicon_activated(self, status_icon):
        self.on_statusicon_activated(status_icon, Gdk.BUTTON_PRIMARY, None)

    def on_gtk_statusicon_popup(self, status_icon, button, time):
        self.menu.popup(None, None, None, None, button, time)

    def on_menu_show(self, widget):
        GLib.spawn_async(["/usr/bin/mintreport", "--reports"])

    def on_menu_quit(self, widget):
        self.quit()

    def activate(self, application):
        if not hasattr(self, "primary_instance"):
            self.hold()
            self.primary_instance = "Primary instance"
            self.load_info()
            # Auto-refresh
            if self.settings.get_boolean("autorefresh"):
                GLib.timeout_add_seconds(self.settings.get_int("autorefresh-seconds"), self.load_info)
            # Auto-monitor
            if self.settings.get_boolean("automonitor"):
                GLib.timeout_add_seconds(self.settings.get_int("automonitor-seconds"), self.monitor)
        else:
            print("Already running!")

    def load_info(self):
        found_pertinent_report = False
        if os.path.exists(INFO_DIR):
            ignored_paths = self.settings.get_strv("ignored-reports")
            for dir_name in sorted(os.listdir(INFO_DIR)):
                path = os.path.join(INFO_DIR, dir_name)
                uuid = dir_name.split("_")[-1]
                if uuid not in ignored_paths:
                    try:
                        report = InfoReportContainer(uuid, path)
                        if report.instance.is_pertinent():
                            found_pertinent_report = True
                            break
                    except Exception as e:
                        print("Failed to load report %s: \n%s\n" % (dir_name, e))

        if found_pertinent_report:
            self.status_icon.set_visible(True)
            self.status_icon.set_icon_name("mintreport-symbolic")
            self.status_icon.set_tooltip_text(_("Some system reports require your attention"))
        else:
            self.status_icon.set_visible(False)

        return True

    def monitor(self):
        if self.monitoring_process != None:
            return GLib.SOURCE_CONTINUE
        processes = []
        processes.append(MonitoredProcess(_("System Snapshots"), "timeshift", _("A Timeshift system snapshot is being created."), is_binary=True))
        processes.append(MonitoredProcess(_("Automatic Updates"), "/usr/lib/linuxmint/mintUpdate/automatic_upgrades.py", _("Automatic updates are being installed.")))
        self.monitor_icon.set_visible(False)
        for process in processes:
            if process.is_running():
                # A process is found running!
                # Show a tray icon
                self.monitoring_process = process
                self.monitor_icon.set_visible(True)
                self.monitor_icon.set_icon_name("xsi-run-symbolic")
                tooltip = "<b>%s</b>\n%s" % (process.name, process.description)
                self.monitor_icon.set_tooltip_text(tooltip)
                # Start a clean up thread to hide the tray when it finishes
                self.monitor_source_id = GLib.timeout_add_seconds(2, self.clean_up)
        return GLib.SOURCE_CONTINUE

    def clean_up(self):
        if self.monitoring_process == None:
            return GLib.SOURCE_REMOVE
        if not self.monitoring_process.is_running():
            # The process is finished, hide the tray
            self.monitoring_process = None
            self.monitor_icon.set_visible(False)
            GLib.source_remove(self.monitor_source_id)
        return GLib.SOURCE_CONTINUE

if __name__ == "__main__":
    if ((not xapp.os.is_live_session()) and (not xapp.os.is_guest_session())):
        application = MyApplication("com.linuxmint.reports-tray", Gio.ApplicationFlags.FLAGS_NONE)
        application.run()
