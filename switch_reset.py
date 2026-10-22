#!/usr/bin/env python3
"""
Switch factory reset over a console cable (USB-serial / rollover)
Switch-Reset über Konsolenkabel (USB-Seriell / Rollover)

Flow / Ablauf:
  1. Finds connected console cables (USB-serial adapters) and lists them
  2. You pick the cable by number
  3. You pick the switch type
  4. The tool connects, logs in, erases the configuration and reboots the switch

Requires / Voraussetzung:  pip install pyserial
Run / Aufruf:              python switch_reset.py   (python3 on macOS/Linux)

Works on Windows (COMx), macOS (/dev/cu.*) and Linux (/dev/ttyUSB*, /dev/ttyACM*).
All errors are shown on screen AND written to switch_reset.log (next to the script).
Alle Fehler werden auf dem Bildschirm UND in switch_reset.log (neben dem Script) ausgegeben.
"""

from __future__ import annotations

import getpass
import locale
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime

IS_WINDOWS = os.name == "nt"

# Windows: UTF-8 output (otherwise umlauts/arrows crash cmd/PowerShell)
# and enable ANSI colors in the console.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
if IS_WINDOWS:
    os.system("")  # enables VT100/ANSI processing in the Windows console

LOGFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "switch_reset.log")

# --------------------------------------------------------------------------- #
#  Language / Sprache
# --------------------------------------------------------------------------- #
LANG = "en"


def _(de: str, en: str) -> str:
    """Returns the text in the selected language."""
    return de if LANG == "de" else en


def waehle_sprache() -> None:
    global LANG
    try:
        loc = (locale.getlocale()[0] or "").lower()
    except Exception:  # noqa: BLE001
        loc = ""
    default = "1" if loc.startswith("de") else "2"
    print("Sprache / Language:")
    print("  [1] Deutsch")
    print("  [2] English")
    while True:
        antwort = input(f"[1/2] (Enter = {default}): ").strip() or default
        if antwort in ("1", "de", "DE"):
            LANG = "de"
            return
        if antwort in ("2", "en", "EN"):
            LANG = "en"
            return


# --------------------------------------------------------------------------- #
#  Logging / Output
# --------------------------------------------------------------------------- #
def log(text: str) -> None:
    try:
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {text}\n")
    except OSError:
        pass  # logfile is optional


def info(text: str) -> None:
    print(text)
    log(text)


def fehler(text: str) -> None:
    print(f"\033[31m[{_('FEHLER', 'ERROR')}] {text}\033[0m")
    log(f"ERROR: {text}")


def warnung(text: str) -> None:
    print(f"\033[33m[{_('WARNUNG', 'WARNING')}] {text}\033[0m")
    log(f"WARNING: {text}")


def ok(text: str) -> None:
    print(f"\033[32m[OK] {text}\033[0m")
    log(f"OK: {text}")


# --------------------------------------------------------------------------- #
#  Check pyserial
# --------------------------------------------------------------------------- #
try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("\033[31m[ERROR/FEHLER] The Python module 'pyserial' is not installed. / "
          "Das Python-Modul 'pyserial' ist nicht installiert.\033[0m")
    print("  Install / Installation:  " + ("pip install pyserial   (or/oder: py -m pip install pyserial)"
                                           if IS_WINDOWS else "pip3 install pyserial"))
    print("  'externally-managed-environment'?")
    print("     python3 -m venv .venv && source .venv/bin/activate && pip install pyserial")
    sys.exit(1)


# --------------------------------------------------------------------------- #
#  Own exceptions (each with a clear message)
# --------------------------------------------------------------------------- #
class ResetError(Exception):
    """Base class for all expected errors."""


class NoResponse(ResetError):
    pass


class LoginError(ResetError):
    pass


class CommandError(ResetError):
    pass


class ConnectionLost(ResetError):
    pass


class RommonError(ResetError):
    pass


# --------------------------------------------------------------------------- #
#  Switch profiles. Texts are (German, English) tuples.
# --------------------------------------------------------------------------- #
@dataclass
class Schritt:
    beschreibung: tuple
    befehl: str
    # (regex, answer, final) - final=True: nothing more to do after the answer (reboot running)
    regeln: list = field(default_factory=list)
    optional: bool = False  # errors in this step are only warnings
    timeout: int = 30


@dataclass
class Profil:
    name: str
    baud: int
    prompt: str  # regex for a prompt at the end of a line
    schritte: list
    enable_befehl: str | None = None  # e.g. "enable" on Cisco/HP/Arista
    unpriv_prompt: str | None = None  # regex: prompt in user mode (-> enable needed)
    shell_prompt: str | None = None   # e.g. Juniper "%"
    shell_zu_cli: str | None = None
    hinweis: tuple = ("", "")


