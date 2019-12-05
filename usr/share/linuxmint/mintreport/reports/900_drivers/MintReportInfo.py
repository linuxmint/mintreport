import gettext
import gi
import os
import subprocess

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from mintreport import InfoReport, InfoReportAction

class Report(InfoReport):

    def __init__(self):

        gettext.install("mintreport", "/usr/share/locale", names="ngettext")

        self.title = _("Install hardware drivers")
        self.icon = "mintreport-hardware-device-symbolic"
        self.has_ignore_button = True

    def is_pertinent(self):
        # Defines whether this report should show up
        self.drivers = []
        try:
            from UbuntuDrivers import detect
            devices = detect.system_device_drivers()
            for device_id in devices:
                device = devices[device_id]
                device_name = "%s %s" % (device['vendor'], device['model'])
                if "virtualbox" in device_name.lower() or "vmware" in device_name.lower():
                    print("Ignoring %s" % device_name)
                    # Ignore them, they're not recommended
                    continue
                packages = []
                for driver_name in device['drivers']:
                    driver = device['drivers'][driver_name]
                    if 'builtin' in driver.keys() and driver['builtin'] == True:
                        continue
                    packages.append(driver_name)
                any_installed = False
                for pkg in packages:
                    # Check if the package is installed
                    if os.path.exists("/var/lib/dpkg/info/%s.list" % pkg):
                        any_installed = True
                        break
                if not any_installed:
                    self.drivers.append(device_name)
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

    def callback(self, data):
        subprocess.run(["pkexec", "driver-manager"])
        # don't reload
        return False

if __name__ == "__main__":
    report = Report()
    print(report.is_pertinent())
