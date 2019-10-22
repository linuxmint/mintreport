import gettext
import gi
import os
import subprocess

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from mintreport import InfoReport, InfoReportAction

class Report(InfoReport):

    def __init__(self):

        gettext.install("mintreport", "/usr/share/locale", names="ngettext")

        self.title = _("Set up the system restore utility")
        self.icon = "document-open-recent-symbolic"
        self.has_ignore_button = True

    def is_pertinent(self):
        # Defines whether this report should show up
        if os.path.exists("/usr/bin/timeshift") and not os.path.exists("/etc/timeshift.json"):
            return True
        else:
            return False

    def get_descriptions(self):
        # Return the descriptions
        descriptions = []
        descriptions.append(_("Linux Mint provides a system restore utility called Timeshift."))
        descriptions.append(_("Thanks to Timeshift you can take snapshots of the system, either manually or automatically."))
        descriptions.append(_("If something goes wrong you can then restore your operating system from a previously saved snapshot."))
        return descriptions

    def get_actions(self):
        # Return available actions
        actions = []
        action = InfoReportAction(label=_("Launch Timeshift"), callback=self.launch_timeshift)
        action.set_style(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
        actions.append(action)
        return actions

    def launch_timeshift(self, data):
        subprocess.run(["pkexec", "timeshift-gtk"])
        # reload
        return True

if __name__ == "__main__":
    report = Report()
    print(report.is_pertinent())