GENERIC_PROMPT = r"[\w\-\.\(\)/@:~ ]{1,60}[>#]\s*\Z"

PROFILE = [
    Profil(
        name="Cisco IOS / IOS-XE (Catalyst 2960/3560/3750/9200/9300 ...)",
        baud=9600,
        prompt=GENERIC_PROMPT,
        unpriv_prompt=r"[\w\-\.\(\)/@:~]{1,60}>\s*\Z",
        enable_befehl="enable",
        schritte=[
            Schritt(("Startup-Config löschen", "Erase startup config"), "write erase",
                    [(r"\[confirm\]", "\r", False)]),
            Schritt(("VLAN-Datenbank (vlan.dat) löschen", "Delete VLAN database (vlan.dat)"),
                    "delete flash:vlan.dat",
                    [(r"Delete filename.*\?", "\r", False),
                     (r"\[confirm\]", "\r", False)],
                    optional=True),
            Schritt(("Neustart", "Reboot"), "reload",
                    [(r"\[yes/no\]", "no", False),
                     (r"\[confirm\]", "\r", True)]),
        ],
        hinweis=("Löscht startup-config und vlan.dat, dann Neustart.",
                 "Erases startup-config and vlan.dat, then reboots."),
    ),
    Profil(
        name="HP ProCurve / Aruba OS-Switch (2530/2540/2920/2930 ...)",
        baud=9600,
        prompt=GENERIC_PROMPT,
        unpriv_prompt=r"[\w\-\.\(\)/@:~]{1,60}>\s*\Z",
        enable_befehl="enable",
        schritte=[
            Schritt(("Startup-Config löschen + Neustart", "Erase startup config + reboot"),
                    "erase startup-config",
                    [(r"\[y/n\]", "y", True)]),
        ],
        hinweis=("'erase startup-config' setzt auf Werkseinstellungen und bootet neu.",
                 "'erase startup-config' restores factory defaults and reboots."),
    ),
    Profil(
        name="Aruba CX (6100/6200/6300/8xxx ...)",
        baud=115200,
        prompt=GENERIC_PROMPT,
        schritte=[
            Schritt(("Startup-Config löschen", "Erase startup config"), "erase startup-config",
                    [(r"\(y/n\)", "y", False)]),
            Schritt(("Neustart", "Reboot"), "boot system",
                    [(r"save.*\(y/n\)", "n", False),
                     (r"\(y/n\)", "y", True)]),
        ],
        hinweis=("Standard-Login bei Werkseinstellung: admin (ohne Passwort).",
                 "Factory default login: admin (no password)."),
    ),
    Profil(
        name="Juniper EX (Junos)",
        baud=9600,
        prompt=r"[\w\-\.@:]{1,60}[>#]\s*\Z",
        shell_prompt=r"[\w\-\.@:]{1,60}%\s*\Z",
        shell_zu_cli="cli",
        schritte=[
            Schritt(("Komplett-Reset (zeroize) + Neustart", "Full reset (zeroize) + reboot"),
                    "request system zeroize",
                    [(r"\[yes,no\]", "yes", True)]),
        ],
        hinweis=("Login meist als 'root'. Zeroize löscht ALLES inkl. Logs.",
                 "Login usually 'root'. Zeroize erases EVERYTHING incl. logs."),
    ),
    Profil(
        name="Extreme Networks EXOS / Switch Engine (X440/X450/X460/X620/X670 ...)",
        baud=9600,
        prompt=GENERIC_PROMPT,
        schritte=[
            Schritt(("Komplett-Reset + Neustart", "Full reset + reboot"), "unconfigure switch all",
                    [(r"\(y/N\)|\[y/N\]|\(y/n\)|\[y/n\]", "y", True)]),
        ],
        hinweis=("Standard-Login: admin (ohne Passwort). Nicht für VOSS/ERS (Avaya).",
                 "Default login: admin (no password). Not for VOSS/ERS (Avaya)."),
    ),
    Profil(
        name="Arista EOS (7010/7050/7060/7280 ...)",
        baud=9600,
        prompt=GENERIC_PROMPT,
        unpriv_prompt=r"[\w\-\.\(\)/@:~]{1,60}>\s*\Z",
        enable_befehl="enable",
        schritte=[
            Schritt(("Startup-Config löschen", "Erase startup config"), "write erase",
                    [(r"\[confirm\]|\[yes/no", "\r", False)]),
            Schritt(("Neustart", "Reboot"), "reload",
                    [(r"yes/no", "no", False),
                     (r"\[confirm\]", "\r", True)]),
        ],
        hinweis=("Login meist 'admin' (ohne Passwort). Danach startet der Switch im ZTP-Modus.",
                 "Login usually 'admin' (no password). The switch then boots into ZTP mode."),
    ),
    Profil(
        name="Huawei VRP (S5700/S6700 ...)",
        baud=9600,
        prompt=r"(<[^<>\r\n]{1,60}>|\[[^\[\]\r\n]{1,60}\])\s*\Z",
        schritte=[
            Schritt(("Gespeicherte Config löschen", "Erase saved configuration"),
                    "reset saved-configuration",
                    [(r"\[Y/N\]", "y", False)]),
            Schritt(("Neustart", "Reboot"), "reboot",
                    [(r"save.*\[Y/N\]", "n", False),
                     (r"\[Y/N\]", "y", True)]),
        ],
        hinweis=("Standard-Login: admin / admin@huawei.com",
                 "Default login: admin / admin@huawei.com"),
    ),
]

