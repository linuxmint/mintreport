import os

class Report():

    def __init__(self, environment):
        self.environment = environment

    def is_pertinent(self):
        # Defines whether this report should show up
        if os.path.exists("/usr/bin/timeshift") and not os.path.exists("/etc/timeshift.json"):
            return True
        else:
            return False
