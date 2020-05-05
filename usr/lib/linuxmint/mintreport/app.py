#!/usr/bin/python3
import apt
import datetime
import gettext
import gi
import locale
import os
import setproctitle
import shutil
import subprocess

gi.require_version("Gtk", "3.0")
gi.require_version('GtkSource', '3.0')
gi.require_version('XApp', '1.0')
from gi.repository import Gtk, Gdk, GtkSource, Gio, XApp

from common import _async, idle, InfoReportContainer, DATA_DIR, INFO_DIR

setproctitle.setproctitle("mintreport")

# i18n
APP = 'mintreport'
LOCALE_DIR = "/usr/share/locale"
locale.bindtextdomain(APP, LOCALE_DIR)
gettext.bindtextdomain(APP, LOCALE_DIR)
gettext.textdomain(APP)
_ = gettext.gettext

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

    def activate(self, application):
        windows = self.get_windows()
        if (len(windows) > 0):
            window = windows[0]
            window.present()
            window.show_all()
        else:
            window = MintReportWindow(self)
            self.add_window(window.window)
            window.window.show_all()

class MintReportWindow():

    def __init__(self, application):

        self.application = application
        self.settings = Gio.Settings(schema_id="com.linuxmint.report")

        os.system("mkdir -p %s" % TMP_DIR)
        os.system("rm -rf %s/*" % TMP_DIR)
        os.system("mkdir -p %s" % UNPACK_DIR)
        os.system("cp -R %s/* %s/" % (DATA_DIR, TMP_DIR))

        self._cache = None
        # Set the Glade file
        gladefile = "/usr/share/linuxmint/mintreport/mintreport.ui"
        self.builder = Gtk.Builder()
        self.builder.set_translation_domain(APP)
        self.builder.add_from_file(gladefile)
        self.window = self.builder.get_object("main_window")
        self.window.set_title(_("System Reports"))
        self.window.set_icon_name("mintreport")

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

        column = Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=COL_INFO_TITLE)
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

        self.load_info()

        accel_group = Gtk.AccelGroup()
        self.window.add_accel_group(accel_group)

        # Menubar
        menubar = self.builder.get_object("menubar")
        menu = Gtk.MenuItem.new_with_mnemonic(_("_File"))
        menubar.append(menu)
        submenu = Gtk.Menu()
        menu.set_submenu(submenu)

        item = Gtk.ImageMenuItem(label=_("Refresh"))
        image = Gtk.Image.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.MENU)
        item.set_image(image)
        item.connect('activate', self.on_menu_refresh)
        key, mod = Gtk.accelerator_parse("<Control>R")
        item.add_accelerator("activate", accel_group, key, mod, Gtk.AccelFlags.VISIBLE)
        submenu.append(item)
        item = Gtk.ImageMenuItem(label=_("Restore ignored reports"))
        item.connect('activate', self.on_menu_restore)
        submenu.append(item)
        submenu.append(Gtk.SeparatorMenuItem())
        item = Gtk.ImageMenuItem(label=_("Quit"))
        image = Gtk.Image.new_from_icon_name("application-exit-symbolic", Gtk.IconSize.MENU)
        item.set_image(image)
        item.connect('activate', self.on_menu_quit)
        key, mod = Gtk.accelerator_parse("<Control>Q")
        item.add_accelerator("activate", accel_group, key, mod, Gtk.AccelFlags.VISIBLE)
        key, mod = Gtk.accelerator_parse("<Control>W")
        item.add_accelerator("activate", accel_group, key, mod, Gtk.AccelFlags.VISIBLE)
        submenu.append(item)
        menubar.show_all()

        menu = Gtk.MenuItem.new_with_mnemonic(_("_Help"))
        menubar.append(menu)
        submenu = Gtk.Menu()
        menu.set_submenu(submenu)
        item = Gtk.ImageMenuItem()
        item.set_image(Gtk.Image.new_from_icon_name("help-about-symbolic", Gtk.IconSize.MENU))
        item.set_label(_("About"))
        item.connect("activate", self.open_about)
        submenu.append(item)

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
        dlg.set_program_name("mintReport")
        dlg.set_comments(_("System Reports"))
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
        self.load_info()

    def on_menu_refresh(self, widget):
        self.load_info()
        self.load_sysinfo()
        self.load_crashes()

    def on_menu_quit(self, widget):
        self.application.quit()

    @_async
    def load_sysinfo(self):
        try:
            sysinfo = subprocess.check_output("LANG=C inxi -Fxxrzc0 --usb", shell=True).decode("UTF-8")
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
        clipboard.set_text("[code]\n%s[/code]\n" % text, -1)
        subprocess.Popen(['notify-send', '-i', 'dialog-information-symbolic', _("System information copied"), _("Your system information was copied into your clipboard so you can paste it on the forums.")])

    def upload_sysinfo(self, button):
        try:
            output = subprocess.check_output("pastebin %s" % TMP_INXI_FILE, shell=True).decode("UTF-8")
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
        self.model_info.set_value(iter, COL_INFO_ICON, report.instance.icon)
        self.model_info.set_value(iter, COL_INFO_TITLE, report.instance.title)
        self.model_info.set_value(iter, COL_INFO_REPORT, report)

    @idle
    def clear_info_treeview(self):
        self.model_info.clear()
        self.builder.get_object("info_box").hide()

    @idle
    def show_info_spinner(self):
        self.builder.get_object("box_info_stack").set_visible_child_name("spinner")
        self.builder.get_object("info_spinner").start()

    @idle
    def show_info_reports(self):
        if self.num_info_found > 0:
            self.builder.get_object("box_info_stack").set_visible_child_name("reports")
            iter_first = self.model_info.get_iter_first()
            if iter_first is not None:
                self.treeview_info.get_selection().select_iter(iter_first)
        else:
            self.builder.get_object("box_info_stack").set_visible_child_name("done")
        self.builder.get_object("info_spinner").stop()

    @_async
    def load_info(self):
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
                button = Gtk.Button(label=_("Ignore this problem"))
                button.connect("clicked", self.on_ignore_button_clicked)
                self.info_button_box.add(button)
            self.builder.get_object("info_box").show_all()

    def on_info_action_clicked(self, button, callback, data):
        self.window.set_sensitive(False)
        reload_requested = callback(data)
        if reload_requested:
            self.load_info()
        self.window.set_sensitive(True)

    def on_ignore_button_clicked(self, button):
            model, iter = self.treeview_info.get_selection().get_selected()
            if iter is not None:
                report = model.get_value(iter, COL_INFO_REPORT)
                dialog = Gtk.MessageDialog(self.window, 0, Gtk.MessageType.QUESTION, Gtk.ButtonsType.OK_CANCEL, _("Are you sure you want to ignore this problem?"))
                dialog.format_secondary_text(_("The problem will be permanently ignored and will no longer be visible."))
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

    @idle
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

    @_async
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
    application = MyApplication("com.linuxmint.reports", Gio.ApplicationFlags.FLAGS_NONE)
    application.run()