# Baud rates tried automatically when only garbage arrives
ANDERE_BAUDRATEN = [9600, 115200, 38400, 57600, 19200]

ERROR_REGEX = re.compile(
    r"(% ?Invalid input|% ?Ambiguous|% ?Incomplete|%Error|% ?Unknown command|"
    r"Invalid command|Unrecognized command|Unknown command|Error:|"
    r"Permission denied|Authorization failed|not permitted|No such file)",
    re.I,
)
LOGIN_FAIL_REGEX = re.compile(
    r"(login invalid|login incorrect|authentication failed|access denied|"
    r"bad passwords|invalid password|login failed|% ?Authentication failed|"
    r"Invalid username or password)", re.I)
ANSI_REGEX = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[=>()][A-Za-z0-9]?|\r")


# --------------------------------------------------------------------------- #
#  Find cables
# --------------------------------------------------------------------------- #
def finde_konsolenkabel():
    """Returns the list of serial ports that look like console cables."""
    ports = []
    for p in serial.tools.list_ports.comports():
        dev = p.device
        # macOS: only cu.* devices (tty.* blocks on open); skip Bluetooth/debug
        if sys.platform == "darwin":
            if not dev.startswith("/dev/cu."):
                continue
            if any(x in dev.lower() for x in ("bluetooth", "debug-console", "wlan-debug")):
                continue
        else:
            if not any(x in dev for x in ("ttyUSB", "ttyACM", "ttyS", "COM", "rfcomm")):
                continue
            if "ttyS" in dev and p.hwid in ("n/a", ""):
                continue  # virtual, unused onboard ports
        ports.append(p)
    return sorted(ports, key=lambda x: x.device)


def zeige_ports(ports):
    print()
    print(_("Gefundene Konsolenkabel:", "Console cables found:"))
    print("-" * 70)
    for i, p in enumerate(ports, 1):
        vidpid = f"{p.vid:04x}:{p.pid:04x}" if p.vid is not None else "----:----"
        beschr = p.description if p.description and p.description != "n/a" else _("Unbekannt", "Unknown")
        print(f"  [{i}] {p.device}")
        print(f"      {beschr}  ({_('USB-ID', 'USB ID')} {vidpid})"
              + (f"  {_('Hersteller', 'Vendor')}: {p.manufacturer}" if p.manufacturer else ""))
    print("-" * 70)


