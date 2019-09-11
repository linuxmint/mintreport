#!/usr/bin/python3
import os
import sys
import gettext
import gi
gi.require_version("Gtk", "3.0")
gi.require_version('GtkSource', '3.0')
gi.require_version('XApp', '1.0')
from gi.repository import Gtk, Gdk, GObject, Gio, XApp, GLib
import subprocess
import setproctitle
import threading
import locale
import imp

from common import async, idle, InfoReport, INFO_DIR

setproctitle.setproctitle("mintreport-tray")

# i18n
APP = 'mintreport'
LOCALE_DIR = "/usr/share/linuxmint/locale"
locale.bindtextdomain(APP, LOCALE_DIR)
gettext.bindtextdomain(APP, LOCALE_DIR)
gettext.textdomain(APP)
_ = gettext.gettext

class MyApplication(Gtk.Application):
    # Main initialization routine
    def __init__(self, application_id, flags):
        Gtk.Application.__init__(self, application_id=application_id, flags=flags)
        self.connect("activate", self.activate)

        # Status icon
        menu = Gtk.Menu()
        menuItem = Gtk.MenuItem.new_with_label(_("Show System Reports"))
        menuItem.connect('activate', self.on_menu_show)
        menu.append(menuItem)
        menu.append(Gtk.SeparatorMenuItem())
        menuItem = Gtk.MenuItem.new_with_label(_("Quit"))
        menuItem.connect('activate', self.on_menu_quit)
        menu.append(menuItem)
        menu.show_all()

        self.status_icon = XApp.StatusIcon()
        self.status_icon.set_visible(False)
        self.status_icon.set_name("mintreport")
        self.status_icon.connect("button-press-event", self.on_statusicon_pressed)
        self.status_icon.connect("button-release-event", self.on_statusicon_released, menu)

    def on_statusicon_pressed(self, widget, x, y, button, time, position):
        if button == 1:
            subprocess.Popen(["/bin/sh", "/usr/bin/mintreport"])
            self.status_icon.set_visible(False)

    def on_statusicon_released(self, icon, x, y, button, time, position, menu):
        if button == 3:
            if position == -1:
                # The position and coordinates are unknown. This is the
                # case when the XAppStatusIcon fallbacks as a Gtk.StatusIcon
                menu.popup(None, None, None, None, button, time)
            else:
                def position_menu_cb(menu, pointer_x, pointer_y, user_data):
                    [x, y, position] = user_data;
                    if (position == Gtk.PositionType.BOTTOM):
                        y = y - menu.get_allocation().height;
                    if (position == Gtk.PositionType.RIGHT):
                        x = x - menu.get_allocation().width;
                    return (x, y, False)
                device = Gdk.Display.get_default().get_device_manager().get_client_pointer()
                menu.popup_for_device(device, None, None, position_menu_cb, [x, y, position], button, time)

    def on_menu_show(self, widget):
        subprocess.Popen(["/bin/sh", "/usr/bin/mintreport"])

    def on_menu_quit(self, widget):
        self.quit()

    def activate(self, application):
        if not hasattr(self, "primary_instance"):
            self.hold()
            self.primary_instance = "Primary instance"
            self.load_info()
            # Load info every hour
            GLib.timeout_add_seconds(3600, self.load_info)
        else:
            print("Already running!")

    def load_info(self):
        pertinent_reports = []
        if os.path.exists(INFO_DIR):
            for dir_name in os.listdir(INFO_DIR):
                path = os.path.join(INFO_DIR, dir_name)
                try:
                    report = InfoReport(path)
                    if report.instance.is_pertinent():
                        pertinent_reports.append(report)
                except Exception as e:
                    print("Failed to load report %s: \n%s\n" % (dir_name, e))

        if len(pertinent_reports) == 0:
            self.status_icon.set_icon_name("task-due-symbolic")
            self.status_icon.set_tooltip_text(_("No reports available"))
            self.status_icon.set_visible(False)
        elif len(pertinent_reports) == 1:
            self.status_icon.set_visible(True)
            report = pertinent_reports[0]
            self.status_icon.set_icon_name(report.instance.icon)
            self.status_icon.set_tooltip_text(report.instance.title)
        else:
            self.status_icon.set_visible(True)
            self.status_icon.set_icon_name("task-due-symbolic")
            self.status_icon.set_tooltip_text(_("Some problems were detected which require your attention"))

if __name__ == "__main__":
    application = MyApplication("com.linuxmint.reports-tray", Gio.ApplicationFlags.FLAGS_NONE)
    application.run()
