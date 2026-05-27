import subprocess
import time
import re

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.align import Align

console = Console()

# ---------------- DEVICE DETECTION ---------------- #
def get_device():
    try:
        result = subprocess.check_output(["adb", "devices"], text=True)

        for line in result.splitlines()[1:]:
            if "\tdevice" in line and "offline" not in line:
                return line.split("\t")[0]

        return None

    except Exception:
        return None


def wait_for_device():
    console.print("[bold yellow]🔍 Waiting for Android device...[/bold yellow]")

    while True:
        device = get_device()

        if device:
            console.print(f"[bold green]✅ Connected: {device}[/bold green]")
            return device

        console.print("[red]❌ No device found. Connect via Wireless Debugging...[/red]")
        time.sleep(3)


# ---------------- BATTERY ---------------- #
def get_battery(device):
    try:
        result = subprocess.check_output(
            ["adb", "-s", device, "shell", "dumpsys", "battery"],
            text=True
        )

        level = "0"
        status = "Unknown"

        for line in result.splitlines():
            line = line.strip()

            if line.startswith("level"):
                level = line.split(":")[1].strip()

            if line.startswith("status"):
                code = line.split(":")[1].strip()

                status_map = {
                    "1": "Unknown",
                    "2": "Charging",
                    "3": "Discharging",
                    "4": "Not Charging",
                    "5": "Full",
                }

                status = status_map.get(code, "Unknown")

        return level, status

    except Exception:
        return "?", "Error"


# ---------------- RAM (PHONE) ---------------- #
def get_ram(device):
    try:
        result = subprocess.check_output(
            ["adb", "-s", device, "shell", "cat", "/proc/meminfo"],
            text=True
        )

        total = 0
        avail = 0

        for line in result.splitlines():
            if "MemTotal" in line:
                total = int(line.split()[1]) / (1024 * 1024)  # GB
            if "MemAvailable" in line:
                avail = int(line.split()[1]) / (1024 * 1024)  # GB

        used = total - avail
        percent = (used / total) * 100 if total else 0

        return used, total, percent

    except Exception:
        return 0, 0, 0


# ---------------- STORAGE (PHONE) ---------------- #
def get_storage(device):
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


# ---------------- UI ---------------- #

def _bar(percent, width=18, good_below=60, warn_below=85, reverse=False):
    """Build a colored unicode progress bar.

    By default, higher percent = worse (for usage metrics like RAM/storage).
    Set reverse=True when higher percent = better (e.g. battery level).
    """
    filled = round(percent / 100 * width)
    filled = max(0, min(filled, width))
    bar_chars = "█" * filled + "░" * (width - filled)

    if reverse:
        color = "red" if percent < good_below else "yellow" if percent < warn_below else "green"
    else:
        color = "green" if percent < good_below else "yellow" if percent < warn_below else "red"

    return f"[{color}]{bar_chars}[/{color}]"


def build(device):
    battery, status = get_battery(device)
    ram_u, ram_t, ram_p = get_ram(device)
    st_u, st_t, st_p = get_storage(device)

    b = int(battery) if battery.isdigit() else 0

    table = Table.grid(expand=True, padding=(0, 3))
    table.add_column(justify="center", ratio=1)
    table.add_column(justify="center", ratio=1)
    table.add_column(justify="center", ratio=1)

    # Row 1: Titles
    table.add_row(
        "[bold]📱 Battery[/bold]",
        "[bold]💻 RAM[/bold]",
        "[bold]💾 Storage[/bold]"
    )

    # Row 2: Progress bars
    # Battery: higher % is good, so invert the color logic
    table.add_row(
        _bar(b, good_below=20, warn_below=60, reverse=True),
        _bar(ram_p),
        _bar(st_p)
    )

    # Row 3: Values
    table.add_row(
        f"[bold]{battery}%[/bold]",
        f"[bold]{ram_u:.1f}[/bold] / {ram_t:.1f} GB",
        f"[bold]{st_u:.1f}[/bold] / {st_t:.1f} GB"
    )

    # Row 4: Status / details
    table.add_row(
        f"⚡ {status}",
        f"{ram_p:.0f}% used",
        f"{st_p:.0f}% used"
    )

    return Panel(
        Align.center(table),
        title="[bold magenta]📊 Android Live Dashboard[/bold magenta]",
        border_style="cyan",
        subtitle=f"[dim]{device}[/dim]"
    )

# ---------------- MAIN ---------------- #
def main():
    device = wait_for_device()

    with Live(build(device), refresh_per_second=2, screen=True) as live:
        while True:
            live.update(build(device))
            time.sleep(2)


if __name__ == "__main__":
    main()