def waehle_port():
    while True:
        try:
            ports = finde_konsolenkabel()
        except Exception as e:  # noqa: BLE001
            fehler(_(f"Port-Suche fehlgeschlagen: {e}", f"Port search failed: {e}"))
            log(traceback.format_exc())
            ports = []

        if not ports:
            fehler(_("Kein Konsolenkabel gefunden.", "No console cable found."))
            print(_("  Mögliche Ursachen:", "  Possible causes:"))
            print(_("   - USB-Seriell-Adapter nicht eingesteckt / Kabel defekt / USB-Hub ohne Strom",
                    "   - USB-serial adapter not plugged in / cable defective / unpowered USB hub"))
            print(_("   - Treiber fehlt (FTDI, Prolific PL2303, Silicon Labs CP210x, WCH CH340)",
                    "   - Driver missing (FTDI, Prolific PL2303, Silicon Labs CP210x, WCH CH340)"))
            if IS_WINDOWS:
                print(_("     Windows: Im Gerätemanager unter 'Anschlüsse (COM & LPT)' nachsehen.",
                        "     Windows: check Device Manager under 'Ports (COM & LPT)'."))
                print(_("     Steht das Gerät unter 'Andere Geräte' mit gelbem Ausrufezeichen,",
                        "     If the device is listed under 'Other devices' with a yellow warning sign,"))
                print(_("     fehlt der Treiber (Hersteller-Treiber installieren, neu einstecken).",
                        "     the driver is missing (install the vendor driver, replug the cable)."))
            else:
                print(_("     macOS: Treiber vom Hersteller installieren, danach in",
                        "     macOS: install the vendor driver, then allow it in"))
                print(_("     Systemeinstellungen > Datenschutz & Sicherheit freigeben und neu einstecken",
                        "     System Settings > Privacy & Security and replug the cable"))
            print(_("   - Cisco-Mini-USB-Konsole: Treiber nötig (Cisco USB Console Driver)",
                    "   - Cisco mini-USB console: driver needed (Cisco USB Console Driver)"))
            print(_("   - Nur ein Netzwerkkabel statt Konsolenkabel eingesteckt",
                    "   - A network cable plugged in instead of a console cable"))
            antwort = input(_("\n[R] erneut suchen   [Q] beenden: ",
                              "\n[R] search again   [Q] quit: ")).strip().lower()
            if antwort == "q":
                return None
            continue

        zeige_ports(ports)
        antwort = input(_("Nummer des Kabels wählen  ([R] neu suchen, [Q] beenden): ",
                          "Choose cable number  ([R] search again, [Q] quit): ")).strip().lower()
        if antwort == "q":
            return None
        if antwort in ("r", ""):
            continue
        if not antwort.isdigit() or not (1 <= int(antwort) <= len(ports)):
            fehler(_(f"'{antwort}' ist keine gültige Auswahl (1-{len(ports)}).",
                     f"'{antwort}' is not a valid choice (1-{len(ports)})."))
            continue
        return ports[int(antwort) - 1].device


def waehle_profil():
    print()
    print(_("Welcher Switch hängt hinter dem Kabel?", "Which switch is connected to the cable?"))
    print("-" * 70)
    for i, p in enumerate(PROFILE, 1):
        print(f"  [{i}] {p.name}")
        print(f"      {_(*p.hinweis)}")
    print("-" * 70)
    while True:
        antwort = input(_("Nummer wählen ([Q] beenden): ", "Choose number ([Q] quit): ")).strip().lower()
        if antwort == "q":
            return None
        if antwort.isdigit() and 1 <= int(antwort) <= len(PROFILE):
            return PROFILE[int(antwort) - 1]
        fehler(_(f"'{antwort}' ist keine gültige Auswahl (1-{len(PROFILE)}).",
                 f"'{antwort}' is not a valid choice (1-{len(PROFILE)})."))


# --------------------------------------------------------------------------- #
#  Serial connection
# --------------------------------------------------------------------------- #
def erklaere_serial_fehler(e: Exception, port: str) -> str:
    msg = str(e)
    errno = getattr(e, "errno", None)
    if IS_WINDOWS:
        low = msg.lower()
        if "access is denied" in low or "zugriff verweigert" in low or "permissionerror" in low:
            return _(f"{port} kann nicht geöffnet werden (Zugriff verweigert). Meist belegt ein "
                     "anderes Programm den COM-Port (PuTTY, Tera Term, SecureCRT, Arduino IDE, "
                     "anderes Terminal-Fenster). Dort die Verbindung schließen und erneut versuchen.",
                     f"{port} cannot be opened (access denied). Usually another program holds the "
                     "COM port (PuTTY, Tera Term, SecureCRT, Arduino IDE, another terminal window). "
                     "Close that connection and try again.")
        if "filenotfound" in low or "cannot find the file" in low or "kann die angegebene datei nicht" in low \
                or "could not open port" in low:
            return _(f"{port} existiert nicht (mehr) – Kabel abgezogen oder Treiber neu gestartet. "
                     "Im Gerätemanager die aktuelle COM-Nummer prüfen.",
                     f"{port} does not exist (any more) - cable unplugged or driver restarted. "
                     "Check the current COM number in Device Manager.")
        if "device attached to the system is not functioning" in low or "ein an das system" in low:
            return _(f"{port}: Adapter reagiert nicht (häufig bei gefälschten Prolific-Chips mit "
                     "neuem Treiber). Älteren PL2303-Treiber (3.8.x) installieren oder anderen Adapter nutzen.",
                     f"{port}: adapter not responding (common with counterfeit Prolific chips and "
                     "the newer driver). Install the older PL2303 driver (3.8.x) or use another adapter.")
    if errno == 13 or "Permission denied" in msg:
        if sys.platform.startswith("linux"):
            return _(f"Keine Berechtigung für {port}. Linux: 'sudo usermod -aG dialout $USER' und neu einloggen.",
                     f"No permission for {port}. Linux: 'sudo usermod -aG dialout $USER' and log in again.")
        return _(f"Keine Berechtigung für {port}. macOS: Terminal evtl. Zugriff geben / Treiber freigeben.",
                 f"No permission for {port}. macOS: grant the terminal access / allow the driver.")
    if errno in (11, 35) or "busy" in msg.lower() or "resource temporarily" in msg.lower() \
            or "could not exclusively lock" in msg.lower():
        return _(f"{port} ist belegt – ein anderes Programm nutzt die Konsole "
                 "(screen, minicom, PuTTY, Terminal-Tab?). Dort beenden "
                 f"(screen: Ctrl-A dann K). Mit 'lsof {port}' siehst du, wer es hält.",
                 f"{port} is busy - another program is using the console "
                 "(screen, minicom, PuTTY, terminal tab?). Close it there "
                 f"(screen: Ctrl-A then K). 'lsof {port}' shows who holds it.")
    if errno == 2 or "No such file" in msg:
        return _(f"{port} existiert nicht mehr – Kabel wurde abgezogen.",
                 f"{port} no longer exists - the cable was unplugged.")
    if errno == 6 or "Device not configured" in msg:
        return _(f"{port}: Gerät nicht mehr verbunden (Kabel abgezogen oder Adapter abgestürzt).",
                 f"{port}: device no longer connected (cable unplugged or adapter crashed).")
    if errno == 5 or "Input/output error" in msg:
        return _(f"{port}: Ein-/Ausgabefehler – Adapter defekt oder Kabel wackelt.",
                 f"{port}: I/O error - adapter defective or cable loose.")
    return _(f"Serieller Fehler auf {port}: {msg}", f"Serial error on {port}: {msg}")


