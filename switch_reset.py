#!/usr/bin/env python3
"""
Switch-Reset über Konsolenkabel (USB-Seriell / Rollover)

Ablauf:
  1. Sucht angeschlossene Konsolenkabel (USB-Seriell-Adapter) und listet sie auf
  2. Du wählst per Zahl das Kabel aus
  3. Du wählst den Switch-Typ
  4. Das Script verbindet sich, loggt sich ein, löscht die Konfiguration und startet neu

Voraussetzung:  pip install pyserial     (Windows)   /   pip3 install pyserial   (macOS/Linux)
Aufruf:         python switch_reset.py   (Windows)   /   python3 switch_reset.py (macOS/Linux)

Läuft unter Windows (COMx), macOS (/dev/cu.*) und Linux (/dev/ttyUSB*, /dev/ttyACM*).
Alle Fehler werden auf dem Bildschirm UND in switch_reset.log (neben dem Script) ausgegeben.
"""

from __future__ import annotations

import getpass
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime

IS_WINDOWS = os.name == "nt"

# Windows: UTF-8-Ausgabe (sonst Crash bei Umlauten/Pfeilen in cmd/PowerShell)
# und ANSI-Farben in der Konsole aktivieren.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
if IS_WINDOWS:
    os.system("")  # schaltet VT100/ANSI-Verarbeitung der Windows-Konsole ein

LOGFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "switch_reset.log")


# --------------------------------------------------------------------------- #
#  Logging / Ausgabe
# --------------------------------------------------------------------------- #
def log(text: str) -> None:
    try:
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {text}\n")
    except OSError:
        pass  # Logfile ist optional


def info(text: str) -> None:
    print(text)
    log(text)


def fehler(text: str) -> None:
    print(f"\033[31m[FEHLER] {text}\033[0m")
    log(f"FEHLER: {text}")


def warnung(text: str) -> None:
    print(f"\033[33m[WARNUNG] {text}\033[0m")
    log(f"WARNUNG: {text}")


def ok(text: str) -> None:
    print(f"\033[32m[OK] {text}\033[0m")
    log(f"OK: {text}")


# --------------------------------------------------------------------------- #
#  pyserial prüfen
# --------------------------------------------------------------------------- #
try:
    import serial
    import serial.tools.list_ports
except ImportError:
    fehler("Das Python-Modul 'pyserial' ist nicht installiert.")
    print("  Installation:  " + ("pip install pyserial   (oder: py -m pip install pyserial)"
                                 if IS_WINDOWS else "pip3 install pyserial"))
    print("  Falls pip meldet 'externally-managed-environment':")
    print("     python3 -m venv .venv && source .venv/bin/activate && pip install pyserial")
    sys.exit(1)


# --------------------------------------------------------------------------- #
#  Eigene Exceptions (jede mit klarer Fehlermeldung)
# --------------------------------------------------------------------------- #
class ResetError(Exception):
    """Basisklasse für alle erwarteten Fehler."""


class KeineAntwort(ResetError):
    pass


class LoginFehler(ResetError):
    pass


class BefehlsFehler(ResetError):
    pass


class VerbindungVerloren(ResetError):
    pass


class RommonFehler(ResetError):
    pass


# --------------------------------------------------------------------------- #
#  Switch-Profile
# --------------------------------------------------------------------------- #
@dataclass
class Schritt:
    beschreibung: str
    befehl: str
    # (regex, antwort, final) – final=True: nach der Antwort ist Schluss (Neustart läuft)
    regeln: list = field(default_factory=list)
    optional: bool = False  # Fehler bei diesem Schritt nur als Warnung behandeln
    timeout: int = 30


@dataclass
class Profil:
    name: str
    baud: int
    prompt: str  # Regex für einen Prompt am Zeilenende
    schritte: list
    enable_befehl: str | None = None  # z.B. "enable" bei Cisco/HP
    unpriv_prompt: str | None = None  # Regex: Prompt im User-Modus (-> enable nötig)
    shell_prompt: str | None = None   # z.B. Juniper "%"
    shell_zu_cli: str | None = None
    hinweis: str = ""


