import gettext
import os
from pathlib import Path
import webbrowser

import lsb_release

from mintreport import InfoReport, InfoReportAction

class Report(InfoReport):

    def __init__(self):

        gettext.install("mintreport", "/usr/share/locale", names="ngettext")

        self.title = _("Perform usrmerge conversion")
        self.icon = "folder-symbolic"
        self.has_ignore_button = True

    def is_pertinent(self):
        try:
            info = lsb_release.get_os_release()

            major_version = info["RELEASE"].split(".")[0]
            if int(major_version) < 20 and "LMDE" not in info["DESCRIPTION"]:
                return False
        except Exception:
            return False

        # from convert-usrmerge script
        directories = ["bin", "sbin", "lib", "libx32", "lib64", "lib32"]

        for dirname in directories:
            link_path = Path(os.path.join("/", dirname))
            target_path = Path(os.path.join("/", "usr", dirname))

            if (not link_path.exists()) and (not target_path.exists()):
                # print(f"skipping: {link_path} (doesn't exist)")
                continue

            # print(f"checking: {link_path} --> {target_path}")

            if not (link_path.is_symlink() and link_path.samefile(target_path)):
                return True
        return False

    def get_descriptions(self):
        # Return the descriptions
        descriptions = [_("We recommend you convert your system with usrmerge."),
        _("This is done already for new installations of Linux Mint, starting with 20.1."),
        _("To convert your system, open a terminal and type:"),
        "\n<span font_family='monospace'>apt install usrmerge</span>\n",
        _("You should reboot the computer once this completes.")]
        return descriptions

    def get_actions(self):
        # Return available actions
        action = InfoReportAction(label=_("More information"), callback=self.more_info)
        return [action]

    def more_info(self, data=None):
        webbrowser.open("https://www.freedesktop.org/wiki/Software/systemd/TheCaseForTheUsrMerge")

if __name__ == "__main__":
    report = Report()
    print(report.is_pertinent())
