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

        self.title = _("Remove conflicting status icon handler")
        self.icon = "mintreport-symbolic"
        self.has_ignore_button = True
        self.de = os.getenv("XDG_CURRENT_DESKTOP")
        self.indicator_path = None
        self.indicator_pkgname = None

    def is_pertinent(self):
        # Defines whether this report should show up

        for pkgset in (["indicator-application", "/usr/lib/systemd/user/indicator-application.service"],
                       ["ayatana-indicator-application", "/usr/lib/systemd/user/ayatana-indicator-application.service"]):
            self.indicator_pkgname, self.indicator_path = pkgset
            if os.path.exists(self.indicator_path):
                return True

        return False

    def get_descriptions(self):
        # Return the descriptions
        descriptions = []
        descriptions.append(_("There is a service installed that could be preventing the display of some "  \
                              "status icons. It needs to be removed to restore proper functionality " \
                              "to the panel's status notification applet."))
        descriptions.append(_("\nYou should log out and back in after this has completed."))
        return descriptions

    def get_actions(self):
        # Return available actions
        actions = []
        action = InfoReportAction(label=_("Uninstall the '%s' package.") % self.indicator_pkgname,
                                  callback=self.callback)
        action.set_style(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
        actions.append(action)
        return actions

    def callback(self, data):
        subprocess.run(["mint-remove-application", self.indicator_path])
        return True

if __name__ == "__main__":
    report = Report()
    print(report.is_pertinent())