GENERIC_PROMPT = r"[\w\-\.\(\)/@:~ ]{1,60}[>#]\s*\Z"

PROFILE = [
    Profil(
        name="Cisco IOS / IOS-XE (Catalyst 2960/3560/3750/9200/9300 ...)",
        baud=9600,
        prompt=GENERIC_PROMPT,
        unpriv_prompt=r"[\w\-\.\(\)/@:~]{1,60}>\s*\Z",
        enable_befehl="enable",
        schritte=[
            Schritt("Startup-Config löschen", "write erase",
                    [(r"\[confirm\]", "\r", False)]),
            Schritt("VLAN-Datenbank (vlan.dat) löschen", "delete flash:vlan.dat",
                    [(r"Delete filename.*\?", "\r", False),
                     (r"\[confirm\]", "\r", False)],
                    optional=True),
            Schritt("Neustart", "reload",
                    [(r"\[yes/no\]", "no", False),
                     (r"\[confirm\]", "\r", True)]),
        ],
        hinweis="Löscht startup-config und vlan.dat, dann Neustart.",
    ),
    Profil(
        name="HP ProCurve / Aruba OS-Switch (2530/2540/2920/2930 ...)",
        baud=9600,
        prompt=GENERIC_PROMPT,
        unpriv_prompt=r"[\w\-\.\(\)/@:~]{1,60}>\s*\Z",
        enable_befehl="enable",
        schritte=[
            Schritt("Startup-Config löschen + Neustart", "erase startup-config",
                    [(r"\[y/n\]", "y", True)]),
        ],
        hinweis="'erase startup-config' setzt auf Werkseinstellungen und bootet neu.",
    ),
    Profil(
        name="Aruba CX (6100/6200/6300/8xxx ...)",
        baud=115200,
        prompt=GENERIC_PROMPT,
        schritte=[
            Schritt("Startup-Config löschen", "erase startup-config",
                    [(r"\(y/n\)", "y", False)]),
            Schritt("Neustart", "boot system",
                    [(r"save.*\(y/n\)", "n", False),
                     (r"\(y/n\)", "y", True)]),
        ],
        hinweis="Standard-Login bei Werkseinstellung: admin (ohne Passwort).",
    ),
    Profil(
        name="Juniper EX (Junos)",
        baud=9600,
        prompt=r"[\w\-\.@:]{1,60}[>#]\s*\Z",
        shell_prompt=r"[\w\-\.@:]{1,60}%\s*\Z",
        shell_zu_cli="cli",
        schritte=[
            Schritt("Komplett-Reset (zeroize) + Neustart", "request system zeroize",
                    [(r"\[yes,no\]", "yes", True)]),
        ],
        hinweis="Login meist als 'root'. Zeroize löscht ALLES inkl. Logs.",
    ),
    Profil(
        name="Extreme Networks EXOS / Switch Engine (X440/X450/X460/X620/X670 ...)",
        baud=9600,
        prompt=GENERIC_PROMPT,
        schritte=[
            Schritt("Komplett-Reset + Neustart", "unconfigure switch all",
                    [(r"\(y/N\)|\[y/N\]|\(y/n\)|\[y/n\]", "y", True)]),
        ],
        hinweis="Standard-Login: admin (ohne Passwort). Nicht für VOSS/ERS (Avaya).",
    ),
    Profil(
        name="Arista EOS (7010/7050/7060/7280 ...)",
        baud=9600,
        prompt=GENERIC_PROMPT,
        unpriv_prompt=r"[\w\-\.\(\)/@:~]{1,60}>\s*\Z",
        enable_befehl="enable",
        schritte=[
            Schritt("Startup-Config löschen", "write erase",
                    [(r"\[confirm\]|\[yes/no", "\r", False)]),
            Schritt("Neustart", "reload",
                    [(r"yes/no", "no", False),
                     (r"\[confirm\]", "\r", True)]),
        ],
        hinweis="Login meist 'admin' (ohne Passwort). Danach startet der Switch im ZTP-Modus.",
    ),
    Profil(
        name="Huawei VRP (S5700/S6700 ...)",
        baud=9600,
        prompt=r"(<[^<>\r\n]{1,60}>|\[[^\[\]\r\n]{1,60}\])\s*\Z",
        schritte=[
            Schritt("Gespeicherte Config löschen", "reset saved-configuration",
                    [(r"\[Y/N\]", "y", False)]),
            Schritt("Neustart", "reboot",
                    [(r"save.*\[Y/N\]", "n", False),
                     (r"\[Y/N\]", "y", True)]),
        ],
        hinweis="Standard-Login: admin / admin@huawei.com",
    ),
]

