import gettext
import gi
import os
import subprocess
import re

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from mintreport import InfoReport, InfoReportAction

class Report(InfoReport):

    def __init__(self):

        gettext.install("mintreport", "/usr/share/locale", names="ngettext")

        self.title = _("Install hardware drivers")
        self.icon = "mintreport-hardware-device-symbolic"
        self.has_ignore_button = True

    def get_cpu_name(self):
        with open("/proc/cpuinfo") as cpuinfo:
            for line in cpuinfo:
                if "model name" in line:
                    return re.sub( ".*model name.*:", "", line, 1).strip()
        return _("Processor")

    def construct_name(self, device):
        model_name = device.get('model', None)
        vendor_name = device.get('vendor', None)
        device_name = None

        is_cpu = False
        if "intel-microcode" in device['drivers'] or "amd64-microcode" in device['drivers']:
            is_cpu = True
        if is_cpu:
            device_name = self.get_cpu_name()
        elif vendor_name is None and model_name is None:
            device_name = _("Unknown")
        elif vendor_name is None:
            device_name = model_name
        elif model_name is None:
            device_name = _("%s (unknown)" % vendor_name)
        else:
            device_name = "%s: %s" % (vendor_name, model_name)
        return device_name

    def is_pertinent(self):
        # Defines whether this report should show up
        self.drivers = []
        try:
            from UbuntuDrivers import detect
            devices = detect.system_device_drivers()
            for device_id in devices:
                device = devices[device_id]
                device_name = self.construct_name(device)
                if "virtualbox" in device_name.lower() or "vmware" in device_name.lower():
                    print("Ignoring %s" % device_name)
                    # Ignore them, they're not recommended
                    continue
                if 'manual_install' in device.keys() and device['manual_install'] == True:
                    print("Ignoring device: %s (manual_install)" % device_name)
                    continue
                packages = []
                for driver_name in device['drivers']:
                    driver = device['drivers'][driver_name]
                    if 'builtin' in driver.keys() and driver['builtin'] == True:
                        print("Ignoring driver: %s (builtin)" % driver)
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
