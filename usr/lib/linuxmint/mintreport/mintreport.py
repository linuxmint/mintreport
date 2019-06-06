#!/usr/bin/python3

import apt
import os
import sys
import gettext
import gi
gi.require_version("Gtk", "3.0")
gi.require_version('GtkSource', '3.0')
gi.require_version('WebKit', '3.0')
gi.require_version('XApp', '1.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GtkSource, GObject, WebKit, Gio, XApp
import subprocess
import shutil
import time
import datetime
import setproctitle
import threading
setproctitle.setproctitle("mintreport")
import locale
import imp
import json

import environment

# i18n
APP = 'mintreport'
LOCALE_DIR = "/usr/share/linuxmint/locale"
locale.bindtextdomain(APP, LOCALE_DIR)
gettext.bindtextdomain(APP, LOCALE_DIR)
gettext.textdomain(APP)
_ = gettext.gettext

DATA_DIR = "/usr/share/linuxmint/mintreport"
INFO_DIR = os.path.join(DATA_DIR, "reports")
TMP_DIR = "/tmp/mintreport"
TMP_INFO_DIR = os.path.join(TMP_DIR, "reports")
TMP_INXI_FILE = os.path.join(TMP_DIR, "inxi")

UNPACK_DIR = os.path.join(TMP_DIR, "crash")
CRASH_ARCHIVE = os.path.join(TMP_DIR, "crash.tar.gz")


COL_CRASH_DAY, COL_CRASH_DATE, COL_CRASH_TIME, COL_CRASH_TIMEZONE, COL_CRASH_PID, COL_CRASH_EXE, COL_CRASH_OBJECT = range(7)

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

class CrashReport():

    def __init__(self, timestamp, pid, sig, executable):
        self.timestamp = timestamp
        self.pid = pid
        self.sig = sig
        self.executable = executable

class MintReport():

    def __init__(self):

        self.environment = environment.Environment()
        self.settings = Gio.Settings("com.linuxmint.report")

        os.system("mkdir -p %s" % TMP_DIR)
        os.system("rm -rf %s/*" % TMP_DIR)
        os.system("mkdir -p %s" % UNPACK_DIR)
        os.system("cp -R %s/* %s/" % (DATA_DIR, TMP_DIR))

        self.cache = apt.Cache()
        # Set the Glade file
        gladefile = "/usr/share/linuxmint/mintreport/mintreport.ui"
        self.builder = Gtk.Builder()
        self.builder.set_translation_domain(APP)
        self.builder.add_from_file(gladefile)
        self.window = self.builder.get_object("main_window")
        self.window.set_title(_("System Reports"))
        self.window.set_icon_name("mintreport")
        self.window.connect("delete_event", Gtk.main_quit)

        self.stack = self.builder.get_object("crash_stack")
        self.spinner = self.builder.get_object("crash_spinner")

        # Fill in the sysinfo pane
        self.load_sysinfo()
        self.builder.get_object("button_sysinfo_copy").connect("clicked", self.copy_sysinfo)
        self.builder.get_object("button_sysinfo_upload").connect("clicked", self.upload_sysinfo)

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
        self.model_sort = self.model_crashes.sort_new_with_model()
        self.model_sort.set_sort_func(COL_CRASH_DATE, sort_by_date)
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

        if os.path.exists("/usr/bin/coredumpctl"):
            self.builder.get_object("crash_internal_stack").set_visible_child_name("page_reports")
            self.load_crashes()
        else:
            self.builder.get_object("crash_internal_stack").set_visible_child_name("page_error")

        self.load_info()

        self.window.show_all()

    @async
    def load_sysinfo(self):
        try:
            sysinfo = subprocess.check_output("LANG=C inxi -Fxxrzc0 --usb", encoding='UTF-8', shell=True)
            self.add_sysinfo_to_textview(sysinfo)
            with open(TMP_INXI_FILE, "w") as f:
                f.write(sysinfo)
        except Exception as e:
            subprocess.Popen(['notify-send', '-i', 'dialog-error-symbolic', _("An error occurred while gathering the system information."), str(e)])
            print (e)

    @idle
    def add_sysinfo_to_textview(self, text):
        buff = Gtk.TextBuffer()
        buff.set_text(text)
        self.builder.get_object("textview_sysinfo").set_buffer(buff)

    def copy_sysinfo(self, button):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        buff = self.builder.get_object("textview_sysinfo").get_buffer()
        text = buff.get_text(buff.get_start_iter(), buff.get_end_iter(), False)
        clipboard.set_text(f"[code]\n{text}[/code]\n", -1)
        subprocess.Popen(['notify-send', '-i', 'dialog-information-symbolic', _("System information copied"), _("Your system information was copied into your clipboard so you can paste it on the forums.")])

    def upload_sysinfo(self, button):
        try:
            output = subprocess.check_output("pastebin %s" % TMP_INXI_FILE, encoding='UTF-8', shell=True)
            link = output.rstrip('\x00').strip() # Remove ASCII null termination with \x00
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            buff = self.builder.get_object("textview_sysinfo").get_buffer()
            clipboard.set_text(link, -1)
            subprocess.Popen(['notify-send', '-i', 'dialog-information-symbolic', _("System information uploaded"), _("Your system information was uploaded to %s. This link was placed in your clipboard so you can paste it on IRC.") % link])
        except Exception as e:
            subprocess.Popen(['notify-send', '-i', 'dialog-error-symbolic', _("An error occurred while uploading the system information"), _("Copy and paste the system information manually into a pastebin site like https://pastebin.com and share the link on IRC."), str(e)])

    @idle
    def add_report_to_treeview(self, report):
        iter = self.model_info.insert_before(None, None)
        self.model_info.set_value(iter, COL_INFO_ICON, report.icon)
        self.model_info.set_value(iter, COL_INFO_NAME, report.name)
        self.model_info.set_value(iter, COL_INFO_REPORT, report)
        self.builder.get_object("main_stack").child_set_property(self.builder.get_object("box_info_reports"), 'needs-attention', True)

    @idle
    def clear_info_treeview(self):
        self.model_info.clear()
        if self.infoview is not None:
            self.infoview.load_html_string('', '')
        self.builder.get_object("main_stack").child_set_property(self.builder.get_object("box_info_reports"), 'needs-attention', False)

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
            new_path = report.path.replace(INFO_DIR, TMP_INFO_DIR)
            new_content = os.path.join(new_path, "content.generated")
            if os.path.exists(content):
                if "parse_content" in dir(report.report):
                    with open(content) as c:
                        html = c.read()
                        new_html = report.report.parse_content(html)
                        with open(new_content, "w") as new_c:
                            new_c.write(new_html)
                        self.infoview.open("file://%s" % new_content)
                else:
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
            try:
                command = path.split("%20")
                subprocess.Popen(command)
            except Exception as e:
                print(e)
            return True
        elif scheme == 'install':
            try:
                subprocess.Popen(["apturl", "apt://%s?refresh=yes" % path])
            except Exception as e:
                print(e)
            return True
        else:
            subprocess.Popen(["xdg-open", uri])
            return True

    def load_crashes(self):
        self.loading = True
        self.model_crashes.clear()

        coredumps = subprocess.run(['coredumpctl', 'list', '--no-legend', '-r', '-q'], stdout=subprocess.PIPE).stdout
        lines = coredumps.decode('utf-8').split('\n')
        for line in lines:
            # Ignore empty lines
            if not line.strip():
                continue
            line = " ".join(line.split()) # remove blank spaces between fields in the coredumpctl output
            try:
                (day, date, time, timezone, pid, uid, gid, sig, corefile, exe) = line.split(" ", 10)
            except:
                print("coredumpctl output: '%s' could not be split" % line)
                continue
            # Ignore python crashes, we don't handle tracebacks with systemd-coredump yet
            if "python" in exe:
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
        self.stack.set_visible_child_name("page0")
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

    @async
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

    @idle
    def on_unpack_crash_report_finished(self):
        self.treeview_crashes.set_sensitive(True)
        self.localfiles_button.set_sensitive(True)
        self.spinner.stop()
        self.stack.set_visible_child_name("page1")

    @idle
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
    MintReport()
    Gtk.main()
