import os
import gettext
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from mintreport import InfoReport, InfoReportAction

class Report(InfoReport):

    def __init__(self):

        gettext.install("mintreport", "/usr/share/locale", names="ngettext")

        self.title = _("Install multimedia codecs")
        self.icon = "applications-multimedia-symbolic"
        self.has_ignore_button = True

    def is_pertinent(self):
        # Defines whether this report should show up
        return bool(os.path.exists("/usr/share/applications/mint-meta-codecs.desktop"))

    def get_descriptions(self):
        # Return the descriptions
        return [_("Multimedia codecs are required to play some video formats and to properly render some websites.")]

    def get_actions(self):
        action = InfoReportAction(label=_("Install the Multimedia Codecs"), callback=self.callback)

        action.set_style(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
        return [action]

    def callback(self, data):
        self.install_packages(["mint-meta-codecs", "libavcodec-extra", "libavcodec-extra58"])
        # reload
        return True

if __name__ == "__main__":
    report = Report()
    print(report.is_pertinent())
