#!/usr/bin/python3
import gi
import json
import os
import psutil
import setproctitle
import subprocess
import time
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

    # Returns the tooltip text and the progress (0..1, or None if unknown)
    def get_status(self):
        return (self.description, None, None)

# Timeshift keeps a lock file saying which kind of run holds it ("backup" for the scheduled check,
# "ondemand", "delete", "restore", "" for the window). Newer versions also publish what they are
# doing and how far they have got in a status file next to it.
TIMESHIFT_LOCK = "/var/run/lock/timeshift/lock"
TIMESHIFT_STATUS = "/var/run/lock/timeshift/status"

class TimeshiftProcess(MonitoredProcess):
    def __init__(self):
        MonitoredProcess.__init__(self, _("System Snapshots"), "timeshift", _("A Timeshift system snapshot is being created."), is_binary=True)
        # the scheduled check whose task is being shown, and the last task it published
        self.task_pid = None
        self.task_action = ""

    def read_lock(self):
        try:
            with open(TIMESHIFT_LOCK) as f:
                fields = f.read().split(";")
            pid = int(fields[0])
            mode = fields[1].strip() if len(fields) > 1 else ""
            if psutil.Process(pid).name().startswith("timeshift"):
                return (pid, mode)
        except (OSError, ValueError, psutil.Error):
            pass
        return (None, None)

    def lock_age(self):
        try:
            return time.time() - os.stat(TIMESHIFT_LOCK).st_mtime
        except OSError:
            return 0

    def read_status(self, pid):
        try:
            with open(TIMESHIFT_STATUS) as f:
                status = json.load(f)
            if status.get("pid") == pid:
                return status
        except (OSError, ValueError):
            pass
        return {}

    def is_running(self):
        pid, mode = self.read_lock()
        if pid is None:
            return False
        if mode == "backup":
            # The hourly check holds the lock for a few seconds even when nothing is due. Only show it
            # once it has started a task, or has held the lock for longer than that (versions without
            # the status file), then keep it shown until it ends, also between its steps.
            if pid != self.task_pid and ("action" in self.read_status(pid) or self.lock_age() > 10):
                self.task_pid = pid
            return pid == self.task_pid
        if mode == "" or mode.startswith("list"):
            # the window, or a quick listing: only show while it publishes a task (creating, deleting...)
            return "action" in self.read_status(pid)
        return True

    def get_status(self):
        pid, mode = self.read_lock()
        mode = mode or ""
        status = self.read_status(pid) if pid is not None else {}
        action = status.get("action", "")
        if pid == self.task_pid:
            # between two steps of a scheduled check there is no status file, keep its last task
            if action:
                self.task_action = action
            else:
                action = self.task_action

        if action == "checking-space":
            description = _("Timeshift is checking the free space for a new snapshot.")
        elif action == "creating" or (action == "" and mode == "ondemand"):
            description = _("A Timeshift system snapshot is being created.")
        elif action == "deleting" or (action == "" and mode.startswith("delete")):
            description = _("A Timeshift snapshot is being deleted.")
        elif action in ("restoring", "comparing") or (action == "" and mode == "restore"):
            description = _("A Timeshift snapshot is being restored.")
        else:
            description = _("Timeshift is running.")

        progress = status.get("progress")
        remaining = status.get("seconds_remaining", -1)
        if progress is not None and progress >= 0:
            description += "\n" + _("%d%% complete") % round(progress * 100)
            if remaining is not None and remaining >= 0:
                duration = "%d:%02d:%02d" % (remaining // 3600, remaining % 3600 // 60, remaining % 60)
                description += ", " + _("%s remaining") % duration
        else:
            progress = None

        return (description, progress, status.get("snapshot"))

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
        processes.append(TimeshiftProcess())
        processes.append(MonitoredProcess(_("Automatic Updates"), "/usr/lib/linuxmint/mintUpdate/automatic_upgrades.py", _("Automatic updates are being installed.")))
        self.monitor_icon.set_visible(False)
        for process in processes:
            if process.is_running():
                # A process is found running!
                # Show a tray icon
                self.monitoring_process = process
                self.monitor_icon.set_visible(True)
                self.monitor_icon.set_icon_name("xsi-run-symbolic")
                self.update_monitor_icon()
                # Start a clean up thread to hide the tray when it finishes
                self.monitor_source_id = GLib.timeout_add_seconds(2, self.clean_up)
        return GLib.SOURCE_CONTINUE

    def update_monitor_icon(self):
        process = self.monitoring_process
        description, progress, _snapshot = process.get_status()
        self.monitor_icon.set_tooltip_text("<b>%s</b>\n%s" % (process.name, description))
        # the percentage next to the icon, when the process publishes it
        self.monitor_icon.set_label("" if progress is None else "%d%%" % round(progress * 100))

    def clean_up(self):
        if self.monitoring_process == None:
            return GLib.SOURCE_REMOVE
        if not self.monitoring_process.is_running():
            # The process is finished, hide the tray
            self.monitoring_process = None
            self.monitor_icon.set_label("")
            self.monitor_icon.set_visible(False)
            GLib.source_remove(self.monitor_source_id)
        else:
            self.update_monitor_icon()
        return GLib.SOURCE_CONTINUE

if __name__ == "__main__":
    if ((not xapp.os.is_live_session()) and (not xapp.os.is_guest_session())):
        application = MyApplication("com.linuxmint.reports-tray", Gio.ApplicationFlags.FLAGS_NONE)
        application.run()
