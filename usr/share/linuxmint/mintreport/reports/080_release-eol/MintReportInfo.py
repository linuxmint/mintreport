import configobj
import gettext
import time

from datetime import datetime
from mintreport import InfoReport

class Report(InfoReport):

    def __init__(self):

        gettext.install("mintreport", "/usr/share/locale", names="ngettext")

        self.icon = "software-update-urgent-symbolic"
        self.has_ignore_button = False

    def is_pertinent(self):
        # Defines whether this report should show up
        self.eol_date = None
        base_codename = None
        base_distro = None

        config = configobj.ConfigObj("/etc/os-release")
        for base_distribution in ['ubuntu', 'debian']:
            if f'{base_distribution.upper()}_CODENAME' in config:
                base_codename = config.get(f'{base_distribution.upper()}_CODENAME')
                base_distro = base_distribution
                break

        distro_info = open(f"/usr/share/distro-info/{base_distro}.csv", "r").readlines()
        for line in distro_info[1:]:
            elements = line.split(",")
            if len(elements) >= 6:
                codename = elements[2]
                eol = elements[5]
                if codename != base_codename:
                    continue

                self.eol_date = time.mktime(time.strptime(eol.rstrip(), '%Y-%m-%d'))
                self.eol_date = datetime.fromtimestamp(self.eol_date)

        if not self.eol_date:
            print(f"Could not find the EOL date for {base_codename}")
            return False

        self.days_before_eol = (self.eol_date - datetime.now()).days
        if self.days_before_eol >= 90:
            return False
            
        if self.days_before_eol > 0:
            self.title = _("Your version of Linux Mint will soon reach End-Of-Life (EOL)")
            self.description = gettext.ngettext('It will stop receiving support and updates in a day.', 'It will stop receiving support and updates in {num_days} days.', self.days_before_eol).format(num_days=self.days_before_eol)

        else:
            self.title = _("Your version of Linux Mint is no longer supported")
            self.description = gettext.ngettext('It reached End-Of-Life (EOL) yesterday.', 'It reached End-Of-Life (EOL) {num_days} days ago.', self.days_before_eol).format(num_days=self.days_before_eol * -1)

        return True
    def get_descriptions(self):
        # Return the descriptions
        return [self.description, _("Visit <a href='https://www.linuxmint.com'>https://www.linuxmint.com</a> to find information about newer releases.")]

    def get_actions(self):
        # Return available actions
        return []

if __name__ == "__main__":
    report = Report()
    print(report.is_pertinent())
