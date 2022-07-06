import gi
import mintcommon.aptdaemon

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from abc import ABC, abstractmethod
import time


class InfoReport(ABC):

    def __init__(self):
        self.title = ""
        self.icon = "mintreport-symbolic"
        self.has_ignore_button = False

    @abstractmethod
    def is_pertinent(self):
        pass

    @abstractmethod
    def get_descriptions(self):
        pass

    @abstractmethod
    def get_actions(self):
        pass

    def install_packages(self, package_names):
        self.apt = mintcommon.aptdaemon.APT(None)
        self.package_names = package_names
        self.apt.set_finished_callback(self.on_update_before_install_finished)
        self.apt.update_cache()
        Gtk.main()

    def on_update_before_install_finished(self, transaction=None, exit_state=None):
        self.apt.set_finished_callback(self.on_install_finished)
        self.apt.set_cancelled_callback(self.on_install_finished)
        self.apt.install_packages(self.package_names)

    def on_install_finished(self, transaction=None, exit_state=None):
        del self.package_names
        del self.apt
        Gtk.main_quit()

    def remove_packages(self, package_names):
        self.apt = mintcommon.aptdaemon.APT(None)
        self.package_names = package_names
        self.apt.set_finished_callback(self.on_update_before_remove_finished)
        self.apt.update_cache()
        Gtk.main()

    def on_update_before_remove_finished(self, transaction=None, exit_state=None):
        self.apt.set_finished_callback(self.on_remove_finished)
        self.apt.set_cancelled_callback(self.on_remove_finished)
        self.apt.remove_packages(self.package_names)

    def on_remove_finished(self, transaction=None, exit_state=None):
        del self.package_names
        del self.apt
        Gtk.main_quit()

class InfoReportAction():

    def __init__(self, label, callback, data=None):
        self.label = label
        self.callback = callback
        self.style = None
        self.data = data

    def set_style(self, style):
        self.style = style
