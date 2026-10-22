# switch-reset

**English** | [Deutsch](README.de.md)

Factory-reset network switches over a serial console cable. The tool finds the cable automatically, asks which switch type is connected, logs in, wipes the configuration and reboots the switch. It runs on Windows, macOS and Linux and needs no Python installation when you use the prebuilt program.

> **Warning:** The complete configuration of the switch is erased and the switch reboots. This cannot be undone.

> **Note:** The program is bilingual. At start you choose **Deutsch** or **English**.

## Supported switches

| No. | Type | Models (as far as known) | Default login (if needed) |
|---|---|---|---|
| 1 | Cisco IOS / IOS-XE | Catalyst 2960, 3560, 3750, 3850, 9200, 9300 | depends on configuration |
| 2 | HP ProCurve / Aruba OS-Switch | 2530, 2540, 2920, 2930 | depends on configuration |
| 3 | Aruba CX | 6100, 6200, 6300, 8xxx | `admin`, no password |
| 4 | Juniper EX (Junos) | EX series | `root` |
| 5 | Extreme EXOS / Switch Engine | X440, X450, X460, X620, X670 | `admin`, no password |
| 6 | Arista EOS | 7010, 7050, 7060, 7280 | `admin`, no password |
| 7 | Huawei VRP | S5700, S6700 | `admin` / `admin@huawei.com` |

Not supported: Cisco Nexus/NX-OS, Cisco Small Business, Extreme VOSS/ERS, Netgear, TP-Link, D-Link, Dell, Ubiquiti, MikroTik, Ruckus/Brocade, Zyxel, Lancom.

The commands are the standard ones for each platform but have not been tested on real hardware. Try it on a switch with nothing important on it first.

## 1. What you need

- The switch, powered on
- A console cable:
  - USB-to-serial adapter plus rollover cable (RJ45 to console port), or
  - Mini-USB / USB-C cable if the switch has a USB console port
- The program (no Python needed):
  - **Windows:** `switch_reset.exe`
  - **Mac / Linux:** `switch_reset`
  - Download: GitHub tab **Actions** → latest run → **Artifacts**. Or build it yourself (section 6).

## 2. Connect the cable

1. Plug the cable into the **CONSOLE** port of the switch, not into a normal LAN port or the management port.
2. Plug the USB end into your computer.
3. Power on the switch and wait 1–2 minutes until it has booted.

**Drivers:** If the program reports that no console cable was found, a driver may be missing. Common chips are FTDI, Prolific PL2303, Silicon Labs CP210x and WCH CH340. For Cisco mini-USB console ports, install the "Cisco USB Console Driver". On Windows, the cable must show up as a COM port in Device Manager under "Ports (COM & LPT)".

## 3. Start the program

**Mac**

Double-click `switch_reset`, or in the terminal:

```bash
cd path/to/the/folder
./switch_reset
```

If macOS blocks the file on first start (for example after a download), right-click it, choose "Open" and confirm. Or in the terminal:

```bash
xattr -d com.apple.quarantine switch_reset
chmod +x switch_reset
```

**Windows**

Double-click `switch_reset.exe`. If SmartScreen warns you, click "More info" and then "Run anyway".

**Linux**

```bash
chmod +x switch_reset
./switch_reset
```

If you get "permission denied" on the port, add yourself to the serial group and log in again: `sudo usermod -aG dialout $USER`.

## 4. Usage

1. **Choose the language:** `1` = Deutsch, `2` = English.
2. **Choose the cable:** The program lists all console cables it found, with numbers. Type the number and press Enter. `R` searches again, `Q` quits.
3. **Choose the switch type:** Type the number from the table above.
4. **Confirm:** The program shows cable, type and the steps once more. Type `YES` (`JA` in German mode) to continue. Anything else cancels without changing anything.
5. **Automatic run:** The program connects, tries several baud rates if needed, logs in (asking for username and password when required; typed passwords are invisible, which is normal), erases the configuration and reboots the switch.
6. **Done:** On success it reports that the reset commands were sent. The reboot takes about 2–5 minutes. Wait before connecting to the switch again.

## 5. Troubleshooting

Every error is shown in red on screen and also written to `switch_reset.log` next to the program.

| Problem | Cause and fix |
|---|---|
| No console cable found | Cable not plugged in, driver missing or cable defective. Try another USB port and install the driver. |
| Port busy / access denied | Another program is using the cable (PuTTY, Tera Term, `screen`, another terminal). Close that connection. On Mac, `lsof /dev/cu.xxx` shows who holds the port. |
| Switch does not answer at any baud rate | Cable is in the wrong port, switch is off or still booting, or a normal LAN cable is used instead of a console cable. The cable may also be defective. On Cisco, the mini-USB port takes priority over RJ45. |
| Unreadable answer | Wrong baud rate or defective adapter. Try another adapter. |
| Login rejected / enable not accepted | Wrong or unknown password. Password recovery on the device is needed (reset button or ROMMON). The program cannot do this. |
| Switch is in ROMMON / bootloader | No valid operating system is loaded. Boot an image manually or reflash. |
| Command reports an error | Most likely the wrong switch type was chosen. Restart and pick the right one. |
| Connection lost / write timeout | Cable was unplugged or is loose. The switch may be in a half-done state: reconnect and repeat. |
| Timeout, switch stops responding | Switch is hanging or booting. Wait and try again. |
| Aborted with Ctrl+C | The switch may be in a half-done state. Repeat the run. |

## 6. Building the program yourself

**Windows (`.exe`)** — must be built on Windows, once, with Python installed:

1. Copy the folder to the Windows PC.
2. Double-click `build_windows.bat`.
3. The result is `dist\switch_reset.exe`. Copy it to any Windows PC; no Python needed there.

**Without your own Windows PC:** The repo contains `.github/workflows/build.yml`. On every push GitHub builds the Windows, Mac and Linux versions automatically. Find them under **Actions** → select a run → **Artifacts**.

**Mac / Linux:** `./build_mac.sh` creates `dist/switch_reset`.

**Run directly with Python (no build):**

```bash
pip install pyserial
python switch_reset.py
```

## 7. Adding another switch type

Add a new `Profil(...)` entry to the `PROFILE` list in `switch_reset.py`: baud rate, prompt pattern and the commands with the confirmation prompts to answer. If a model behaves differently than expected, `switch_reset.log` shows exactly what the switch answered.

## Contributing / Feedback

Missing your switch model or vendor? Found a bug? Open an [issue](../../issues) or send a pull request. If a model behaves differently than expected, attach your `switch_reset.log` (remove passwords and IP addresses first). That makes it easy to add or fix a profile.
