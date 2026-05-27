import subprocess
import time
import re

from rich.console import Console
from rich.live import Live
from rich.align import Align
from rich.layout import Layout

console = Console()

# ---------------- DEVICE DETECTION ---------------- #

def get_device():
    """Return the first connected device ID, or None."""
    try:
        result = subprocess.check_output(["adb", "devices"], text=True)
        for line in result.splitlines()[1:]:
            if "\tdevice" in line and "offline" not in line:
                return line.split("\t")[0]
        return None
    except Exception:
        return None


def wait_for_device():
    """Keep polling until a device is connected, then return its ID."""
    console.print("[bold yellow]Waiting for Android device...[/bold yellow]")
    while True:
        device = get_device()
        if device:
            console.print(f"[bold green]Connected: {device}[/bold green]")
            return device
        console.print("[red]No device found. Connect via Wireless Debugging...[/red]")
        time.sleep(3)


def is_device_connected(device):
    """Check if a previously-known device is still connected."""
    try:
        result = subprocess.check_output(["adb", "devices"], text=True)
        return device in result and "\tdevice" in result
    except Exception:
        return False


def get_phone_name(device):
    """Return the human-readable phone model name."""
    try:
        name = subprocess.check_output(
            ["adb", "-s", device, "shell", "getprop", "ro.product.model"],
            text=True
        ).strip()
        return name if name else "Android Device"
    except Exception:
        return "Android Device"


# ---------------- BATTERY ---------------- #

def get_battery(device):
    """Return (level_str, status_str, temp_celsius)."""
    try:
        result = subprocess.check_output(
            ["adb", "-s", device, "shell", "dumpsys", "battery"],
            text=True
        )

        level = "0"
        status = "Unknown"
        temp = 0.0

        status_map = {
            "1": "Unknown",
            "2": "Charging",
            "3": "Discharging",
            "4": "Not Charging",
            "5": "Full",
        }

        for line in result.splitlines():
            line = line.strip()
            if line.startswith("level"):
                level = line.split(":")[1].strip()
            if line.startswith("status"):
                code = line.split(":")[1].strip()
                status = status_map.get(code, "Unknown")
            if line.startswith("temperature"):
                raw = int(line.split(":")[1].strip())
                temp = raw / 10.0

        return level, status, temp

    except Exception:
        return "?", "Error", 0.0


def battery_color(level):
    """Return a Rich colour string based on battery percentage."""
    lvl = int(level) if level.isdigit() else 0
    if lvl > 60:
        return "green"
    elif lvl > 30:
        return "yellow"
    else:
        return "red"


# ---------------- RAM (PHONE) ---------------- #

def get_ram(device):
    """Return (used_gb, total_gb, percent)."""
    try:
        result = subprocess.check_output(
            ["adb", "-s", device, "shell", "cat", "/proc/meminfo"],
            text=True
        )

        total = 0
        avail = 0

        for line in result.splitlines():
            if "MemTotal" in line:
                total = int(line.split()[1]) / (1024 * 1024)  # kB → GB
            if "MemAvailable" in line:
                avail = int(line.split()[1]) / (1024 * 1024)  # kB → GB

        used = total - avail
        percent = (used / total) * 100 if total else 0

        return used, total, percent

    except Exception:
        return 0, 0, 0


# ---------------- STORAGE (PHONE) ---------------- #

def get_storage(device):
    """Return (used_gb, total_gb, percent)."""
    try:
        result = subprocess.check_output(
            ["adb", "-s", device, "shell", "df", "/sdcard"],
            text=True
        )

        lines = result.splitlines()
        if len(lines) < 2:
            return 0, 0, 0

        parts = re.split(r"\s+", lines[1])

        total = int(parts[1]) / (1024 * 1024)
        used = int(parts[2]) / (1024 * 1024)

        percent = (used / total) * 100 if total else 0

        return used, total, percent

    except Exception:
        return 0, 0, 0


# ---------------- CPU ---------------- #

