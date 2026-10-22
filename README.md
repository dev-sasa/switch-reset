# Switch-Reset über Konsolenkabel

Mit diesem Programm setzt du Switche auf Werkseinstellungen zurück. Du brauchst nur ein Konsolenkabel (USB-Seriell). Python musst du nicht installieren.

> **Achtung:** Die komplette Konfiguration des Switches wird gelöscht und der Switch startet neu. Das lässt sich nicht rückgängig machen.

## 1. Was du brauchst

- Den Switch, eingeschaltet
- Ein Konsolenkabel:
  - USB-Seriell-Adapter plus Rollover-Kabel (RJ45 auf Console-Port), oder
  - Mini-USB-/USB-C-Kabel, wenn der Switch einen USB-Konsolenport hat
- Die Programmdatei (kein Python nötig):
  - **Windows:** `switch_reset.exe`
  - **Mac / Linux:** `switch_reset`
  - Download: GitHub-Reiter **Actions** → letzter Lauf → **Artifacts**. Oder selbst bauen (Abschnitt 6).

## 2. Kabel anschließen

1. Kabel in den **CONSOLE**-Port des Switches stecken. Nicht in einen normalen LAN-Port und nicht in den Management-Port.
2. USB-Seite in den Computer stecken.
3. Switch einschalten. Nach dem Einschalten 1–2 Minuten warten, bis er gebootet hat.

**Treiber:** Meldet das Programm später „Kein Konsolenkabel gefunden“, fehlt evtl. ein Treiber. Gängige Chips sind FTDI, Prolific PL2303, Silicon Labs CP210x und WCH CH340. Bei Cisco-Mini-USB-Ports hilft der „Cisco USB Console Driver“. Windows-Hinweis: Im Gerätemanager unter „Anschlüsse (COM & LPT)“ muss das Kabel als COM-Port auftauchen.

## 3. Programm starten

**Mac**

Per Doppelklick auf `switch_reset`, oder im Terminal:

```bash
cd Pfad/zum/Ordner/mit/der/Datei
./switch_reset
```

Beim ersten Start von einem fremden Mac blockiert macOS die Datei evtl. Dann Rechtsklick, „Öffnen“ und bestätigen. Oder im Terminal:

```bash
xattr -d com.apple.quarantine switch_reset
chmod +x switch_reset
```

**Windows**

Doppelklick auf `switch_reset.exe`. Bei der SmartScreen-Warnung auf „Weitere Informationen“ und dann „Trotzdem ausführen“ klicken.

## 4. Bedienung

1. **Kabel wählen:** Das Programm listet alle gefundenen Kabel mit Nummer auf. Tippe die Nummer ein und drücke Enter.
   - `R` sucht erneut, `Q` beendet.
2. **Switch-Typ wählen:** Tippe die Nummer des Herstellers ein.

   | Nr. | Typ | Login (falls nötig) |
   |---|---|---|
   | 1 | Cisco IOS / IOS-XE (Catalyst) | je nach Konfiguration |
   | 2 | HP ProCurve / Aruba OS-Switch | je nach Konfiguration |
   | 3 | Aruba CX | `admin`, ohne Passwort |
   | 4 | Juniper EX | `root` |
   | 5 | Extreme EXOS / Switch Engine | `admin`, ohne Passwort |
   | 6 | Arista EOS | `admin`, ohne Passwort |
   | 7 | Huawei VRP | `admin` / `admin@huawei.com` |

3. **Bestätigen:** Das Programm zeigt dir noch einmal Kabel, Typ und die Schritte. Tippe `JA` (Großbuchstaben) ein. Alles andere bricht ab, ohne etwas zu ändern.
4. **Automatischer Ablauf:** Das Programm verbindet sich und probiert dabei bei Bedarf mehrere Baudraten durch. Danach meldet es sich am Switch an. Wenn nötig, fragt es dich nach Benutzername und Passwort. Die Passworteingabe bleibt unsichtbar, das ist normal. Zum Schluss löscht es die Konfiguration und startet den Switch neu.
5. **Fertig:** Bei Erfolg steht „Reset-Befehle gesendet“ da. Der Neustart dauert etwa 2–5 Minuten. Erst danach kannst du dich wieder mit dem Switch verbinden.

## 5. Probleme und Lösungen

Jeder Fehler erscheint rot auf dem Bildschirm und steht zusätzlich in der Datei `switch_reset.log` (neben dem Programm).

| Meldung | Ursache und Lösung |
|---|---|
| Kein Konsolenkabel gefunden | Kabel nicht eingesteckt, Treiber fehlt oder Kabel defekt. USB-Port wechseln, Treiber installieren. |
| Port ist belegt / Zugriff verweigert | Ein anderes Programm nutzt das Kabel (PuTTY, Tera Term, `screen`, Terminal-Tab). Dort die Verbindung schließen. Auf dem Mac zeigt `lsof /dev/cu.xxx`, wer den Port hält. |
| Switch antwortet auf keiner Baudrate | Kabel steckt im falschen Port, Switch ist aus oder bootet noch, oder du nutzt ein normales LAN-Kabel statt eines Konsolenkabels. Außerdem kann das Kabel defekt sein. Bei Cisco hat der Mini-USB-Port Vorrang vor dem RJ45-Port. |
| Antwort unleserlich | Falsche Baudrate oder defekter Adapter. Anderen Adapter probieren. |
| Login abgelehnt / enable nicht akzeptiert | Passwort falsch oder unbekannt. Dann ist eine Passwort-Wiederherstellung am Gerät nötig (Reset-Taste oder ROMMON). Das kann das Programm nicht. |
| Switch steht im ROMMON/Bootloader | Es ist kein gültiges Betriebssystem geladen. Image von Hand starten oder neu aufspielen. |
| Befehl meldet Fehler | Wahrscheinlich falscher Switch-Typ gewählt. Neu starten und den richtigen Typ wählen. |
| Verbindung verloren / Schreib-Timeout | Kabel wurde abgezogen oder wackelt. Der Switch kann in einem halben Zustand sein: neu verbinden und den Vorgang wiederholen. |
| Timeout, Switch reagiert nicht mehr | Switch hängt oder bootet. Warten und noch einmal versuchen. |
| Abbruch mit Strg+C | Der Switch kann in einem halben Zustand sein. Vorgang wiederholen. |

## 6. Windows-Programm (.exe) selbst bauen

Das geht nicht auf dem Mac. Du brauchst einmalig einen Windows-PC mit Python:

1. Ordner auf den Windows-PC kopieren.
2. `build_windows.bat` doppelklicken.
3. Die fertige Datei liegt dann unter `dist\switch_reset.exe`. Kopiere sie auf beliebige Windows-PCs, dort braucht es kein Python.

**Alternative (ohne eigenen Windows-PC):** Das Repo enthält `.github/workflows/build.yml`. GitHub baut bei jedem Push automatisch Windows-, Mac- und Linux-Version. Du findest sie unter **Actions** → Lauf auswählen → **Artifacts**.

**Mac/Linux selbst bauen:** `./build_mac.sh` erzeugt `dist/switch_reset`.

**Mit Python direkt starten (ohne Bauen):**

```bash
pip install pyserial
python switch_reset.py
```

## 7. Hinweis zum Testen

Teste beim ersten Mal mit einem Switch, auf dem nichts Wichtiges läuft. Die Befehle sind die gängigen Standardbefehle, aber an deinen Modellen noch nicht erprobt. Wenn ein Modell anders reagiert, schick die Datei `switch_reset.log`, dann lässt sich das Programm anpassen.
