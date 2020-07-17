import gettext
import gi
import pwd
import os
import subprocess

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from mintreport import InfoReport, InfoReportAction

class Report(InfoReport):

    def __init__(self):

        gettext.install("mintreport", "/usr/share/locale", names="ngettext")

        self.title = _("Correct file ownership problem")
        self.icon = "mintreport-symbolic"
        self.has_ignore_button = True
        self.files = ""

    def is_pertinent(self):
        # Defines whether this report should show up
        result = subprocess.run(["/usr/bin/find", os.path.expanduser("~"),
                                 "-maxdepth", "1",
                                 "-name", ".*",
                                 "-type", "f",
                                 "-user", "root"
                                ], capture_output=True, text=True)
        self.files += result.stdout
        result = subprocess.run(["/usr/bin/find", os.path.join(os.path.expanduser("~"), ".config"), 
                                                  os.path.join(os.path.expanduser("~"), ".local"),
                                 "-user", "root",
                                 "(", "-name", "Steam", "-prune", "-o", "-print", ")",
                                ], capture_output=True, text=True)
        self.files += result.stdout
        return (len(self.files) > 0)

    def get_descriptions(self):
        # Return the descriptions
        descriptions = []
        descriptions.append(_("These files or directories are owned by root but should be owned by you:"))
        descriptions.append(self.files)
        return descriptions

    def get_actions(self):
        # Return available actions
        actions = []
        action = InfoReportAction(label=_("Restore ownership to yourself"),
                                  callback=self.callback)
        action.set_style(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
        actions.append(action)
        return actions

    def callback(self, data):
        subprocess.run(["/usr/bin/pkexec", "/bin/chown", "-R", "--from=root", "{}:".format(pwd.getpwuid(os.getuid()).pw_name), os.path.expanduser("~")])
        # Reload
        return True

if __name__ == "__main__":
    report = Report()
    print(report.is_pertinent())
