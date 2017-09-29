import os

class Report():

    def __init__(self, environment):
        self.environment = environment

    def is_pertinent(self):
        # Defines whether this report should show up
        if os.path.exists("/usr/share/nemo-python/extensions/nemo-media-columns.py") and self.environment.desktop == "Cinnamon":
            return True
        else:
            return False
