#!/usr/bin/python3

import os
import re
import sys
import gettext
import fileinput
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk
import subprocess
import shutil
import time

# i18n
gettext.install("mintreport", "/usr/share/linuxmint/locale")

CRASH_DIR = "/var/crash"

TMP_DIR = "/tmp/mintreport"
UNPACK_DIR = os.path.join(TMP_DIR, "crash")
CRASH_ARCHIVE = os.path.join(TMP_DIR, "crash.tar.gz")

class MintReport():

    def __init__(self):
        # Set the Glade file
        gladefile = "/usr/share/linuxmint/mintreport/mintreport.ui"
        builder = Gtk.Builder()
        builder.add_from_file(gladefile)
        self.window = builder.get_object("main_window")
        self.window.set_title(_("System Reports"))
        self.window.set_icon_name("mintreport")
        self.window.connect("delete_event", Gtk.main_quit)

        # the treeview
        self.treeview_crashes = builder.get_object("treeview_crashes")

        column = Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=0)
        column.set_sort_column_id(0)
        column.set_resizable(True)
        self.treeview_crashes.append_column(column)
        column = Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=1)
        column.set_sort_column_id(1)
        column.set_resizable(True)
        self.treeview_crashes.append_column(column)
        self.treeview_crashes.show()
        self.model_crashes = Gtk.TreeStore(str, str)
        self.model_crashes.set_sort_column_id(0, Gtk.SortType.DESCENDING)
        self.treeview_crashes.set_model(self.model_crashes)

        self.load_crashes()

        self.textview = builder.get_object("textview_crash")

        self.treeview_crashes.get_selection().connect("changed", self.on_crash_selected)

        builder.get_object("button_browse_crash_report").connect("clicked", self.on_button_browse_crash_report_clicked)

        self.window.show_all()

    def load_crashes(self):
        self.model_crashes.clear()
        if os.path.exists(CRASH_DIR):
            for file in os.listdir(CRASH_DIR):
                if file.endswith(".crash"):
                    if ".py" in file or "apport" in file or "mintreport" in file:
                        continue
                    iter = self.model_crashes.insert_before(None, None)
                    mtime = time.ctime(os.path.getmtime(os.path.join(CRASH_DIR, file)))
                    self.model_crashes.set_value(iter, 0, mtime)
                    self.model_crashes.set_value(iter, 1, file)

    def on_crash_selected(self, selection):
        os.system("rm -rf %s/*" % UNPACK_DIR)
        model, iter = selection.get_selected()
        file = os.path.join(CRASH_DIR, model.get_value(iter, 1))
        if os.path.exists(file):
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

            # Produce a stack trace
            if os.path.exists("CoreDump") and os.path.exists("ExecutablePath"):
                with open("ExecutablePath") as f:
                    path = f.readlines()[0]
                    os.system("LANG=C gdb %s CoreDump --batch > StackTrace 2>&1" % path)
                    with open("StackTrace") as s:
                        text = s.read()
                        self.textview.get_buffer().set_text(text)

            # Archive the crash report - exclude the CoreDump as it can be very big (close to 1GB)
            os.chdir(TMP_DIR)
            subprocess.call(["tar", "caf", CRASH_ARCHIVE, "crash", "--exclude", "CoreDump"])

    def on_button_browse_crash_report_clicked(self, button):
        os.system("xdg-open %s" % TMP_DIR)

if __name__ == "__main__":
    os.system("mkdir -p %s" % UNPACK_DIR)
    MintReport()
    Gtk.main()