# Baudraten, die automatisch probiert werden, wenn nur Müll ankommt
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
#  Kabel finden
# --------------------------------------------------------------------------- #
def finde_konsolenkabel():
    """Gibt Liste der seriellen Ports zurück, die wie Konsolenkabel aussehen."""
    ports = []
    for p in serial.tools.list_ports.comports():
        dev = p.device
        # macOS: nur die cu.* Geräte (tty.* blockiert beim Öffnen), Bluetooth/Debug raus
        if sys.platform == "darwin":
            if not dev.startswith("/dev/cu."):
                continue
            if any(x in dev.lower() for x in ("bluetooth", "debug-console", "wlan-debug")):
                continue
        else:
            if not any(x in dev for x in ("ttyUSB", "ttyACM", "ttyS", "COM", "rfcomm")):
                continue
            if "ttyS" in dev and p.hwid in ("n/a", ""):
                continue  # virtuelle, nicht belegte Onboard-Ports
        ports.append(p)
    return sorted(ports, key=lambda x: x.device)


def zeige_ports(ports):
    print()
    print("Gefundene Konsolenkabel:")
    print("-" * 70)
    for i, p in enumerate(ports, 1):
        vidpid = f"{p.vid:04x}:{p.pid:04x}" if p.vid is not None else "----:----"
        beschr = p.description if p.description and p.description != "n/a" else "Unbekannt"
        print(f"  [{i}] {p.device}")
        print(f"      {beschr}  (USB-ID {vidpid})"
              + (f"  Hersteller: {p.manufacturer}" if p.manufacturer else ""))
    print("-" * 70)


def waehle_port():
    while True:
        try:
            ports = finde_konsolenkabel()
        except Exception as e:  # noqa: BLE001
            fehler(f"Port-Suche fehlgeschlagen: {e}")
            log(traceback.format_exc())
            ports = []

        if not ports:
            fehler("Kein Konsolenkabel gefunden.")
            print("  Mögliche Ursachen:")
            print("   - USB-Seriell-Adapter nicht eingesteckt / Kabel defekt / USB-Hub ohne Strom")
            print("   - Treiber fehlt (FTDI, Prolific PL2303, Silicon Labs CP210x, WCH CH340)")
            if IS_WINDOWS:
                print("     Windows: Im Gerätemanager unter 'Anschlüsse (COM & LPT)' nachsehen.")
                print("     Steht das Gerät unter 'Andere Geräte' mit gelbem Ausrufezeichen,")
                print("     fehlt der Treiber (Hersteller-Treiber installieren, neu einstecken).")
            else:
                print("     macOS: Treiber vom Hersteller installieren, danach in")
                print("     Systemeinstellungen > Datenschutz & Sicherheit freigeben und neu einstecken")
            print("   - Cisco-Mini-USB-Konsole: Treiber nötig (Cisco USB Console Driver)")
            print("   - Nur ein Netzwerkkabel statt Konsolenkabel eingesteckt")
            antwort = input("\n[R] erneut suchen   [Q] beenden: ").strip().lower()
            if antwort == "q":
                return None
            continue

        zeige_ports(ports)
        antwort = input("Nummer des Kabels wählen  ([R] neu suchen, [Q] beenden): ").strip().lower()
        if antwort == "q":
            return None
        if antwort in ("r", ""):
            continue
        if not antwort.isdigit() or not (1 <= int(antwort) <= len(ports)):
            fehler(f"'{antwort}' ist keine gültige Auswahl (1-{len(ports)}).")
            continue
        return ports[int(antwort) - 1].device


