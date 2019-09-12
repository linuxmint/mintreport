import os
import subprocess
import gettext

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from mintreport import InfoReport, InfoReportAction

class Report(InfoReport):

    def __init__(self):

        gettext.install("mintreport", "/usr/share/linuxmint/locale", names="ngettext")

        self.title = _("Set up a root password")
        self.icon = "security-high-symbolic"
        self.has_ignore_button = True

    def is_pertinent(self):
        # Defines whether this report should show up
        return True

    def get_descriptions(self):
        # Return the descriptions
        descriptions = []
        descriptions.append(_("By default, the root account has no password.. blah blah blah..."))
        return descriptions

# pros
#
# nobody remote can get in

# cons
#
# Emergency mode is locked
# 

    def get_actions(self):
        # Return available actions
        actions = []
        return actions

if __name__ == "__main__":
    report = Report()
    print(report.is_pertinent())
