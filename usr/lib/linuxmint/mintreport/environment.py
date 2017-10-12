#!/usr/bin/python3

import os
import xapp.os
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

class Environment():

    def __init__(self):
        # Current desktop
        self.desktop = xapp.os.get_current_desktop()
        self.is_lmde = os.path.exists("/usr/share/doc/debian-system-adjustments/copyright")

        # Current locale
        self.locale = ""
        self.language = ""
        try:
            self.locale = os.getenv('LANGUAGE').split(".")[0]
            self.language = self.locale.split("_")[0]
        except:
            pass

        # Icons
        self.iconTheme = Gtk.IconTheme.get_default()
        self.info_icon = self.iconTheme.load_icon("dialog-information-symbolic", 16, 0)
        self.warning_icon = self.iconTheme.load_icon("dialog-warning-symbolic", 16, 0)
        self.error_icon = self.iconTheme.load_icon("dialog-error-symbolic", 16, 0)
        self.question_icon = self.iconTheme.load_icon("dialog-question-symbolic", 16, 0)