def waehle_profil():
    print()
    print("Welcher Switch hängt hinter dem Kabel?")
    print("-" * 70)
    for i, p in enumerate(PROFILE, 1):
        print(f"  [{i}] {p.name}")
        print(f"      {p.hinweis}")
    print("-" * 70)
    while True:
        antwort = input("Nummer wählen ([Q] beenden): ").strip().lower()
        if antwort == "q":
            return None
        if antwort.isdigit() and 1 <= int(antwort) <= len(PROFILE):
            return PROFILE[int(antwort) - 1]
        fehler(f"'{antwort}' ist keine gültige Auswahl (1-{len(PROFILE)}).")


# --------------------------------------------------------------------------- #
#  Serielle Verbindung
# --------------------------------------------------------------------------- #
def erklaere_serial_fehler(e: Exception, port: str) -> str:
    msg = str(e)
    errno = getattr(e, "errno", None)
    if IS_WINDOWS:
        low = msg.lower()
        if "access is denied" in low or "zugriff verweigert" in low or "permissionerror" in low:
            return (f"{port} kann nicht geöffnet werden (Zugriff verweigert). Meist belegt ein "
                    "anderes Programm den COM-Port (PuTTY, Tera Term, SecureCRT, Arduino IDE, "
                    "anderes Terminal-Fenster). Dort die Verbindung schließen und erneut versuchen.")
        if "filenotfound" in low or "cannot find the file" in low or "kann die angegebene datei nicht" in low \
                or "could not open port" in low:
            return (f"{port} existiert nicht (mehr) – Kabel abgezogen oder Treiber neu gestartet. "
                    "Im Gerätemanager die aktuelle COM-Nummer prüfen.")
        if "device attached to the system is not functioning" in low or "ein an das system" in low:
            return (f"{port}: Adapter reagiert nicht (häufig bei gefälschten Prolific-Chips mit "
                    "neuem Treiber). Älteren PL2303-Treiber (3.8.x) installieren oder anderen Adapter nutzen.")
    if errno == 13 or "Permission denied" in msg:
        hint = (f"Keine Berechtigung für {port}. "
                + ("Linux: 'sudo usermod -aG dialout $USER' und neu einloggen. "
                   if sys.platform.startswith("linux") else
                   "macOS: Terminal evtl. Zugriff geben / Treiber freigeben. "))
        return hint
    if errno in (11, 35) or "busy" in msg.lower() or "resource temporarily" in msg.lower() \
            or "could not exclusively lock" in msg.lower():
        return (f"{port} ist belegt – ein anderes Programm nutzt die Konsole "
                "(screen, minicom, PuTTY, Terminal-Tab?). Dort beenden "
                "(screen: Ctrl-A dann K). Mit 'lsof " + port + "' siehst du, wer es hält.")
    if errno == 2 or "No such file" in msg:
        return f"{port} existiert nicht mehr – Kabel wurde abgezogen."
    if errno == 6 or "Device not configured" in msg:
        return f"{port}: Gerät nicht mehr verbunden (Kabel abgezogen oder Adapter abgestürzt)."
    if errno == 5 or "Input/output error" in msg:
        return f"{port}: Ein-/Ausgabefehler – Adapter defekt oder Kabel wackelt."
    return f"Serieller Fehler auf {port}: {msg}"


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
        raise VerbindungVerloren(
            "Verbindung während des Lesens verloren – Kabel abgezogen? "
            f"({erklaere_serial_fehler(e, ser.port)})") from e
    text = data.decode("latin-1", errors="replace")
    return ANSI_REGEX.sub("", text)


