#!/usr/bin/python3
import gi
import importlib
import os
import sys
import glob
import threading
from pathlib import Path
from gi.repository import GObject

DATA_DIR = "/usr/share/linuxmint/mintreport"
INFO_DIR = os.path.join(DATA_DIR, "reports")
TMP_DIR = "/tmp/mintreport"

# Used as a decorator to run things in the background
def _async(func):
    def wrapper(*args, **kwargs):
        thread = threading.Thread(target=func, args=args, kwargs=kwargs)
        thread.daemon = True
        thread.start()
        return thread
    return wrapper

# Used as a decorator to run things in the main loop, from another thread
def idle(func):
    def wrapper(*args):
        GObject.idle_add(func, *args)
    return wrapper

class InfoReportContainer():
    def __init__(self, uuid, path):
        self.uuid = uuid
        self.path = path
        sys.path.insert(0, path)
        import MintReportInfo
        importlib.reload(MintReportInfo)
        self.instance = MintReportInfo.Report()
        sys.path.remove(path)

def prefix_version(version):
    if version == "":
        return ""
    elif version[0].isnumeric():
        return f"v{version}"
    else:
        return version

def clean_brand(brand):
    return BRAND_MAP.get(brand, brand)

def read_efi(name):
    """Read a UEFI variable (returns None if missing or unreadable)."""
    paths = glob.glob(f"/sys/firmware/efi/efivars/{name}-*")
    if not paths:
        return None
    try:
        with open(paths[0], "rb") as f:
            data = f.read()
        # First 4 bytes are attributes; next byte is the actual value
        return data[4]
    except Exception:
        return None

def read_dmi(field):
    path = Path(f"/sys/class/dmi/id/{field}")
    if not path.exists():
        return ""
    try:
        value = path.read_text().strip()
        if value.lower() in BAD_DMI_VALUES:
            value = ""
        return value
    except Exception as e:
        print("Could not read", path)
        return ""

BAD_DMI_VALUES = [
    "default string",
    "to be filled by o.e.m.",
    "not specified",
    "none",
    "n/a",
    "unknown",
]

BRAND_MAP = {
    "Adaptec": "Adaptec",
    "Advanced Micro Devices, Inc. [AMD/ATI]": "AMD",
    "Advanced Micro Devices, Inc.": "AMD",
    "Altera Corporation": "Altera",
    "American Megatrends Inc.": "AMI",
    "Apple Inc.": "Apple",
    "ASMedia Technology Inc.": "ASMedia",
    "ASUSTeK COMPUTER INC.": "ASUS",
    "AverMedia Technologies, Inc.": "AverMedia",
    "Blackmagic Design": "Blackmagic",
    "Broadcom / Avago": "Broadcom",
    "Broadcom / LSI": "LSI",
    "Broadcom Inc. and subsidiaries": "Broadcom",
    "Broadcom Limited": "Broadcom",
    "C-Media Electronics Inc": "C-Media",
    "Creative Labs": "Creative",
    "Creative Technology Ltd.": "Creative",
    "Crucial Technology": "Crucial",
    "Compulab Ltd.": "Compulab",
    "Dell Inc.": "Dell",
    "Dynabook Inc.": "Dynabook",
    "Elgato Systems": "Elgato",
    "Freescale Semiconductor Inc": "Freescale",
    "Fujitsu / Fujitsu Siemens Computers": "Fujitsu",
    "Gigabyte Technology Co., Ltd.": "Gigabyte",
    "GoPro, Inc.": "GoPro",
    "Hewlett-Packard / HP": "HP",
    "Huawei Technologies Co., Ltd.": "Huawei",
    "HUAWEI": "Huawei",
    "innotek GmBH": "innotek",
    "Intel Corporation (Network)": "Intel",
    "Intel Corporation": "Intel",
    "Kingston Technology Company": "Kingston",
    "Lattice Semiconductor Corp.": "Lattice",
    "Marvell Technology Group Ltd.": "Marvell",
    "MediaTek Inc.": "MediaTek",
    "Mellanox Technologies": "Mellanox",
    "Microchip Technology Inc.": "Microchip",
    "Micron Technology": "Micron",
    "Micro-Star International Co., Ltd.": "MSI",
    "Microsoft Corporation": "Microsoft",
    "NEC Corporation": "NEC",
    "NVIDIA Corporation": "NVIDIA",
    "NXP Semiconductors": "NXP",
    "Oracle Corporation": "Oracle",
    "Panasonic Corporation": "Panasonic",
    "Phison Electronics Corporation": "Phison",
    "Qualcomm Atheros": "Atheros",
    "Qualcomm Technologies, Inc": "Qualcomm",
    "Realtek Semiconductor Co., Ltd.": "Realtek",
    "Realtek Semiconductor Corp.": "Realtek",
    "Renesas Technology Corp.": "Renesas",
    "Samsung Electronics Co Ltd": "Samsung",
    "Samsung Electronics Co., Ltd.": "Samsung",
    "SanDisk Corp.": "SanDisk",
    "Sony Corporation": "Sony",
    "Texas Instruments": "TI",
    "VIA Technologies, Inc.": "VIA",
    "VMware, Inc.": "VMware",
    "Western Digital Corporation": "WD",
    "Western Digital": "WD",
    "Xilinx Corporation": "Xilinx",
}
