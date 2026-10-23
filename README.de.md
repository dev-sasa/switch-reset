# switch-reset

[English](README.md) | **Deutsch**

Setzt Netzwerk-Switche per Konsolenkabel auf Werkseinstellungen zurück. Das Programm findet das Kabel automatisch, fragt den Switch-Typ ab, meldet sich am Switch an, löscht die Konfiguration und startet den Switch neu. Es läuft unter Windows, macOS und Linux und braucht bei der fertigen Programmdatei keine Python-Installation.

> **Achtung:** Die komplette Konfiguration des Switches wird gelöscht und der Switch startet neu. Das lässt sich nicht rückgängig machen.

> **Hinweis:** Das Programm ist zweisprachig. Beim Start wählst du **Deutsch** oder **English**.

## Unterstützte Switche

| Nr. | Typ | Modelle (soweit bekannt) | Standard-Login (falls nötig) |
|---|---|---|---|
| 1 | Cisco IOS / IOS-XE | Catalyst 2960, 3560, 3750, 3850, 9200, 9300 | je nach Konfiguration |
| 2 | HP ProCurve / Aruba OS-Switch | 2530, 2540, 2920, 2930 | je nach Konfiguration |
| 3 | Aruba CX | 6100, 6200, 6300, 8xxx | `admin`, ohne Passwort |
| 4 | Juniper EX (Junos) | EX-Serie | `root` |
| 5 | Extreme EXOS / Switch Engine | X440, X450, X460, X620, X670 | `admin`, ohne Passwort |
| 6 | Arista EOS | 7010, 7050, 7060, 7280 | `admin`, ohne Passwort |
| 7 | Huawei VRP | S5700, S6700 | `admin` / `admin@huawei.com` |

Nicht unterstützt: Cisco Nexus/NX-OS, Cisco Small Business, Extreme VOSS/ERS, Netgear, TP-Link, D-Link, Dell, Ubiquiti, MikroTik, Ruckus/Brocade, Zyxel, Lancom.

Die Befehle sind die Standardbefehle der jeweiligen Plattform, aber an echten Geräten noch nicht getestet. Probiere es zuerst an einem Switch, auf dem nichts Wichtiges läuft.

## 1. Was du brauchst

- Den Switch, eingeschaltet
- Ein Konsolenkabel:
  - USB-Seriell-Adapter plus Rollover-Kabel (RJ45 auf Console-Port), oder
  - Mini-USB-/USB-C-Kabel, wenn der Switch einen USB-Konsolenport hat
- Die Programmdatei (kein Python nötig, nichts zu bauen): im
  [neuesten Release](../../releases/latest) herunterladen:
  - **Windows:** `switch_reset-windows.exe`
  - **macOS:** `switch_reset-macos`
  - **Linux:** `switch_reset-linux`

## 2. Kabel anschließen

1. Kabel in den **CONSOLE**-Port des Switches stecken. Nicht in einen normalen LAN-Port und nicht in den Management-Port.
2. USB-Seite in den Computer stecken.
3. Switch einschalten und 1–2 Minuten warten, bis er gebootet hat.

**Treiber:** Meldet das Programm „Kein Konsolenkabel gefunden“, fehlt evtl. ein Treiber. Gängige Chips sind FTDI, Prolific PL2303, Silicon Labs CP210x und WCH CH340. Bei Cisco-Mini-USB-Ports hilft der „Cisco USB Console Driver“. Unter Windows muss das Kabel im Gerätemanager unter „Anschlüsse (COM & LPT)“ als COM-Port auftauchen.

## 3. Programm starten

**Mac**

Doppelklick auf `switch_reset-macos`, oder im Terminal:

```bash
cd pfad/zum/ordner
./switch_reset-macos
```

Blockiert macOS die Datei beim ersten Start (z. B. nach einem Download), dann Rechtsklick, „Öffnen“ und bestätigen. Oder im Terminal:

```bash
xattr -d com.apple.quarantine switch_reset-macos
chmod +x switch_reset-macos
```

**Windows**

Doppelklick auf `switch_reset-windows.exe`. Bei der SmartScreen-Warnung auf „Weitere Informationen“ und dann „Trotzdem ausführen“ klicken.

**Linux**

```bash
chmod +x switch_reset-linux
./switch_reset-linux
```

Bei „permission denied“ am Port: `sudo usermod -aG dialout $USER` und neu einloggen.

## 4. Bedienung

