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
        self.icon = "dialog-password-symbolic"
        self.has_ignore_button = True
        self.files = ""

    def is_pertinent(self):
        # Defines whether this report should show up
        result = subprocess.run(["/usr/bin/find", os.path.expanduser("~"),
                                 "-path", os.path.join(os.path.expanduser("~"), ".*"),
                                 "-user", "root"
                                ], capture_output=True, text=True)
        self.files = result.stdout
        return (len(self.files) > 0)

    def get_descriptions(self):
        # Return the descriptions
        descriptions = []
        descriptions.append(_("These hidden files and/or directories are owned by root instead of by you:"))
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
        subprocess.run(["/usr/bin/find", os.path.expanduser("~"),
                        "-path", os.path.join(os.path.expanduser("~"), ".*"),
                        "-user", "root",
                        "-exec", "/usr/bin/pkexec", "/bin/chown", "{}:".format(pwd.getpwuid(os.getuid()).pw_name), "{}", "+",
                       ])
        # Reload
        return True

if __name__ == "__main__":
    report = Report()
    print(report.is_pertinent())
