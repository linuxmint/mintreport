import os

class Report():

    def __init__(self, environment):
        self.environment = environment

    def is_pertinent(self):
        # Defines whether this report should show up
        if os.path.exists("/usr/share/applications/mint-meta-codecs.desktop"):
            return True
        else:
            return False

    def parse_content(self, content):
        codecs = "mint-meta-codecs"
        content = content.replace("$codecs", codecs)
        return content