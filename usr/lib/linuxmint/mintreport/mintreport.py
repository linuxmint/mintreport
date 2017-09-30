#!/usr/bin/python3

import apt
import os
import sys
import gettext
import gi
gi.require_version("Gtk", "3.0")
gi.require_version('GtkSource', '3.0')
gi.require_version('WebKit', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GtkSource, GObject, WebKit, Gio
import subprocess
import shutil
import time
import setproctitle
import threading
setproctitle.setproctitle("mintreport")

import imp
import json

import environment

# i18n
gettext.install("mintreport", "/usr/share/linuxmint/locale")

INFO_DIR = "/usr/share/linuxmint/mintreport/reports"

CRASH_DIR = "/var/crash"

TMP_DIR = "/tmp/mintreport"
UNPACK_DIR = os.path.join(TMP_DIR, "crash")
CRASH_ARCHIVE = os.path.join(TMP_DIR, "crash.tar.gz")

COL_CRASH_TIMESTAMP, COL_CRASH_DATE, COL_CRASH_FILENAME = range(3)

COL_INFO_ICON, COL_INFO_NAME, COL_INFO_REPORT = range(3)

# Used as a decorator to run things in the background
def async(func):
    def wrapper(*args, **kwargs):
        thread = threading.Thread(target=func, args=args, kwargs=kwargs)
        thread.daemon = True
        thread.start()
        return thread
    return wrapper

# Used as a decorator to run things in the main loop, from another thread
def idle(func):
    def wrapper(*args):
        GObject.idle_add(func, *args)
    return wrapper

class InfoReport():
    def __init__(self, path, environment):
        sys.path.insert(0, path)
        import MintReportInfo
        imp.reload(MintReportInfo)
        self.report = MintReportInfo.Report(environment)
        sys.path.remove(path)
        self.path = path
        self.environment = environment

    def load_metadata(self):
        with open(os.path.join(self.path, 'metadata.json')) as metadata_file:
            self.metadata = json.load(metadata_file)
        self.uuid = self.metadata["uuid"]
        self.name = self.metadata["name"]
        for prop in ("name[%s]" % self.environment.language, "name[%s]" % self.environment.locale):
            try:
                self.name = self.metadata[prop]
            except:
                pass
        self.icon = self.environment.info_icon
        if self.metadata["type"] == "warning":
            self.icon = self.environment.warning_icon
        elif self.metadata["type"] == "error":
            self.icon = self.environment.error_icon
        elif self.metadata["type"] == "question":
            self.icon = self.environment.question_icon

class MintReport():

    def __init__(self):

        self.environment = environment.Environment()
        self.settings = Gio.Settings("com.linuxmint.report")

        self.cache = apt.Cache()
        # Set the Glade file
        gladefile = "/usr/share/linuxmint/mintreport/mintreport.ui"
        self.builder = Gtk.Builder()
        self.builder.add_from_file(gladefile)
        self.window = self.builder.get_object("main_window")
        self.window.set_title(_("System Reports"))
        self.window.set_icon_name("mintreport")
        self.window.connect("delete_event", Gtk.main_quit)

        self.stack = self.builder.get_object("crash_stack")
        self.spinner = self.builder.get_object("crash_spinner")

        # the crashes treeview
        self.treeview_crashes = self.builder.get_object("treeview_crashes")

        column = Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=COL_CRASH_DATE)
        column.set_sort_column_id(COL_CRASH_TIMESTAMP)
        column.set_resizable(True)
        self.treeview_crashes.append_column(column)
        column = Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=COL_CRASH_FILENAME)
        column.set_sort_column_id(COL_CRASH_FILENAME)
        column.set_resizable(True)
        self.treeview_crashes.append_column(column)
        self.treeview_crashes.show()
        self.model_crashes = Gtk.TreeStore(float, str, str) # timestamp, readable date, filename
        self.model_crashes.set_sort_column_id(COL_CRASH_TIMESTAMP, Gtk.SortType.DESCENDING)
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
        self.delete_button = self.builder.get_object("button_delete")

        self.localfiles_button.connect("clicked", self.on_button_browse_crash_report_clicked)
        self.bugtracker_button.connect("clicked", self.on_button_open_bugtracker_clicked)
        self.pastebin_button.connect("clicked", self.on_button_pastebin_clicked)
        self.delete_button.connect("clicked", self.on_button_delete_clicked)

        # the info treeview
        self.treeview_info = self.builder.get_object("treeview_info")
        renderer = Gtk.CellRendererPixbuf()
        column = Gtk.TreeViewColumn("", renderer)
        column.add_attribute(renderer, "pixbuf", COL_INFO_ICON)
        self.treeview_info.append_column(column)

        column = Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=COL_INFO_NAME)
        column.set_sort_column_id(COL_INFO_NAME)
        column.set_resizable(True)
        self.treeview_info.append_column(column)
        self.treeview_info.show()
        self.model_info = Gtk.TreeStore(GdkPixbuf.Pixbuf, str, object) # icon, name, report
        self.model_info.set_sort_column_id(COL_INFO_NAME, Gtk.SortType.ASCENDING)
        self.treeview_info.set_model(self.model_info)

        self.infoview = None # Don't load webkit view just yet

        self.treeview_info.get_selection().connect("changed", self.on_info_selected)

        self.delete_info_button = self.builder.get_object("button_delete_info")
        self.delete_info_button.connect("clicked", self.on_button_delete_info_clicked)

        self.load_crashes()

        self.load_info()

        self.window.show_all()

    @idle
    def add_report_to_treeview(self, report):
        iter = self.model_info.insert_before(None, None)
        self.model_info.set_value(iter, COL_INFO_ICON, report.icon)
        self.model_info.set_value(iter, COL_INFO_NAME, report.name)
        self.model_info.set_value(iter, COL_INFO_REPORT, report)

    @idle
    def clear_info_treeview(self):
        self.model_info.clear()
        self.infoview.load_html_string('', '')

    @async
    def load_info(self):
        self.loading = True
        self.info_reports = []
        self.clear_info_treeview()

        for dir_name in os.listdir(INFO_DIR):
            path = os.path.join(INFO_DIR, dir_name)
            try:
                report = InfoReport(path, self.environment)
                self.info_reports.append(report)
            except Exception as e:
                print("Failed to load report %s: \n%s\n" % (dir_name, e))

        for report in self.info_reports:
            report.load_metadata()
            if report.uuid not in self.settings.get_strv("deleted-reports") and report.report.is_pertinent():
                self.add_report_to_treeview(report)
        self.loading = False

    def on_info_selected(self, selection):
        if self.loading:
            return
        if self.infoview is None:
            self.infoview = WebKit.WebView()
            self.infoview.set_zoom_level(0.9)
            self.infoview.set_full_content_zoom(True)
            # kill right click menus in webkit views
            self.infoview.connect("button-press-event", lambda w, e: e.button == 3)
            self.infoview.connect("navigation-requested", self.on_link_clicked)
            self.builder.get_object("scrolledwindow_info").add(self.infoview)
            self.infoview.show()

        model, iter = selection.get_selected()
        if iter is not None:
            report = model.get_value(iter, COL_INFO_REPORT)
            content = os.path.join(report.path, "content.html")
            if os.path.exists(content):
                self.infoview.open("file://%s" % content)
            else:
                print("Could not find %s" % content)

    def on_button_delete_info_clicked(self, button):
        model, iter = self.treeview_info.get_selection().get_selected()
        if iter is not None:
            report = model.get_value(iter, COL_INFO_REPORT)
            dialog = Gtk.MessageDialog(self.window, 0, Gtk.MessageType.QUESTION, Gtk.ButtonsType.OK_CANCEL, _("Are you sure you want to delete this report?"))
            dialog.format_secondary_text(_("The report will be permanently deleted and will no longer be visible."))
            response = dialog.run()
            dialog.destroy()

            if response == Gtk.ResponseType.OK:
                deleted_reports = self.settings.get_strv("deleted-reports")
                if report.uuid not in deleted_reports:
                    deleted_reports.append(report.uuid)
                    self.settings.set_strv("deleted-reports", deleted_reports)
                    self.load_info()

    def on_link_clicked(self, view, frame, request, data=None):
        uri = request.get_uri()
        scheme, path = uri.split('://', 1)
        if scheme == 'file':
            return False
        elif scheme == 'launch':
            command = path.split("%20")
            subprocess.Popen(command)
            return True
        else:
            subprocess.Popen(["xdg-open", uri])
            return True

    def load_crashes(self):
        self.loading = True
        self.model_crashes.clear()
        if os.path.exists(CRASH_DIR):
            for file in os.listdir(CRASH_DIR):
                if file.endswith(".crash"):
                    if "apport" not in file:
                        iter = self.model_crashes.insert_before(None, None)
                        mtime = os.path.getmtime(os.path.join(CRASH_DIR, file))
                        readable_date = time.ctime(mtime)
                        self.model_crashes.set_value(iter, COL_CRASH_TIMESTAMP, mtime)
                        self.model_crashes.set_value(iter, COL_CRASH_DATE, readable_date)
                        self.model_crashes.set_value(iter, COL_CRASH_FILENAME, file)
        self.loading = False

    def on_crash_selected(self, selection):
        if self.loading:
            return
        self.stack.set_visible_child_name("page0")
        self.spinner.start()
        self.spinner.show()
        self.treeview_crashes.set_sensitive(False)
        self.localfiles_button.set_sensitive(False)
        self.bugtracker_button.set_sensitive(False)
        self.pastebin_button.set_sensitive(False)
        self.delete_button.set_sensitive(False)
        self.buffer.set_language(self.language_manager.get_language(""))
        self.buffer.set_text("")
        os.system("rm -rf %s/*" % UNPACK_DIR)
        model, iter = selection.get_selected()
        if iter is not None:
            file = os.path.join(CRASH_DIR, model.get_value(iter, COL_CRASH_FILENAME))
            if os.path.exists(file):
                self.unpack_crash_report(file)

    @async
    def unpack_crash_report(self, file):

        if not os.access(file , os.R_OK):
            self.buffer.set_text(_("The file %s could not be read.\nPlease fix its permissions.") % file)
            self.on_unpack_crash_report_finished()
            return

        subprocess.call(["apport-unpack", file, UNPACK_DIR])
        os.chdir(UNPACK_DIR)

        # Add info about the Linux Mint release
        if os.path.exists("/etc/linuxmint/info"):
            shutil.copyfile("/etc/linuxmint/info", "LinuxMintInfo")

        # Produce an Inxi report
        if os.path.exists("/usr/bin/inxi"):
            with open("Inxi", "w") as f:
                subprocess.call(['inxi', '-Fxxrzc0'], stdout=f)

        # Produce a list of installed packages
        with open("Packages", "w") as f:
            subprocess.call(['dpkg', '-l'], stdout=f)

        executable_path = ""
        if os.path.exists("ExecutablePath"):
            with open("ExecutablePath") as f:
                executable_path = f.readlines()[0]

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

                if "mate" in output or output in ["caja", "atril", "pluma", "engrampa", "eog"]:
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

        # Produce a stack trace
        if os.path.exists("CoreDump"):
            os.system("echo '===================================================================' > StackTrace")
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
            self.trace = "StackTrace"
            language = "gdb-log"
        elif os.path.exists("Traceback"):
            self.trace = "Traceback"
            language = "python"
        else:
            self.trace = None
            language = None

        if self.trace is not None:
            with open(self.trace) as f:
                text = f.read()
                if "is not at the expected address (wrong library or version mismatch" in text:
                    self.buffer.set_text(_("The headers or binaries installed on your system do not match the code which was executed during the crash.\nThey probably got upgraded since.\nA stack trace is available in 'Local Files' but its content is probably inaccurate."))
                else:
                    self.show_stack_trace(text, language)

        # Archive the crash report - exclude the CoreDump as it can be very big (close to 1GB)
        os.chdir(TMP_DIR)
        subprocess.call(["tar", "caf", CRASH_ARCHIVE, "crash", "--exclude", "CoreDump"])

        self.on_unpack_crash_report_finished()

    @idle
    def on_unpack_crash_report_finished(self):
        self.treeview_crashes.set_sensitive(True)
        self.localfiles_button.set_sensitive(True)
        self.delete_button.set_sensitive(True)
        self.spinner.stop()
        self.stack.set_visible_child_name("page1")

    @idle
    def show_stack_trace(self, text, language):
        if language is not None:
            self.buffer.set_language(self.language_manager.get_language(language))
        self.buffer.set_text(text)
        self.bugtracker_button.set_sensitive(True)
        self.pastebin_button.set_sensitive(True)

    def on_button_delete_clicked(self, button):
        model, iter = self.treeview_crashes.get_selection().get_selected()
        if iter is not None:
            file = os.path.join(CRASH_DIR, model.get_value(iter, COL_CRASH_FILENAME))
            if os.path.exists(file):
                if os.access(CRASH_DIR, os.W_OK) and os.access(file, os.W_OK):
                    os.remove(file)
                    self.buffer.set_text("")
                    self.delete_button.set_sensitive(False)
                    self.load_crashes()
                else:
                    # Show an error message
                    dialog = Gtk.MessageDialog(self.window, 0, Gtk.MessageType.ERROR, Gtk.ButtonsType.CANCEL, _("The report could not be deleted."))
                    dialog.format_secondary_text(_("Check the permissions for /var/crash and %s.") % file)
                    dialog.run()
                    dialog.destroy()

    def on_button_browse_crash_report_clicked(self, button):
        os.system("xdg-open %s" % TMP_DIR)

    def on_button_open_bugtracker_clicked(self, button):
        os.system("xdg-open %s" % self.bugtracker)

    def on_button_pastebin_clicked(self, button):
        if self.trace is not None:
            pastebin = subprocess.Popen(['/usr/bin/pastebin', os.path.join(UNPACK_DIR, self.trace)], stdout=subprocess.PIPE)
            output = pastebin.communicate()[0]
            output = output.split()[0] # if we have more than one URL, only use the first one
            pastebin.wait()
            subprocess.call(['xdg-open', output])

if __name__ == "__main__":
    os.system("mkdir -p %s" % UNPACK_DIR)
    MintReport()
    Gtk.main()
