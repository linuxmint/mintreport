import gettext
import subprocess

from mintreport import InfoReport, InfoReportAction

class Report(InfoReport):

    def __init__(self):

        gettext.install("mintreport", "/usr/share/linuxmint/locale", names="ngettext")

        self.title = _("Set the root password")
        self.icon = "security-high-symbolic"
        self.has_ignore_button = True

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
        return actions

if __name__ == "__main__":
    report = Report()
    print(report.is_pertinent())
