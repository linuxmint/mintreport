import os
import subprocess
import gettext

class Report():

    def __init__(self):

        gettext.install("mintreport", "/usr/share/linuxmint/locale", names="ngettext")

        self.title = _("Install multimedia codecs")
        self.icon = "applications-multimedia-symbolic"

    def is_pertinent(self):
        # Defines whether this report should show up
        if os.path.exists("/usr/share/applications/mint-meta-codecs.desktop"):
            return True
        else:
            return False

    def get_descriptions(self):
        # Return the descriptions
        descriptions = []
        descriptions.append(_("Multimedia codecs are required to play some video formats and to properly render some websites."))
        return descriptions

    def get_actions(self):
        # Return available actions
        actions = []
        actions.append([_("Install the Multimedia Codecs"), self.install_codecs])
        return actions

    def install_codecs(self):
        subprocess.run(["apturl", "apt://mint-meta-codecs?refresh=yes"])