def sende(ser, text: str) -> None:
    try:
        ser.write(text.encode("latin-1", errors="replace"))
        ser.flush()
    except serial.SerialTimeoutException as e:
        raise VerbindungVerloren(
            "Schreib-Timeout – Switch/Adapter nimmt keine Daten an "
            "(Flusskontrolle hängt, Kabel lose?).") from e
    except (serial.SerialException, OSError) as e:
        raise VerbindungVerloren(
            "Verbindung beim Senden verloren – Kabel abgezogen? "
            f"({erklaere_serial_fehler(e, ser.port)})") from e


def lesbar(text: str) -> bool:
    """Mind. 80% druckbare Zeichen -> Baudrate stimmt vermutlich."""
    if not text.strip():
        return False
    ok_chars = sum(1 for c in text if c.isprintable() or c in "\r\n\t")
    return ok_chars / len(text) >= 0.8


def wecke_switch(ser, wartezeit=2.5) -> str:
    """Sendet Enter und sammelt die Antwort."""
    ser.reset_input_buffer()
    buf = ""
    for _ in range(3):
        sende(ser, "\r")
        ende = time.time() + wartezeit / 3
        while time.time() < ende:
            buf += lies(ser)
    return buf


def verbinde(port: str, profil: Profil):
    """Öffnet den Port und findet bei Bedarf die richtige Baudrate."""
    baudliste = [profil.baud] + [b for b in ANDERE_BAUDRATEN if b != profil.baud]
    gesehen_muell = False
    for baud in baudliste:
        ser = oeffne_port(port, baud)
        info(f"Teste {baud} Baud ...")
        antwort = wecke_switch(ser)
        if not antwort.strip():
            ser.close()
            # Stille: andere Baudrate bringt meist nichts, aber kurz weitertesten
            continue
        if lesbar(antwort):
            ok(f"Switch antwortet mit {baud} Baud.")
            log(f"Erste Antwort: {antwort!r}")
            return ser, antwort
        gesehen_muell = True
        warnung(f"{baud} Baud: Antwort unleserbar (falsche Baudrate?).")
        ser.close()

    if gesehen_muell:
        raise KeineAntwort(
            "Es kommen Daten an, aber bei keiner Baudrate lesbarer Text. "
            "Möglich: Switch nutzt ungewöhnliche Baudrate, Kabel/Adapter defekt "
            "oder falscher Parity/Stopbit-Wert.")
    raise KeineAntwort(
        "Der Switch antwortet auf keiner Baudrate. Mögliche Ursachen:\n"
        "   - Switch ist aus oder bootet noch (30-120 s warten)\n"
        "   - Kabel steckt nicht im CONSOLE-Port (sondern z.B. Management-Port)\n"
        "   - Falsches Kabel: Es wird ein Rollover-/Konsolenkabel gebraucht, kein normales LAN-Kabel\n"
        "   - Kabel/USB-Adapter defekt oder Treiber unpassend (Fake-Prolific-Chips!)\n"
        "   - Port am Switch deaktiviert (Cisco: Mini-USB und RJ45 gleichzeitig = USB hat Vorrang)\n"
        "   - Anderes Kabel/anderen USB-Port ausprobieren")


