import os
import subprocess
import gettext
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('XApp', '1.0')
from gi.repository import Gtk, XApp

from mintreport import InfoReport, InfoReportAction

class Report(InfoReport):

    def __init__(self):

        gettext.install("mintreport", "/usr/share/locale", names="ngettext")

        self.title = _("Add the XApp Status applet")
        self.icon = "mintreport-symbolic"
        self.has_ignore_button = True
        self.de = os.getenv("XDG_CURRENT_DESKTOP")

    def is_pertinent(self):
        # Defines whether this report should show up
        if not hasattr(XApp, 'StatusIcon'):
            return False

        if self.de is None:
            return False
        else:
            self.de = self.de.lower()

        return not XApp.StatusIcon.any_monitors()

    def get_descriptions(self):
        # Return the descriptions
        descriptions = []
        descriptions.append(_("The XApp Status applet allows applications to provide a tray icon without rendering glitches and with support for HiDPI and symbolic icons."))
        if self.de == "mate":
            descriptions.append(_("Right-click the panel and choose 'Add to Panel'."))
        return descriptions

    def get_actions(self):
        # Return available actions
        actions = []
        if "cinnamon" in self.de or "xfce" in self.de:
            action = InfoReportAction(label=_("Add the XApp Status applet to the panel"), callback=self.callback)
            action.set_style(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
            actions.append(action)
        return actions

    def callback(self, data):
        if "cinnamon" in self.de:
            subprocess.run(["cinnamon-settings", "applets"])
        elif "xfce" in self.de:
            subprocess.run(["xfce4-panel", "-a"])
        # reload
        return True

if __name__ == "__main__":
    report = Report()
    print(report.is_pertinent())
