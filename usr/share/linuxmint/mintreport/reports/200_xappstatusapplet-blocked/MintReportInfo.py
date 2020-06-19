import os
import subprocess
import gettext
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('XApp', '1.0')
from gi.repository import Gtk, XApp, GLib

from mintreport import InfoReport, InfoReportAction

class Report(InfoReport):

    def __init__(self):

        gettext.install("mintreport", "/usr/share/locale", names="ngettext")

        self.title = _("Remove conflicting indicators")
        self.icon = "mintreport-symbolic"
        self.has_ignore_button = True
        self.indicator_path = None
        self.indicator_pkgname = None
        self.indicators = []
        self.indicators.append(["indicator-application", "/usr/lib/systemd/user/indicator-application.service"])
        self.indicators.append(["ayatana-indicator-application", "/usr/lib/systemd/user/ayatana-indicator-application.service"])
        self.packages = []

    def is_pertinent(self):
        # Defines whether this report should show up
        for name, path in self.indicators:
            if os.path.exists(path):
                self.packages.append(name)
        return (len(self.packages) > 0)

    def get_descriptions(self):
        # Return the descriptions
        descriptions = []
        descriptions.append(_("The following packages prevent tray icons from working properly:"))
        descriptions.append("\n".join(self.packages))
        descriptions.append(_("Note: You will need to log out after removing them."))
        return descriptions

    def get_actions(self):
        # Return available actions
        actions = []
        action = InfoReportAction(label=_("Remove the conflicting packages."),
                                  callback=self.callback)
        action.set_style(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
        actions.append(action)
        return actions

    def callback(self, data):
        self.remove_packages(self.packages)
        return True

if __name__ == "__main__":
    report = Report()
    print(report.is_pertinent())