def oeffne_port(port: str, baud: int):
    try:
        return serial.Serial(
            port=port, baudrate=baud, bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
            timeout=0.3, write_timeout=3, xonxoff=False, rtscts=False, dsrdtr=False,
            exclusive=True if os.name == "posix" else None,
        )
    except (serial.SerialException, OSError, ValueError) as e:
        raise ResetError(erklaere_serial_fehler(e, port)) from e


def lies(ser) -> str:
    try:
        data = ser.read(max(1, ser.in_waiting))
    except (serial.SerialException, OSError) as e:
        raise ConnectionLost(
            _("Verbindung während des Lesens verloren – Kabel abgezogen? ",
              "Connection lost while reading - cable unplugged? ")
            + f"({erklaere_serial_fehler(e, ser.port)})") from e
    text = data.decode("latin-1", errors="replace")
    return ANSI_REGEX.sub("", text)


def sende(ser, text: str) -> None:
    try:
        ser.write(text.encode("latin-1", errors="replace"))
        ser.flush()
    except serial.SerialTimeoutException as e:
        raise ConnectionLost(
            _("Schreib-Timeout – Switch/Adapter nimmt keine Daten an "
              "(Flusskontrolle hängt, Kabel lose?).",
              "Write timeout - switch/adapter does not accept data "
              "(flow control stuck, cable loose?).")) from e
    except (serial.SerialException, OSError) as e:
        raise ConnectionLost(
            _("Verbindung beim Senden verloren – Kabel abgezogen? ",
              "Connection lost while sending - cable unplugged? ")
            + f"({erklaere_serial_fehler(e, ser.port)})") from e


def lesbar(text: str) -> bool:
    """At least 80% printable characters -> baud rate is probably right."""
    if not text.strip():
        return False
    ok_chars = sum(1 for c in text if c.isprintable() or c in "\r\n\t")
    return ok_chars / len(text) >= 0.8


def wecke_switch(ser, wartezeit=2.5) -> str:
    """Sends Enter and collects the answer."""
    ser.reset_input_buffer()
    buf = ""
    for _i in range(3):
        sende(ser, "\r")
        ende = time.time() + wartezeit / 3
        while time.time() < ende:
            buf += lies(ser)
    return buf


