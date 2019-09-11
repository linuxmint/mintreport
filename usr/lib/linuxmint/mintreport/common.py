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

DATA_DIR = "/usr/share/linuxmint/mintreport"
INFO_DIR = os.path.join(DATA_DIR, "reports")
TMP_DIR = "/tmp/mintreport"

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
    def __init__(self, path):
        self.path = path
        sys.path.insert(0, path)
        import MintReportInfo
        imp.reload(MintReportInfo)
        self.instance = MintReportInfo.Report()
        sys.path.remove(path)