# --------------------------------------------------------------------------- #
#  Dialog mit dem Switch
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
        self.login_versuche = 0
        self.zugangsdaten_cache = {}

    # ---- Eingaben beim Benutzer erfragen
    def frage(self, was: str, geheim=False) -> str:
        if was in self.zugangsdaten_cache:
            return self.zugangsdaten_cache[was]
        wert = getpass.getpass(f"{was}: ") if geheim else input(f"{was}: ")
        self.zugangsdaten_cache[was] = wert
        return wert

    # ---- Lesen bis Ruhe, dann Muster prüfen
    def warte(self, regeln, timeout, idle=0.6):
        """
        regeln: Liste (regex, antwort, final) – wird zuerst geprüft.
        Rückgabe: ('prompt'|'final', Text)
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

            # globale Dialoge (More, initial dialog ...)
            for rx, antwort in GLOBAL_REGELN:
                if rx.search(tail):
                    sende(self.ser, antwort)
                    buf = ""
                    break
            else:
                # schritt-spezifische Regeln
                for rx, antwort, final in regeln:
                    if re.search(rx, tail, re.I):
                        log(f"Dialog erkannt ({rx!r}) -> sende {antwort!r}")
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
                        raise LoginFehler(
                            "Login abgelehnt (Benutzername/Passwort falsch). "
                            "Ist der Switch passwortgeschützt und das Passwort unbekannt, "
                            "ist ein Password-Recovery per Reset-Taste/ROMMON nötig.")
                    if ROMMON_REGEX.search(tail):
                        raise RommonFehler(
                            "Der Switch steht im Bootloader/ROMMON (kein gültiges Betriebssystem "
                            "geladen oder Boot-Fehler). Das Script kann hier nichts zurücksetzen – "
                            "Image per 'boot flash:<datei>' starten bzw. neu flashen.")
                    if self.prompt.search(tail) or (
                            self.p.shell_prompt and re.search(self.p.shell_prompt, tail)):
                        return "prompt", gesamt
                    # Noch kein Prompt: Eingaben für Login nötig?
                    if USER_REGEX.search(tail):
                        sende(self.ser, self.frage("Benutzername") + "\r")
                        buf = ""
                    elif PASS_REGEX.search(tail):
                        sende(self.ser, self.frage("Passwort", geheim=True) + "\r")
                        buf = ""
                    else:
                        # unbekannte Ausgabe: noch einmal Enter schicken
                        sende(self.ser, "\r")
                        buf = ""
        raise KeineAntwort(
            f"Timeout nach {timeout}s – der Switch hat nicht mehr reagiert. "
            f"Letzte Ausgabe: {gesamt[-300:]!r}")

    # ---- Einloggen & in privilegierten Modus
    def login(self, erste_antwort: str):
        info("Melde am Switch an ...")
        sende(self.ser, "\r")
        zustand, text = self.warte([], timeout=60)
        # Juniper: von Shell (%) in die CLI
        if self.p.shell_prompt and re.search(self.p.shell_prompt, text[-200:]):
            sende(self.ser, self.p.shell_zu_cli + "\r")
            self.warte([], timeout=20)

        # Cisco/HP: User-Modus (>) -> enable
        if self.p.enable_befehl and self.p.unpriv_prompt and \
                re.search(self.p.unpriv_prompt, text[-200:]):
            info("User-Modus erkannt, wechsle mit 'enable' in den privilegierten Modus ...")
            sende(self.ser, self.p.enable_befehl + "\r")
            self.warte([], timeout=30)
            # Nach enable muss ein '#' kommen
            sende(self.ser, "\r")
            _, text = self.warte([], timeout=15)
            if re.search(self.p.unpriv_prompt, text[-200:]):
                raise LoginFehler(
                    "'enable' wurde nicht akzeptiert – Enable-Passwort falsch oder nicht bekannt.")
        ok("Angemeldet.")

    def fuehre_aus(self, schritt: Schritt):
        info(f"→ {schritt.beschreibung}  ({schritt.befehl})")
        log(f"Sende Befehl: {schritt.befehl}")
        self.ser.reset_input_buffer()
        sende(self.ser, schritt.befehl + "\r")
        zustand, text = self.warte(schritt.regeln, timeout=schritt.timeout)
        log(f"Ausgabe: {text!r}")
        m = ERROR_REGEX.search(text)
        if m and zustand != "final":
            msg = (f"Befehl '{schritt.befehl}' meldet Fehler: "
                   f"'{m.group(0)}'. Ausgabe: {text.strip()[-200:]!r}")
            if schritt.optional:
                warnung(msg + " (optionaler Schritt, wird übersprungen)")
                return zustand
            raise BefehlsFehler(
                msg + "\n   Möglich: falscher Switch-Typ gewählt oder fehlende Rechte.")
        return zustand


# --------------------------------------------------------------------------- #
#  Hauptablauf
# --------------------------------------------------------------------------- #
def bestaetigung(port: str, profil: Profil) -> bool:
    print()
    print("\033[31m" + "=" * 70)
    print(" ACHTUNG: Die gesamte Konfiguration des Switches wird GELÖSCHT")
    print(" und der Switch startet neu!")
    print("=" * 70 + "\033[0m")
    print(f"  Kabel : {port}")
    print(f"  Typ   : {profil.name}")
    print("  Schritte:")
    for s in profil.schritte:
        print(f"    - {s.beschreibung}  ({s.befehl})")
    return input("\nZum Fortfahren 'JA' eingeben (alles andere bricht ab): ").strip() == "JA"


def reset_durchfuehren(port: str, profil: Profil) -> bool:
    ser = None
    try:
        ser, erste = verbinde(port, profil)
        sitzung = Sitzung(ser, profil)
        sitzung.login(erste)
        for s in profil.schritte:
            sitzung.fuehre_aus(s)
        ok("Reset-Befehle gesendet – der Switch startet jetzt neu und lädt Werkseinstellungen.")
        print("   Hinweis: Der Neustart dauert ca. 2-5 Minuten. Erst danach neu verbinden.")
        return True
    except ResetError as e:
        fehler(f"{type(e).__name__}: {e}")
        log(traceback.format_exc())
        return False
    except KeyboardInterrupt:
        warnung("Abbruch durch Benutzer (Strg+C). Der Switch kann in einem halben Zustand sein!")
        return False
    except (serial.SerialException, OSError) as e:
        fehler(erklaere_serial_fehler(e, port))
        log(traceback.format_exc())
        return False
    except Exception as e:  # noqa: BLE001 – alles andere ebenfalls melden
        fehler(f"Unerwarteter Fehler: {type(e).__name__}: {e}")
        print(f"   Details im Logfile: {LOGFILE}")
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
    print(" Switch-Reset über Konsolenkabel")
    print("=" * 70)
    log("=== Start ===")
    if sys.version_info < (3, 9):
        fehler("Python 3.9 oder neuer wird benötigt.")
        return 1

    while True:
        port = waehle_port()
        if port is None:
            return 0
        profil = waehle_profil()
        if profil is None:
            return 0
        if not bestaetigung(port, profil):
            warnung("Abgebrochen – es wurde nichts verändert.")
        else:
            reset_durchfuehren(port, profil)

        if input("\nNoch einen Switch zurücksetzen? [j/N]: ").strip().lower() != "j":
            print(f"Fertig. Protokoll: {LOGFILE}")
            return 0


if __name__ == "__main__":
    code = 0
    try:
        code = main()
    except KeyboardInterrupt:
        print("\nBeendet.")
        code = 130
    except Exception as e:  # noqa: BLE001
        fehler(f"Unerwarteter Fehler: {type(e).__name__}: {e}")
        log(traceback.format_exc())
        code = 1
    # Als fertige Programmdatei (Doppelklick) Fenster offen halten, damit man Meldungen lesen kann
    if getattr(sys, "frozen", False):
        try:
            input("\nEnter drücken zum Beenden ...")
        except (EOFError, KeyboardInterrupt):
            pass
    sys.exit(code)