def verbinde(port: str, profil: Profil):
    """Opens the port and finds the right baud rate if needed."""
    baudliste = [profil.baud] + [b for b in ANDERE_BAUDRATEN if b != profil.baud]
    gesehen_muell = False
    for baud in baudliste:
        ser = oeffne_port(port, baud)
        info(_(f"Teste {baud} Baud ...", f"Trying {baud} baud ..."))
        antwort = wecke_switch(ser)
        if not antwort.strip():
            ser.close()
            continue
        if lesbar(antwort):
            ok(_(f"Switch antwortet mit {baud} Baud.", f"Switch answers at {baud} baud."))
            log(f"First answer: {antwort!r}")
            return ser, antwort
        gesehen_muell = True
        warnung(_(f"{baud} Baud: Antwort unleserbar (falsche Baudrate?).",
                  f"{baud} baud: unreadable answer (wrong baud rate?)."))
        ser.close()

    if gesehen_muell:
        raise NoResponse(
            _("Es kommen Daten an, aber bei keiner Baudrate lesbarer Text. "
              "Möglich: Switch nutzt ungewöhnliche Baudrate, Kabel/Adapter defekt "
              "oder falscher Parity/Stopbit-Wert.",
              "Data arrives, but no baud rate gives readable text. "
              "Possible: switch uses an unusual baud rate, cable/adapter defective "
              "or wrong parity/stop-bit setting."))
    raise NoResponse(
        _("Der Switch antwortet auf keiner Baudrate. Mögliche Ursachen:\n"
          "   - Switch ist aus oder bootet noch (30-120 s warten)\n"
          "   - Kabel steckt nicht im CONSOLE-Port (sondern z.B. Management-Port)\n"
          "   - Falsches Kabel: Es wird ein Rollover-/Konsolenkabel gebraucht, kein normales LAN-Kabel\n"
          "   - Kabel/USB-Adapter defekt oder Treiber unpassend (Fake-Prolific-Chips!)\n"
          "   - Port am Switch deaktiviert (Cisco: Mini-USB und RJ45 gleichzeitig = USB hat Vorrang)\n"
          "   - Anderes Kabel/anderen USB-Port ausprobieren",
          "The switch does not answer at any baud rate. Possible causes:\n"
          "   - Switch is off or still booting (wait 30-120 s)\n"
          "   - Cable is not in the CONSOLE port (e.g. in the management port)\n"
          "   - Wrong cable: a rollover/console cable is needed, not a normal LAN cable\n"
          "   - Cable/USB adapter defective or wrong driver (counterfeit Prolific chips!)\n"
          "   - Port disabled on the switch (Cisco: mini-USB and RJ45 at once = USB takes priority)\n"
          "   - Try another cable / another USB port"))


# --------------------------------------------------------------------------- #
#  Dialog with the switch
# --------------------------------------------------------------------------- #
GLOBAL_REGELN = [
    (re.compile(r"--More--|<--- More --->|---- More ----", re.I), " "),
    (re.compile(r"initial configuration dialog\?.*\[yes/no\]", re.I | re.S), "no"),
    (re.compile(r"press return to get started", re.I), "\r"),
    (re.compile(r"press any key to continue|press enter to continue", re.I), "\r"),
    (re.compile(r"terminate autoinstall\?.*\[yes\]", re.I | re.S), "yes"),
]
ROMMON_REGEX = re.compile(r"(rommon \d+ ?>|switch: ?\Z|loader ?>|u-boot ?>|boot ?> ?\Z)", re.I)
USER_REGEX = re.compile(r"(user ?name|login|user):\s*\Z", re.I)
PASS_REGEX = re.compile(r"pass(word|phrase)?:\s*\Z", re.I)


