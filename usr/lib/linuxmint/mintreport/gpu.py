#!/usr/bin/python3
import gi
import os
import pyudev
import re
import shutil
import subprocess
import xapp.SettingsWidgets as Xs
import xapp.threading as xt
import xapp.util
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from common import read_dmi, read_efi, clean_brand
from pathlib import Path

_ = xapp.util.gettext("mintreport")


def run_cmd(cmd):
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return ""

# --- OpenGL detection ---
def detect_opengl():
    """
    Returns True if OpenGL is hardware-accelerated (not llvmpipe/swrast/softpipe).
    """
    out = run_cmd(["glxinfo", "-B"])
    if not out:
        return False

    # Check for direct rendering
    direct = bool(re.search(r"direct rendering:\s*Yes", out, re.IGNORECASE))

    # Extract renderer string
    m = re.search(r"OpenGL renderer string:\s*(.*)", out)
    renderer = m.group(1).strip() if m else ""

    # Detect software renderers
    software = any(x in renderer.lower() for x in ("llvmpipe", "softpipe", "swrast", "mesa offscreen"))

    return direct and not software

def detect_vulkan_acceleration():
    """Return True if any Vulkan GPU is hardware-accelerated."""
    try:
        out = subprocess.check_output(
            ["vulkaninfo", "--summary"],
            text=True, stderr=subprocess.DEVNULL, timeout=3
        )
    except Exception:
        return None  # vulkaninfo not available or failed

    # Split per GPU block
    gpus = re.split(r"GPU\d+:", out)
    accel_found = False

    for gpu in gpus:
        if not gpu.strip():
            continue
        # Ignore software drivers like lavapipe
        if re.search(r"lavapipe", gpu, re.IGNORECASE):
            continue
        # If we find a valid hardware vendor/device ID
        if re.search(r"vendorID\s*=\s*0x[0-9a-f]+", gpu, re.IGNORECASE):
            accel_found = True
            break

    return accel_found

def detect_gles():
    result = False
    out = run_cmd(["es2_info"]) # part of mesa-utils
    if out:
        out = out.lower()
        if "llvmpipe" not in out and "softpipe" not in out:
            result = True
    return result

def get_default_gpu_id():
    drm_path = Path("/sys/class/drm")
    cards = sorted(drm_path.glob("card[0-9]*"))
    for card_dir in cards:
        dev_dir = card_dir / "device"
        if not dev_dir.exists():
            continue

        # Detect display connection (for default GPU)
        has_display = any(
            (card_dir / conn / "status").exists() and
            (card_dir / conn / "status").read_text().strip() == "connected"
            for conn in card_dir.iterdir() if conn.is_dir()
        )

        vendor = (dev_dir / "vendor").read_text().strip()
        device = (dev_dir / "device").read_text().strip()
        pci_id = f"{vendor}:{device}".replace("0x", "")

        if has_display:
            return pci_id

    # Fallback: return the first card's PCI ID
    if cards:
        dev_dir = cards[0] / "device"
        if (dev_dir / "vendor").exists() and (dev_dir / "device").exists():
            vendor = (dev_dir / "vendor").read_text().strip()
            device = (dev_dir / "device").read_text().strip()
            return f"{vendor}:{device}".replace("0x", "")

    return None

def get_pci_device(default_id):
    context = pyudev.Context()
    devices = []

    def decode(v): return v.decode().strip() if hasattr(v, "decode") else v

    for dev in context.list_devices(subsystem="pci"):
        try:
            vendor = dev.attributes.asstring("vendor")[2:]
            device = dev.attributes.asstring("device")[2:]
            pci_id = f"{vendor}:{device}"
            if pci_id != default_id:
                continue
        except Exception as e:
            print(e)

        return dev

def detect_video_acceleration():
    result = []
    # VA-API
    try:
        out = subprocess.check_output(
            ["vainfo"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=3,
        )
        if "Driver version" in out or re.search(r"VAProfile", out):
            result.append("VA-API")
    except Exception as e:
        pass
        #print(e)

    # VDPAU
    try:
        out = subprocess.check_output(
            ["vdpauinfo"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=3,
        )
        if re.search(r"VDPAU Driver", out) and not re.search(r"llvmpipe", out, re.IGNORECASE):
            result.append("VDPAU")
    except Exception as e:
        pass
        #print(e)

    return result

def get_gpu_driver_version(driver):
    path = Path(f"/sys/module/{driver}/version")
    if path.exists():
        return path.read_text().strip()  # e.g. NVIDIA
    if driver in ("i915", "amdgpu", "nouveau"):
        # Built-in drivers → no version file
        return None
    # fallback: modinfo
    try:
        out = subprocess.check_output(["modinfo", driver], text=True)
        m = re.search(r"version:\s*([^\n]+)", out)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return None

def bool_to_accel(boolean):
    if boolean:
        return _("Enabled")
    else:
        return _("Disabled (Software rendering)")

class GPUListWidget(Xs.SettingsPage):
    def __init__(self):
        super().__init__()
        self.set_spacing(24)
        self.set_margin_left(0)
        self.set_margin_right(0)
        self.set_margin_top(0)
        self.set_margin_bottom(0)
        self.section_gpu = self.add_section(_("Default device"))
        self.section_acceleration = self.add_section(_("GPU Acceleration"))

    @xt.run_async
    def load(self):
        gl = detect_opengl()
        es = detect_gles()
        vk = detect_vulkan_acceleration()
        pci_id = get_default_gpu_id()
        device = get_pci_device(pci_id)
        vendor = device.get("ID_VENDOR_FROM_DATABASE") or ""
        name = device.get("ID_MODEL_FROM_DATABASE") or ""
        driver = device.driver
        driver_version = get_gpu_driver_version(driver)
        video = detect_video_acceleration()
        if len(video) == 0:
            video = _("Disabled (Software rendering)")
        else:
            video = _("Enabled (%s)") % ", ".join(video)
        info_gpu = []
        info_gpu.append([_('Brand'), clean_brand(vendor)])
        info_gpu.append([_('Name'), name])
        info_gpu.append([_('PCI ID'), pci_id])
        info_gpu.append([_('Driver'), driver])
        if driver_version:
            info_gpu.append([_('Driver version'), driver_version])
        info_acceleration = []
        info_acceleration.append([_('OpenGL'), bool_to_accel(gl)])
        info_acceleration.append([_('OpenGL ES'), bool_to_accel(es)])
        info_acceleration.append([_('Vulkan'), bool_to_accel(vk)])
        info_acceleration.append([_('Video playback'), video])
        self.update_ui(info_gpu, self.section_gpu)
        self.update_ui(info_acceleration, self.section_acceleration)

    @xt.run_idle
    def update_ui(self, info, section):
        for (key, value) in info:
            widget = Xs.SettingsWidget()
            widget.set_spacing(40)
            labelKey = Gtk.Label.new(key)
            widget.pack_start(labelKey, False, False, 0)
            labelKey.get_style_context().add_class("dim-label")
            labelValue = Gtk.Label.new(value)
            labelValue.set_selectable(True)
            labelValue.set_line_wrap(True)
            widget.pack_end(labelValue, False, False, 0)
            section.add_row(widget)
        self.show_all()

# -------------------------------------------------------------------
# Standalone test window
# -------------------------------------------------------------------

if __name__ == "__main__":
    win = Gtk.Window()
    viewer = GPUListWidget()
    viewer.load()
    win.add(viewer)
    win.set_default_size(800, 400)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
