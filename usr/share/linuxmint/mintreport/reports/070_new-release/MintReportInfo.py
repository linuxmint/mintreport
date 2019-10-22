import configparser
import os
import subprocess
import gettext
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from mintreport import InfoReport, InfoReportAction

class Report(InfoReport):

    def __init__(self):

        gettext.install("mintreport", "/usr/share/locale", names="ngettext")

        self.title = _("A new version of Linux Mint is available")
        self.icon = "mintupdate-type-package-symbolic"
        self.has_ignore_button = True

    def is_pertinent(self):
        # Defines whether this report should show up
        self.rel_target = None
        rel_edition = None
        rel_codename = None
        if os.path.exists("/etc/linuxmint/info"):
            with open("/etc/linuxmint/info", encoding="utf-8") as info:
                for line in info:
                    line = line.strip()
                    if "EDITION=" in line:
                        rel_edition = line.split('=')[1].replace('"', '').split()[0]
                    if "CODENAME=" in line:
                        rel_codename = line.split('=')[1].replace('"', '').split()[0]
        if rel_edition is not None and rel_codename is not None:
            rel_path = "/usr/share/mint-upgrade-info/%s/info" % rel_codename
            if os.path.exists(rel_path):
                config = configparser.ConfigParser()
                config.read(rel_path)
                if rel_edition.lower() in config['general']['editions']:
                    self.rel_target = config['general']['target_name']
                    return True
        return False

    def get_descriptions(self):
        # Return the descriptions
        descriptions = []
        descriptions.append(_("Visit %s for the latest announcements.") % "<a href='https://blog.linuxmint.com'>https://blog.linuxmint.com</a>")
        return descriptions

    def get_actions(self):
        # Return available actions
        actions = []
        action = InfoReportAction(label=_("Upgrade to %s") % self.rel_target, callback=self.callback)
        action.set_style(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
        actions.append(action)
        return actions

    def callback(self, data):
        subprocess.run(["/usr/bin/mint-release-upgrade"])
        # reload
        return True

if __name__ == "__main__":
    report = Report()
    print(report.is_pertinent())
