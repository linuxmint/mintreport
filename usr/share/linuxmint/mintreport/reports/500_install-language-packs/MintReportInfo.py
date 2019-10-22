import apt_pkg
import codecs
import gettext
import gi
import os

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from mintreport import InfoReport, InfoReportAction

class LanguagePack:

    def __init__(self, category, language, dependency, package):
        self.category = category
        self.language = language
        self.dependency = dependency
        self.package = package

class Report(InfoReport):

    def __init__(self):

        gettext.install("mintreport", "/usr/share/locale", names="ngettext")

        self.title = _("Install language packs")
        self.icon = "preferences-desktop-locale-symbolic"
        self.has_ignore_button = True

    def is_pertinent(self):
        # Defines whether this report should show up
        language = os.getenv('LANG')
        if language is None:
            return False
        else:
            return self.check_missing_packages(language)

    def get_descriptions(self):
        # Return the descriptions
        descriptions = []
        descriptions.append(_("The following localization packages are missing to properly support your language:"))
        descriptions.append("\n".join(self.missing_pack_names))
        return descriptions

    def get_actions(self):
        # Return available actions
        actions = []
        action = InfoReportAction(label=_("Install the Language Packs"), callback=self.callback)
        action.set_style(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
        actions.append(action)
        return actions

    def callback(self, data):
        self.install_packages(self.missing_pack_names)
        # reload
        return True

    def check_missing_packages(self, locale):
        self.missing_pack_names = []
        apt_pkg.init()
        self.cache = apt_pkg.Cache(None)

        (language_code, country_code) = self.split_locale(locale)

        self.language_packs = []
        with codecs.open("/usr/share/linuxmint/mintlocale/language_packs", 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                columns = line.split(":")
                if len(columns) == 4:
                    (category, language, dependency, package) = columns
                    if package.endswith("-"):
                        self.language_packs.append(LanguagePack(category, language, dependency, "%sLANG" % package))
                        self.language_packs.append(LanguagePack(category, language, dependency, "%sLANG-COUNTRY" % package))
                    else:
                        self.language_packs.append(LanguagePack(category, language, dependency, package))

        # Check if the language packs are installed
        for language_pack in self.language_packs:
            if language_pack.language == "" or language_pack.language == language_code:
                pkgname = language_pack.package.replace("LANG", language_code).replace("COUNTRY", country_code)
                depname = language_pack.dependency
                if pkgname in self.cache:
                    pkg = self.cache[pkgname]
                    if (pkg.has_versions and pkg.current_state != apt_pkg.CURSTATE_INSTALLED):
                        if depname != "":
                            if depname in self.cache and self.cache[depname].current_state == apt_pkg.CURSTATE_INSTALLED:
                                if pkgname not in self.missing_pack_names:
                                    self.missing_pack_names.append(pkgname)
                        else:
                            if pkgname not in self.missing_pack_names:
                                self.missing_pack_names.append(pkgname)

        if len(self.missing_pack_names) == 0:
            return False
        else:
            return True

    def split_locale(self, locale_code):
        if "_" in locale_code:
            split = locale_code.split("_")
            language_code = split[0]
            language = language_code
            country_code = split[1].lower().split('@')[0].strip()
            country = country_code
        else:
            language_code = locale_code
            country_code = ""

        return (language_code, country_code)

if __name__ == "__main__":
    report = Report()
    print(report.is_pertinent())