class Sitzung:
    def __init__(self, ser, profil: Profil):
        self.ser = ser
        self.p = profil
        self.prompt = re.compile(profil.prompt)
        self.zugangsdaten_cache = {}

    def frage(self, was: str, geheim=False) -> str:
        if was in self.zugangsdaten_cache:
            return self.zugangsdaten_cache[was]
        wert = getpass.getpass(f"{was}: ") if geheim else input(f"{was}: ")
        self.zugangsdaten_cache[was] = wert
        return wert

    def warte(self, regeln, timeout, idle=0.6):
        """
        regeln: list of (regex, answer, final) - checked first.
        Returns: ('prompt'|'final', text)
        """
        buf, gesamt = "", ""
        letzte_daten = time.time()
        ende = time.time() + timeout
        while time.time() < ende:
            chunk = lies(self.ser)
            if chunk:
                buf += chunk
                gesamt += chunk
                letzte_daten = time.time()
                continue
            if not buf or time.time() - letzte_daten < idle:
                continue
            tail = buf[-400:]

            # global dialogs (More, initial dialog ...)
            for rx, antwort in GLOBAL_REGELN:
                if rx.search(tail):
                    sende(self.ser, antwort)
                    buf = ""
                    break
            else:
                # step-specific rules
                for rx, antwort, final in regeln:
                    if re.search(rx, tail, re.I):
                        log(f"Dialog detected ({rx!r}) -> sending {antwort!r}")
                        sende(self.ser, antwort if antwort in (" ",) else antwort + ("" if antwort == "\r" else "\r"))
                        buf = ""
                        if final:
                            fin = time.time() + 6
                            while time.time() < fin:
                                gesamt += lies(self.ser)
                            return "final", gesamt
                        break
                else:
                    if LOGIN_FAIL_REGEX.search(tail):
                        raise LoginError(
                            _("Login abgelehnt (Benutzername/Passwort falsch). "
                              "Ist der Switch passwortgeschützt und das Passwort unbekannt, "
                              "ist ein Password-Recovery per Reset-Taste/ROMMON nötig.",
                              "Login rejected (wrong username/password). "
                              "If the switch is password-protected and the password is unknown, "
                              "password recovery via reset button/ROMMON is required."))
                    if ROMMON_REGEX.search(tail):
                        raise RommonError(
                            _("Der Switch steht im Bootloader/ROMMON (kein gültiges Betriebssystem "
                              "geladen oder Boot-Fehler). Das Script kann hier nichts zurücksetzen – "
                              "Image per 'boot flash:<datei>' starten bzw. neu flashen.",
                              "The switch is in the bootloader/ROMMON (no valid operating system "
                              "loaded or boot error). This tool cannot reset anything here - "
                              "boot an image with 'boot flash:<file>' or reflash."))
                    if self.prompt.search(tail) or (
                            self.p.shell_prompt and re.search(self.p.shell_prompt, tail)):
                        return "prompt", gesamt
                    # No prompt yet: login input needed?
                    if USER_REGEX.search(tail):
                        sende(self.ser, self.frage(_("Benutzername", "Username")) + "\r")
                        buf = ""
                    elif PASS_REGEX.search(tail):
                        sende(self.ser, self.frage(_("Passwort", "Password"), geheim=True) + "\r")
                        buf = ""
                    else:
                        sende(self.ser, "\r")  # unknown output: send Enter again
                        buf = ""
        raise NoResponse(
            _(f"Timeout nach {timeout}s – der Switch hat nicht mehr reagiert. "
              f"Letzte Ausgabe: {gesamt[-300:]!r}",
              f"Timeout after {timeout}s - the switch stopped responding. "
              f"Last output: {gesamt[-300:]!r}"))

    def login(self, erste_antwort: str):
        info(_("Melde am Switch an ...", "Logging in to the switch ..."))
        sende(self.ser, "\r")
        zustand, text = self.warte([], timeout=60)
        # Juniper: from shell (%) into the CLI
        if self.p.shell_prompt and re.search(self.p.shell_prompt, text[-200:]):
            sende(self.ser, self.p.shell_zu_cli + "\r")
            self.warte([], timeout=20)

        # Cisco/HP/Arista: user mode (>) -> enable
        if self.p.enable_befehl and self.p.unpriv_prompt and \
                re.search(self.p.unpriv_prompt, text[-200:]):
            info(_("User-Modus erkannt, wechsle mit 'enable' in den privilegierten Modus ...",
                   "User mode detected, switching to privileged mode with 'enable' ..."))
            sende(self.ser, self.p.enable_befehl + "\r")
            self.warte([], timeout=30)
            sende(self.ser, "\r")
            _z, text = self.warte([], timeout=15)
            if re.search(self.p.unpriv_prompt, text[-200:]):
                raise LoginError(
                    _("'enable' wurde nicht akzeptiert – Enable-Passwort falsch oder nicht bekannt.",
                      "'enable' was not accepted - enable password wrong or unknown."))
        ok(_("Angemeldet.", "Logged in."))

    def fuehre_aus(self, schritt: Schritt):
        info(f"→ {_(*schritt.beschreibung)}  ({schritt.befehl})")
        log(f"Sending command: {schritt.befehl}")
        self.ser.reset_input_buffer()
        sende(self.ser, schritt.befehl + "\r")
        zustand, text = self.warte(schritt.regeln, timeout=schritt.timeout)
        log(f"Output: {text!r}")
        m = ERROR_REGEX.search(text)
        if m and zustand != "final":
            msg = _(f"Befehl '{schritt.befehl}' meldet Fehler: "
                    f"'{m.group(0)}'. Ausgabe: {text.strip()[-200:]!r}",
                    f"Command '{schritt.befehl}' reported an error: "
                    f"'{m.group(0)}'. Output: {text.strip()[-200:]!r}")
            if schritt.optional:
                warnung(msg + _(" (optionaler Schritt, wird übersprungen)",
                                " (optional step, skipped)"))
                return zustand
            raise CommandError(
                msg + _("\n   Möglich: falscher Switch-Typ gewählt oder fehlende Rechte.",
                        "\n   Possible: wrong switch type chosen or missing privileges."))
        return zustand


