#!/usr/bin/python3
import gi
gi.require_version("Gtk", "3.0")

import gettext
import locale
import os
import xapp.SettingsWidgets
from gi.repository import Gtk
from common import _async, idle, read_dmi, read_efi, clean_brand, prefix_version

# i18n
APP = 'mintreport'
LOCALE_DIR = "/usr/share/locale"
locale.bindtextdomain(APP, LOCALE_DIR)
gettext.bindtextdomain(APP, LOCALE_DIR)
gettext.textdomain(APP)
_ = gettext.gettext

class BIOSListWidget(xapp.SettingsWidgets.SettingsPage):
    def __init__(self):
        super().__init__()
        self.set_spacing(24)
        self.set_margin_left(0)
        self.set_margin_right(0)
        self.section_bios = self.add_section(_("BIOS"))
        self.section_motherboard = self.add_section(_("Motherboard"))

    @_async
    def load(self):
        # Don't load chassis info. It's rarely useful
        # 1. often the same as product info
        # 2. often missing
        # 3. oten just describes what the user already knows (laptop, desktop..)

        infos_bios = []
        infos_bios.append([_('Brand'), clean_brand(read_dmi('bios_vendor'))])
        infos_bios.append([_('Version'), read_dmi('bios_version')])
        infos_bios.append([_('Release'), read_dmi('bios_release')])
        infos_bios.append([_('Release Date'), read_dmi('bios_date')])

        if not os.path.exists("/sys/firmware/efi"):
            infos_bios.append([_('Boot Mode'), 'BIOS'])
            infos_bios.append([_('Secure Boot'), _("Disabled")])
        else:
            infos_bios.append([_('Boot Mode'), 'UEFI'])
            if read_efi("SecureBoot") == 1:
                infos_bios.append([_('Secure Boot'), _("Enabled")])
                setup_mode = read_efi("SetupMode")
                if setup_mode == 1:
                    infos_bios.append([_('Secure Boot mode'), _("Setup Mode (keys not enrolled)")])
                elif setup_mode == 0:
                    infos_bios.append([_('Secure Boot mode'), _("User Mode (normal)")])
            else:
                infos_bios.append([_('Secure Boot'), _("Disabled")])

        infos_motherboard = []
        infos_motherboard.append([_('Brand'), clean_brand(read_dmi('board_vendor'))])
        infos_motherboard.append([_('Name'), read_dmi('board_name')])
        infos_motherboard.append([_('Version'), read_dmi('board_version')])

        self.update_ui(infos_bios, infos_motherboard)

    @idle
    def update_ui(self, infos_bios, infos_motherboard):
        for (key, value) in infos_bios:
            widget = xapp.SettingsWidgets.SettingsWidget()
            widget.set_spacing(40)
            labelKey = Gtk.Label.new(key)
            widget.pack_start(labelKey, False, False, 0)
            labelKey.get_style_context().add_class("dim-label")
            labelValue = Gtk.Label.new(value)
            labelValue.set_selectable(True)
            labelValue.set_line_wrap(True)
            widget.pack_end(labelValue, False, False, 0)
            self.section_bios.add_row(widget)
        for (key, value) in infos_motherboard:
            widget = xapp.SettingsWidgets.SettingsWidget()
            widget.set_spacing(40)
            labelKey = Gtk.Label.new(key)
            widget.pack_start(labelKey, False, False, 0)
            labelKey.get_style_context().add_class("dim-label")
            labelValue = Gtk.Label.new(value)
            labelValue.set_selectable(True)
            labelValue.set_line_wrap(True)
            widget.pack_end(labelValue, False, False, 0)
            self.section_motherboard.add_row(widget)
        self.show_all()

# -------------------------------------------------------------------
# Standalone test window
# -------------------------------------------------------------------

if __name__ == "__main__":
    win = Gtk.Window(title="BIOS")
    viewer = BIOSListWidget()
    viewer.load()
    win.add(viewer)
    win.set_default_size(800, 400)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
