import os
import subprocess
import gettext

class Report():

    def __init__(self):

        gettext.install("mintreport", "/usr/share/linuxmint/locale", names="ngettext")

        self.title = _("Set up the system restore utility")
        self.icon = "document-open-recent-symbolic"

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
        actions.append([_("Launch Timeshift"), self.launch_timeshift])
        return actions

    def launch_timeshift(self):
        subprocess.run(["pkexec", "timeshift-gtk"])