# --------------------------------------------------------------------------- #
#  Main flow
# --------------------------------------------------------------------------- #
def bestaetigung(port: str, profil: Profil) -> bool:
    print()
    print("\033[31m" + "=" * 70)
    print(_(" ACHTUNG: Die gesamte Konfiguration des Switches wird GELÖSCHT",
            " WARNING: The entire configuration of the switch will be ERASED"))
    print(_(" und der Switch startet neu!", " and the switch will reboot!"))
    print("=" * 70 + "\033[0m")
    print(f"  {_('Kabel ', 'Cable ')}: {port}")
    print(f"  {_('Typ   ', 'Type  ')}: {profil.name}")
    print(_("  Schritte:", "  Steps:"))
    for s in profil.schritte:
        print(f"    - {_(*s.beschreibung)}  ({s.befehl})")
    antwort = input(_("\nZum Fortfahren 'JA' eingeben (alles andere bricht ab): ",
                      "\nType 'YES' to continue (anything else cancels): ")).strip()
    return antwort == ("JA" if LANG == "de" else "YES")


def reset_durchfuehren(port: str, profil: Profil) -> bool:
    ser = None
    try:
        ser, erste = verbinde(port, profil)
        sitzung = Sitzung(ser, profil)
        sitzung.login(erste)
        for s in profil.schritte:
            sitzung.fuehre_aus(s)
        ok(_("Reset-Befehle gesendet – der Switch startet jetzt neu und lädt Werkseinstellungen.",
             "Reset commands sent - the switch now reboots and loads factory defaults."))
        print(_("   Hinweis: Der Neustart dauert ca. 2-5 Minuten. Erst danach neu verbinden.",
                "   Note: the reboot takes about 2-5 minutes. Reconnect only afterwards."))
        return True
    except ResetError as e:
        fehler(f"{type(e).__name__}: {e}")
        log(traceback.format_exc())
        return False
    except KeyboardInterrupt:
        warnung(_("Abbruch durch Benutzer (Strg+C). Der Switch kann in einem halben Zustand sein!",
                  "Aborted by user (Ctrl+C). The switch may be in a half-done state!"))
        return False
    except (serial.SerialException, OSError) as e:
        fehler(erklaere_serial_fehler(e, port))
        log(traceback.format_exc())
        return False
    except Exception as e:  # noqa: BLE001 - report everything else too
        fehler(_(f"Unerwarteter Fehler: {type(e).__name__}: {e}",
                 f"Unexpected error: {type(e).__name__}: {e}"))
        print(_(f"   Details im Logfile: {LOGFILE}", f"   Details in the log file: {LOGFILE}"))
        log(traceback.format_exc())
        return False
    finally:
        if ser is not None:
            try:
                ser.close()
            except Exception:  # noqa: BLE001
                pass


def main() -> int:
    print("=" * 70)
    print(" Switch-Reset / Switch Reset")
    print("=" * 70)
    log("=== Start ===")
    if sys.version_info < (3, 9):
        print("Python 3.9+ required / benötigt.")
        return 1

    waehle_sprache()
    print()

    while True:
        port = waehle_port()
        if port is None:
            return 0
        profil = waehle_profil()
        if profil is None:
            return 0
        if not bestaetigung(port, profil):
            warnung(_("Abgebrochen – es wurde nichts verändert.", "Cancelled - nothing was changed."))
        else:
            reset_durchfuehren(port, profil)

        if input(_("\nNoch einen Switch zurücksetzen? [j/N]: ",
                   "\nReset another switch? [y/N]: ")).strip().lower() not in ("j", "y"):
            print(_(f"Fertig. Protokoll: {LOGFILE}", f"Done. Log: {LOGFILE}"))
            return 0


if __name__ == "__main__":
    code = 0
    try:
        code = main()
    except KeyboardInterrupt:
        print("\n" + _("Beendet.", "Exited."))
        code = 130
    except Exception as e:  # noqa: BLE001
        fehler(_(f"Unerwarteter Fehler: {type(e).__name__}: {e}",
                 f"Unexpected error: {type(e).__name__}: {e}"))
        log(traceback.format_exc())
        code = 1
    # As a built program (double-click) keep the window open so messages can be read
    if getattr(sys, "frozen", False):
        try:
            input("\n" + _("Enter drücken zum Beenden ...", "Press Enter to exit ..."))
        except (EOFError, KeyboardInterrupt):
            pass
    sys.exit(code)
