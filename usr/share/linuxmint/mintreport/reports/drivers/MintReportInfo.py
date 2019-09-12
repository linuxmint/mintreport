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

        self.title = _("Install hardware drivers")
        self.icon = "mintreport-hardware-device-symbolic"
        self.has_ignore_button = True

    def is_pertinent(self):
        # Defines whether this report should show up
        self.drivers = []
        try:
            from UbuntuDrivers import detect
            driver_packages = detect.system_driver_packages()
            for package_name in driver_packages:
                if "virtualbox" in package_name:
                    # Ignore them, they're not recommended
                    continue
                driver = driver_packages[package_name]
                # if the package isn't installed, add it
                if not os.path.exists("/var/lib/dpkg/info/%s.list" % package_name):
                    self.drivers.append("%s %s" % (driver['vendor'], driver['model']))
            return (len(self.drivers) > 0)
        except Exception as e:
            print ("Failed to assess drivers availability: %s" % e)
            return False

    def get_descriptions(self):
        # Return the descriptions
        descriptions = []
        descriptions.append(_("Hardware drivers are available for the following devices:"))
        descriptions.append("\n".join(self.drivers))
        return descriptions

    def get_actions(self):
        # Return available actions
        actions = []
        action = InfoReportAction(label=_("Launch the Driver Manager"), callback=self.callback)
        action.set_style(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
        actions.append(action)
        return actions

    def callback(self):
        subprocess.run(["pkexec", "driver-manager"])

if __name__ == "__main__":
    report = Report()
    print(report.is_pertinent())