def get_cpu(device):
    """Return (total_cpu_percent, load_1m).

    Parses ``adb shell dumpsys cpuinfo`` output.
    """
    try:
        out = subprocess.check_output(
            ["adb", "-s", device, "shell", "dumpsys", "cpuinfo"],
            text=True
        )

        percent = 0.0
        load_1m = 0.0

        for line in out.splitlines():
            # "Load: 1.5 / 1.8 / 2.0"
            if line.startswith("Load:"):
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        load_1m = float(parts[1].rstrip(","))
                    except ValueError:
                        pass

            # "24% TOTAL: 15% user + 8% kernel + 1% iowait"
            match = re.search(r"(\d+(?:\.\d+)?)%\s+TOTAL", line)
            if match:
                percent = float(match.group(1))

        return percent, load_1m

    except Exception:
        return 0, 0, 0


# ---------------- UI HELPERS ---------------- #

def _bar(percent, width=18, good_below=60, warn_below=85, reverse=False):
    """Build a coloured unicode progress bar.

    By default higher percent = worse (usage metrics like RAM / storage).
    Set *reverse=True* when higher percent = better (e.g. battery level).
    """
    filled = round(percent / 100 * width)
    filled = max(0, min(filled, width))
    bar_chars = "█" * filled + "░" * (width - filled)

    if reverse:
        color = "red" if percent < good_below else "yellow" if percent < warn_below else "green"
    else:
        color = "green" if percent < good_below else "yellow" if percent < warn_below else "red"

    return f"[{color}]{bar_chars}[/{color}]"


# ---------------- UI ---------------- #

def build(device, phone_name):
    """Render the borderless horizontal dashboard."""
    battery, status, temp = get_battery(device)
    ram_u, ram_t, ram_p = get_ram(device)
    st_u, st_t, st_p = get_storage(device)
    cpu_p, cpu_load = get_cpu(device)

    b = int(battery) if battery.isdigit() else 0
    batt_col = battery_color(battery)

    # ── Battery card ───────────────────────────────────────────────
    batt_text = (
        "[bold]Battery[/bold]\n\n"
        f"{_bar(b, good_below=20, warn_below=60, reverse=True)}\n\n"
        f"[{batt_col} bold]{battery}%[/{batt_col} bold]   {status}\n\n"
        f"[bold]{temp:.1f}°C[/bold]"
    )
    batt_card = Align.center(batt_text)

    # ── RAM card ───────────────────────────────────────────────────
    ram_text = (
        "[bold]RAM[/bold]\n\n"
        f"{_bar(ram_p)}\n\n"
        f"[bold]{ram_u:.1f}[/bold] / {ram_t:.1f} GB\n\n"
        f"{ram_p:.0f}% used"
    )
    ram_card = Align.center(ram_text)

    # ── Storage card ───────────────────────────────────────────────
    st_text = (
        "[bold]Storage[/bold]\n\n"
        f"{_bar(st_p)}\n\n"
        f"[bold]{st_u:.1f}[/bold] / {st_t:.1f} GB\n\n"
        f"{st_p:.0f}% used"
    )
    st_card = Align.center(st_text)

    # ── CPU card ───────────────────────────────────────────────────
    load_line = f"Load: {cpu_load:.1f}" if cpu_load else "—"
    cpu_text = (
        "[bold]CPU[/bold]\n\n"
        f"{_bar(cpu_p)}\n\n"
        f"[bold]{cpu_p:.0f}%[/bold]\n\n"
        f"{load_line}"
    )
    cpu_card = Align.center(cpu_text)

    # ── Layout ─────────────────────────────────────────────────────
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=1),
        Layout(name="body"),
    )

    layout["header"].update(
        Align.center(
            f"[bold magenta]{phone_name}[/bold magenta]"
        )
    )

    body = Layout()
    body.split_row(
        Layout(batt_card),
        Layout(ram_card),
        Layout(st_card),
        Layout(cpu_card),
    )
    layout["body"].update(body)

    return layout


# ---------------- MAIN ---------------- #

def main():
    device = wait_for_device()
    phone_name = get_phone_name(device)

    with Live(build(device, phone_name), refresh_per_second=2, screen=True) as live:
        while True:
            if not is_device_connected(device):
                live.update(
                    Align.center(
                        "[bold red]Device disconnected!\n\n"
                        "[yellow]Waiting for reconnection...[/yellow]"
                    )
                )
                device = wait_for_device()
                phone_name = get_phone_name(device)
                continue

            live.update(build(device, phone_name))
            time.sleep(2)


if __name__ == "__main__":
    main()
