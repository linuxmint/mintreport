import gettext
import gi
import subprocess

from gi.repository import Gio
from mintreport import InfoReport, InfoReportAction

class Report(InfoReport):

    def __init__(self):

        gettext.install("mintreport", "/usr/share/locale", names="ngettext")

        self.title = _("Set the root password")
        self.icon = "security-high-symbolic"
        self.has_ignore_button = False
        self.settings = Gio.Settings("com.linuxmint.report")
        self.report_id = "root-password-not-set"

    def is_pertinent(self):
        # Defines whether this report should show up
        return True

    def get_descriptions(self):
        # Return the descriptions
        descriptions = []
        descriptions.append(_("The root account is locked by default in Linux Mint and its password is not set."))
        release_info = subprocess.run(["lsb_release", "-irs"], stdout=subprocess.PIPE).stdout.decode().split("\n")
        if release_info[0] == "LinuxMint" and float(release_info[1]) >= 13:
            # Mint
            descriptions.append(_("Your boot menu's emergency mode does not require a password. Set the root password to protect it."))
        else:
            # LMDE
            descriptions.append(_("Your boot menu's emergency mode requires a password which isn't set. Set the root password to fix it."))
        descriptions.append("")
        descriptions.append(_("To set the root password, open a terminal and type:"))
        descriptions.append("<b>sudo passwd root</b>")
        descriptions.append("")
        descriptions.append("<i>%s</i>" % _("Disclaimer: Proper security can only be achieved by restricting physical access to your computer and encrypting your data. BIOS passwords can be reset and your root account can be accessed without a password by booting another operating system."))

        return descriptions

    def get_actions(self):
        # Return available actions
        actions = []
        action = InfoReportAction(label=_("I understand"), callback=self.callback)
        action.set_style(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
        actions.append(action)
        return actions

    def callback(self, data):
        ignored_uuids = self.settings.get_strv("ignored-reports")
        if self.report_id not in ignored_uuids:
            ignored_uuids.append(self.report_id)
            self.settings.set_strv("ignored-reports", ignored_uuids)
        # reload
        return True

if __name__ == "__main__":
    report = Report()
    print(report.is_pertinent())
