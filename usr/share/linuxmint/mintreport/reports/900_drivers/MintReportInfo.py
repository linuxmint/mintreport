import gettext
import gi
import os
import subprocess
import re
import json

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

        is_cpu = "intel-microcode" in device['drivers'] or "amd64-microcode" in device['drivers']
        if is_cpu:
            return self.get_cpu_name()
        elif vendor_name is None and model_name is None:
            return _("Unknown")
        elif vendor_name is None:
            return model_name
        elif model_name is None:
            return _(f"{vendor_name} (unknown)")
        else:
            return f"{vendor_name}: {model_name}"

    def is_pertinent(self):
        # Defines whether this report should show up
        self.drivers = []

        # ubuntu-drivers and UbuntuDrivers module share the same package; if it's
        # missing, we're on lmde.
        if not os.path.exists("/usr/bin/ubuntu-drivers"):
            return False

        try:
            output = subprocess.check_output(
                ["python3",
                 "-c",
                 "import json; from UbuntuDrivers import detect; detect.apt_pkg.init(); d = json.dumps(detect.system_device_drivers()); print(d)"],
                stderr=subprocess.DEVNULL).decode("UTF-8")

            devices = json.loads(output)
            for device_id in devices:
                device = devices[device_id]
                device_name = self.construct_name(device)
                if "virtualbox" in device_name.lower() or "vmware" in device_name.lower():
                    print(f"Ignoring {device_name}")
                    # Ignore them, they're not recommended
                    continue
                if 'manual_install' in device.keys() and device['manual_install'] == True:
                    print(f"Ignoring device: {device_name} (manual_install)")
                    continue
                packages = []
                for driver_name in device['drivers']:
                    driver = device['drivers'][driver_name]
                    if 'builtin' in driver.keys() and driver['builtin'] == True:
                        print(f"Ignoring driver: {driver} (builtin)")
                        continue
                    packages.append(driver_name)
                any_installed = any(os.path.exists(f"/var/lib/dpkg/info/{pkg}.list") for pkg in packages)
                if not any_installed:
                    self.drivers.append(device_name)
            return (len(self.drivers) > 0)
        except Exception as e:
            print(f"Failed to assess drivers availability: {e}")
            return False

    def get_descriptions(self):
        # Return the descriptions
        return [_("Hardware drivers are available for the following devices:"), "\n".join(self.drivers)]

    def get_actions(self):
        # Return available actions
        action = InfoReportAction(label=_("Launch the Driver Manager"), callback=self.callback)
        action.set_style(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
        return [action]

    def callback(self, data):
        subprocess.run(["pkexec", "driver-manager"])
        # don't reload
        return False

if __name__ == "__main__":
    report = Report()
    print(report.is_pertinent())