1. **Sprache wählen:** `1` = Deutsch, `2` = English.
2. **Kabel wählen:** Das Programm listet alle gefundenen Kabel mit Nummer auf. Nummer eintippen und Enter drücken. `R` sucht erneut, `Q` beendet.
3. **Switch-Typ wählen:** Nummer aus der Tabelle oben eintippen.
4. **Bestätigen:** Das Programm zeigt Kabel, Typ und die Schritte noch einmal. Tippe `JA` (im englischen Modus `YES`) ein. Alles andere bricht ab, ohne etwas zu ändern.
5. **Automatischer Ablauf:** Das Programm verbindet sich, probiert bei Bedarf mehrere Baudraten durch, meldet sich an (fragt nach Benutzername und Passwort, wenn nötig; die Passworteingabe bleibt unsichtbar, das ist normal), löscht die Konfiguration und startet den Switch neu.
6. **Fertig:** Bei Erfolg meldet das Programm, dass die Reset-Befehle gesendet wurden. Der Neustart dauert etwa 2–5 Minuten. Erst danach wieder mit dem Switch verbinden.

## 5. Probleme und Lösungen

Jeder Fehler erscheint rot auf dem Bildschirm und steht zusätzlich in `switch_reset.log` neben dem Programm.

| Problem | Ursache und Lösung |
|---|---|
| Kein Konsolenkabel gefunden | Kabel nicht eingesteckt, Treiber fehlt oder Kabel defekt. Anderen USB-Port probieren, Treiber installieren. |
| Port belegt / Zugriff verweigert | Ein anderes Programm nutzt das Kabel (PuTTY, Tera Term, `screen`, anderes Terminal). Dort die Verbindung schließen. Auf dem Mac zeigt `lsof /dev/cu.xxx`, wer den Port hält. |
| Switch antwortet auf keiner Baudrate | Kabel steckt im falschen Port, Switch ist aus oder bootet noch, oder du nutzt ein normales LAN-Kabel statt eines Konsolenkabels. Das Kabel kann auch defekt sein. Bei Cisco hat der Mini-USB-Port Vorrang vor RJ45. |
| Antwort unleserlich | Falsche Baudrate oder defekter Adapter. Anderen Adapter probieren. |
| Login abgelehnt / enable nicht akzeptiert | Passwort falsch oder unbekannt. Dann ist eine Passwort-Wiederherstellung am Gerät nötig (Reset-Taste oder ROMMON). Das kann das Programm nicht. |
| Switch steht im ROMMON / Bootloader | Es ist kein gültiges Betriebssystem geladen. Image von Hand starten oder neu aufspielen. |
| Befehl meldet Fehler | Wahrscheinlich falscher Switch-Typ gewählt. Neu starten und den richtigen wählen. |
| Verbindung verloren / Schreib-Timeout | Kabel wurde abgezogen oder wackelt. Der Switch kann in einem halben Zustand sein: neu verbinden und wiederholen. |
| Timeout, Switch reagiert nicht mehr | Switch hängt oder bootet. Warten und noch einmal versuchen. |
| Abbruch mit Strg+C | Der Switch kann in einem halben Zustand sein. Vorgang wiederholen. |

## 6. Programm selbst bauen (nur für Entwickler)

Das brauchst du **nicht**, um das Tool zu benutzen. Lade einfach das Release oben herunter.

**Windows (`.exe`)** – muss einmalig auf Windows mit installiertem Python gebaut werden:

1. Ordner auf den Windows-PC kopieren.
2. `build_windows.bat` doppelklicken.
3. Die fertige Datei liegt unter `dist\switch_reset.exe`. Auf beliebige Windows-PCs kopieren, dort braucht es kein Python.

**Ohne eigenen Windows-PC:** Das Repo enthält `.github/workflows/build.yml`. GitHub baut die Windows-, Mac- und Linux-Version automatisch. Ein Versions-Tag (z. B. `git tag v1.0.0 && git push origin v1.0.0`) veröffentlicht sie als Release.

**Mac / Linux:** `./build_mac.sh` erzeugt `dist/switch_reset`.

**Direkt mit Python starten (ohne Bauen):**

```bash
pip install pyserial
python switch_reset.py
```

## 7. Weiteren Switch-Typ ergänzen

In `switch_reset.py` einen neuen `Profil(...)`-Eintrag zur Liste `PROFILE` hinzufügen: Baudrate, Prompt-Muster und die Befehle mit den Rückfragen, die beantwortet werden müssen. Texte als Tupel `("Deutsch", "English")`. Verhält sich ein Modell anders als erwartet, zeigt `switch_reset.log` genau, was der Switch geantwortet hat.

## Mitmachen / Feedback

Dein Switch-Modell oder Hersteller fehlt? Fehler gefunden? Eröffne ein [Issue](../../issues) oder schick einen Pull Request. Wenn sich ein Modell anders verhält als erwartet, hänge deine `switch_reset.log` an (vorher Passwörter und IP-Adressen entfernen). Dann lässt sich ein Profil leicht ergänzen oder korrigieren.

---

Erstellt von [Sasa](https://sasa-dev.de)
