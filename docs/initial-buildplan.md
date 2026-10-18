# Ketten-Roboter: Umsetzungsplan & Systemarchitektur

Oct 6, 2026 · @Max

## Überblick und Annahmen

Der Roboter wird in 9 Phasen gebaut: erst sicher fahren (Phasen 0–2), dann kartieren und autonom navigieren (3–4), danach sehen, folgen und als KI-Assistent handeln (5–8). Jede Phase endet mit einem testbaren Ergebnis, bevor die nächste beginnt.

**Grundregel für den Rechenort:** Alles, was für sicheres Fahren nötig ist, läuft auf dem Roboter. Visualisierung, Entwicklung und schwere KI laufen auf Laptop oder Cloud. Fällt WLAN oder Internet aus, bleibt der Roboter stehen statt blind weiterzufahren.

**Hardware-Stand** (bestätigt am 7. Oktober 2026) und verbleibende Annahmen:

- **Raspberry Pi 4 mit 4 GB RAM im Flirc-Alugehäuse.** Das reicht, wenn der Pi ohne Desktop läuft und RViz auf dem Laptop bleibt. Das Gehäuse kühlt passiv; die GPIO-Pins sind nur über einen Schlitz an der Unterseite erreichbar.
- **Encoder-Motoren vorhanden.** Zwei Pololu-Getriebemotoren 25D HP 6V mit Getriebe 20,4:1 und 48-CPR-Encoder (Pololu #2272, Motor RK-370SD) ersetzen die Originalmotoren des Devastator. Sie sind rund dreimal so schnell, haben mehr Drehmoment und ziehen blockiert bis zu 6,5 A. Damit gibt es Rad-Odometrie von Phase 1 an.
- **Motortreiber Pololu Dual VNH5019 Shield.** Es ersetzt den L298N und sitzt direkt auf dem Arduino. Weil es kaum Spannung verliert, begrenzt die Firmware die PWM bei einem 2S-Akku auf etwa 70 %, damit die 6-V-Motoren nicht dauerhaft mit 8,4 V laufen.
- **Antrieb = Skid-Steer.** ROS behandelt Ketten wie einen Differentialantrieb, beim Drehen rutschen die Ketten aber stark. Das beeinflusst Odometrie und Nav2-Tuning.
- **Laptop unter Windows.** Foxglove läuft dort nativ und reicht über foxglove\_bridge auf dem Pi für Visualisierung und Teleop. Für RViz2, ROS-Kommandozeile und Gazebo: Ubuntu 24.04 in WSL2 mit gespiegeltem Netzwerk (networkingMode=mirrored). Die Windows-Firewall muss dann UDP vom und zum Pi erlauben, sonst finden sich die Knoten nicht.
- **Drei Stromquellen:** Hama-Powerbank für den Pi, Nitecore-Powerbank für den USB-Hub, ein 2S-LiPo (7,4 V) für die Motoren. So bleibt der Pi stabil, wenn die Motoren beim Anfahren die Spannung einbrechen lassen.

## Systemarchitektur

Auf dem Pi arbeiten vier Schichten: Aufgaben und Dialog, Wahrnehmung und Navigation, Fahrbefehle und Sensor-Treiber. Darunter regelt der Arduino die Motoren, darüber liefern Cloud und Laptop optionale Dienste.

&#91;embedded content: Systemarchitektur · Cloud, Laptop, Roboter\]

Fällt die Cloud aus, verliert der Roboter nur Sprache und Bildverständnis; fällt der Laptop aus, nur die Überwachung. Jede Fahrbewegung läuft durch `twist_mux`, sodass Not-Halt und Teleop jede Automatik übersteuern.

## Rechenort pro Komponente

Fahren, Sensorik und Navigation laufen auf dem Pi, Echtzeit-Motorregelung auf dem Arduino, GUI und Simulation auf dem Laptop, Sprachmodell und Spracherkennung in der Cloud. Der Laptop ist für den Betrieb nicht nötig, nur für Entwicklung und Überwachung.

| Komponente | Läuft auf | Begründung |
| --- | --- | --- |
| PWM, Encoder zählen, PID-Regelung, Watchdog | Arduino | Harte Echtzeit; stoppt die Motoren, wenn 0,5 s kein Befehl kommt |
| ros2\_control mit diff\_drive\_controller | Pi | Fahrregelung muss auch ohne WLAN laufen |
| LiDAR-Treiber (sllidar\_ros2) | Pi | Sensor hängt per USB am Pi |
| IMU-Fusion (robot\_localization, EKF) | Pi | Leicht, braucht kurze Latenz |
| SLAM Toolbox (Kartierung) | Pi, Fallback Laptop | Pi 4 schafft es bei langsamer Fahrt; Scans sind klein und gehen notfalls gut über WLAN |
| Nav2 (Planer, Controller, Costmaps) | Pi | Hindernisvermeidung darf nicht vom WLAN abhängen |
| Kamera-Treiber (camera\_ros) | Pi | Kamera am CSI-Port |
| Personenerkennung | Pi + Coral | \~10–30 Bilder/s lokal, kein Videostream übers WLAN nötig |
| Person-Tracking und Folge-Regler | Pi | Muss schnell auf die Person reagieren |
| Wake-Word-Erkennung | Pi | Hört dauerhaft mit, daher lokal und privat |
| Sprachausgabe (TTS, z. B. Piper) | Pi | Läuft auf dem Pi 4 flüssig genug |
| Assistant-Bridge (LLM-Werkzeuge → ROS-Aktionen) | Pi | Sicherheitsprüfung jedes KI-Befehls passiert lokal |
| Spracherkennung (STT, Whisper) | Cloud, Alternative Laptop | Whisper ist auf dem Pi 4 zu langsam |
| Sprachmodell / Agent (z. B. Claude) | Cloud, Alternative Laptop mit Ollama | Aktuelle Modelle laufen nicht sinnvoll auf einem Pi 4 |
| Bildverständnis ("Was siehst du?") | Cloud | Einzelbild nur bei Bedarf senden |
| RViz2, Foxglove, Tastatur-Teleop, rqt | Laptop | GUI-Last gehört nicht auf den Pi |
| Gazebo-Simulation | Laptop | Für den Pi viel zu schwer |

**Faustregel:** Ein Ausfall von Laptop oder Cloud darf nur Komfort kosten, nie Sicherheit. Ohne Cloud fährt der Roboter weiter autonom, kann aber nicht mehr sprechen und verstehen.

## Hardware-Ergänzungen und Verkabelung

Plattform, Encoder-Motoren, Motortreiber-Shield, Motorschalter, Status-LEDs, IMU, Xbox-Controller, Kühlung und beide Powerbanks sind da. Es fehlen der 2S-LiPo mit Ladegerät und Anschlussmaterial, der aktive USB-Hub und die Widerstände für den Spannungsteiler. Mikrofon und Lautsprecher kommen erst in Phase 7 dazu.

| Teil | Status | Details | Ab Phase |
| --- | --- | --- | --- |
| Plattform | Vorhanden | [DFRobot Devastator](https://littlebirdelectronics.com.au/products/devastator-tank-mobile-robot-platform): Antriebsrad 43 mm Durchmesser | 0 |
| Pi-Kühlung | Vorhanden | Flirc-Alugehäuse, passiv. Den Coral nicht direkt daneben montieren, er wird selbst warm | 0 |
| Powerbank Pi | Vorhanden | Hama 12.000 mAh (44,3 Wh), USB-C 5 V / 3 A, höchstens 3 A gesamt; versorgt nur den Pi mit Kamera, IMU und LEDs | 0 |
| Motorschalter | Vorhanden | Kippschalter hinten rechts, trennt nur den Motorkreis; erst einschalten, wenn die Startup-LED dauerhaft leuchtet | 0 |
| Status-LEDs | Vorhanden | Zwei weiße LEDs vorne: Power-LED an 3,3 V, Startup-LED an GPIO 4 | 0 |
| Motoren mit Encoder | Vorhanden | [Pololu #2272](https://www.pololu.com/product/2272): 25D HP 6V, Getriebe 20,4:1, Motor RK-370SD. Ohne Last 460 U/min bei 550 mA, blockiert 5,5 kg·cm bei 6,5 A. Encoder 48 Zählschritte je Motorumdrehung, also 979,62 pro Kettenradumdrehung. Abtriebswelle 4 mm mit D-Profil, Befestigung über zwei M3-Gewinde (höchstens 6 mm tief einschrauben). Rechnerisch bis 1,04 m/s | 1 |
| Motortreiber | Vorhanden | [Pololu Dual VNH5019 Shield](https://www.pololu.com/docs/0j49/all), ersetzt den L298N: 12 A pro Kanal, 5,5–24 V, Strommessung 140 mV/A. Jumper ARDVIN=VOUT nicht stecken | 1 |
| Motorakku | Fehlt | [Gens ace 2200 mAh 2S 60C Hardcase](https://gensace.de/collections/hardcase-lipo-batteries) mit XT60-Stecker, ca. 92 × 31 × 17 mm, 108 g, 24,99 €. Liefert problemlos die bis zu 13 A, wenn beide Motoren blockieren | 1 |
| LiPo-Ladegerät | Fehlt | [SkyRC e3](https://www.kotte-zeller.de/skyrc-e3-lipo-2-3s-balance-charger-ladegeraet-230v-sk100081), 2–3S, lädt über den Balancer-Stecker, direkt an 230 V, 24,98 € | 1 |
| Anschlussmaterial Motorkreis | Fehlt | XT60-Buchse mit Kabel und offenem Ende, Flachsicherungshalter mit Kabel und 10-A-Flachsicherung, WAGO-221-Hebelklemmen, etwas 1-mm²-Kabel | 1 |
| LiPo-Zubehör | Fehlt | LiPo-Sack zum Laden und Lagern, Spannungsalarm für den Balancer-Stecker, Klettband zum Festmachen | 1 |
| Spannungsteiler | Fehlt | 2 × 10 kΩ, halbiert die Akkuspannung für A2 des Arduino; misst hinter dem Motorschalter Akkustand und Schalterstellung | 1 |
| Xbox-Controller + Empfänger | Vorhanden | Empfänger unter dem Rumpf, lief im alten Aufbau schon mit ROS 2; wird Teleop mit Totmannknopf | 1 |
| IMU | Vorhanden | SparkFun ICM-20948, bereits an I2C des Pi verdrahtet; Magnetometer in Innenräumen nicht nutzen | 2 |
| Powerbank USB-Hub | Vorhanden | Nitecore NB10000 (38,5 Wh), ein Ausgang mit 5 V / 3 A; versorgt nur den aktiven Hub | 3 |
| Aktiver USB-Hub | Fehlt | Der Pi hat 4 USB-Ports, gebraucht werden 5: Arduino, LiDAR, Xbox-Empfänger, Coral, später Mikrofon. Hängt an der Nitecore-Powerbank und darf keinen Strom in den Pi zurückspeisen | 3 |
| Mikrofon + Lautsprecher | Fehlt | USB-Mikrofon-Array + kleiner USB-Lautsprecher | 7 |

**Verkabelung im Überblick:**

- **Drei Stromkreise:** Hama-Powerbank → Pi (USB-C). Nitecore-Powerbank → aktiver USB-Hub. 2S-LiPo (XT60) → Sicherung 10 A → Motorschalter → Klemmen VIN und GND des VNH5019-Shields; Details unter *Stromversorgung und LiPo-Umgang*.
- **Arduino nur über USB versorgen:** Den Jumper ARDVIN=VOUT auf dem Shield nicht stecken. Dann bekommt der Arduino Strom nur über USB, und der Motorschalter wirkt nur auf die Motoren. Die gemeinsame Masse stellt das Shield her.
- **Arduino Uno** per USB am Pi, ab Phase 3 am Hub (serielle Verbindung, 115200 Baud), das Shield steckt direkt darauf.
- **Motoren:** links an M1A/M1B, rechts an M2A/M2B. Läuft eine Kette verkehrt herum, ihre zwei Motorleitungen tauschen.
- **Encoder:** Kabelfarben laut Pololu: Rot und Schwarz = Motor, Grün = Encoder-GND, Blau = Encoder-VCC, Gelb = Kanal A, Weiß = Kanal B. Rot und Schwarz kommen an das Shield, Blau an 5 V, Grün an GND und die Signale an den Arduino laut Tabelle unten.
- **Status-LEDs (vorhanden):** Power-LED an Pin 1 (3,3 V) und Pin 6 (GND), leuchtet, sobald der Pi Strom hat. Startup-LED an Pin 7 (GPIO 4) und Pin 9 (GND), wird zur Bereitschaftsanzeige.
- **ICM-20948 (vorhanden):** Pin 3 = SDA, Pin 5 = SCL, Pin 17 = 3,3 V, Pin 25 = GND. IMU flach und fest montieren, möglichst nahe der Drehachse.
- **USB-Geräte am Hub:** RPLidar A1M8 über seine Adapterplatine, Arduino, Xbox-Empfänger, Coral (im Standardtakt), später Mikrofon.
- **Kamera** am CSI-Port im weißen Halter vorne.

**Pinbelegung Arduino Uno mit VNH5019-Shield:**

| Arduino-Pin | Funktion |
| --- | --- |
| D2, D4, D9 | Motor links: INA, INB, PWM (Shield) |
| D7, D8, D10 | Motor rechts: INA, INB, PWM (Shield) |
| D6, D12 | Fehlermeldung EN/DIAG links, rechts (Shield) |
| A0, A1 | Strommessung links, rechts (Shield) |
| D3, D5 | Encoder links, Kanal A und B |
| A4, A5 | Encoder rechts, Kanal A und B |
| A2 | Spannungsteiler Motorakku |
| D11, D13, A3 | frei |

Das Shield belegt D2, wo ros\_arduino\_bridge den linken Encoder erwartet. Deshalb wandert er auf D3/D5; die Firmware zählt beide Encoder über Pin-Change-Interrupts.

Gemeinsame Masse aller Komponenten ist Pflicht, sonst gibt es Störungen auf der seriellen Leitung und den Encodern.

## Einschaltreihenfolge und Status-LED

Der Motorstrom kommt erst dazu, wenn der Pi gestartet ist und ROS die Motorsteuerung übernommen hat. Die weiße Startup-LED vorne zeigt diesen Moment an.

**Einschalten:**

1. Motorschalter steht auf AUS. Beide Powerbanks einschalten (Hama für den Pi, Nitecore für den USB-Hub), die Power-LED leuchtet.
2. Linux startet, ein systemd-Dienst startet den ROS-Bringup. Die Startup-LED blinkt langsam.
3. Der Knoten `status_led` prüft: Arduino antwortet, `diff_drive_controller` ist aktiv, `/scan` kommt an. Dann leuchtet die LED dauerhaft.
4. Erst jetzt den Motorschalter einschalten.

**Ausschalten:** Motorschalter aus, Pi herunterfahren (per SSH oder Tastenkombination am Xbox-Controller), warten bis die grüne Aktivitäts-LED des Pi aus bleibt, dann beide Powerbanks trennen. Bleibt der Roboter mehrere Tage stehen, auch den LiPo abstecken. Ohne Herunterfahren riskierst du eine beschädigte SD-Karte.

| Startup-LED | Bedeutung | Motorschalter |
| --- | --- | --- |
| aus | Pi bootet oder ist heruntergefahren | aus lassen |
| blinkt langsam (1 Hz) | ROS startet | aus lassen |
| leuchtet dauerhaft | Bereit | darf an |
| blinkt schnell (4 Hz) | Fehler, z. B. Arduino oder LiDAR antwortet nicht | ausschalten |

**Warum das zählt:** Öffnet der Pi die serielle Verbindung, startet der Arduino neu, und seine Pins sind 1–2 s offen. Das VNH5019-Shield hält die PWM-Eingänge dann auf LOW, die Motoren bleiben stromlos. Watchdog, Teleop und Not-Halt arbeiten aber erst, wenn ROS läuft; bis dahin bleibt der Motorkreis aus.

**Umsetzung:**

- In `/boot/firmware/config.txt` die Zeile `gpio=4=op,dl` eintragen. GPIO 4 hat beim Booten einen Pull-up; ohne die Zeile glimmt die LED schon vor dem Start.
- Knoten `status_led` (Python, im Paket `tank_bringup`) schaltet GPIO 4 mit `gpiozero` und dem lgpio-Backend. Zugriff auf `/dev/gpiochip*` per udev-Regel für den Roboter-Benutzer freigeben.
- systemd-Dienst `tank-bringup.service` startet den Launch nach `network-online.target` und schaltet beim Stoppen die LED aus.
- Firmware: Motoren starten mit PWM 0 und laufen erst bei einem gültigen Fahrbefehl; der Watchdog setzt die PWM nach 0,5 s ohne Befehl wieder auf 0. Liegt die Strommessung eines Motors länger als 0,5 s über 3 A, ist die Kette blockiert: Die Firmware schaltet ab und meldet den Fehler.
- Das Hardwareinterface liest die Spannung an A2 mit und meldet Fahrbefehle bei ausgeschaltetem Motorstrom als Warnung, statt still zu scheitern.

## Stromversorgung und LiPo-Umgang

Drei getrennte Quellen versorgen den Roboter: Jede Powerbank hat nur einen Verbraucher und bleibt unter ihren 3 A, der LiPo treibt allein die Motoren. Angeschlossen wird ohne Löten, mit Steckern, Hebelklemmen und den Schraubklemmen des Shields.

| Quelle | versorgt | Strom typisch / Spitze |
| --- | --- | --- |
| Hama 12.000 mAh, USB-C | Pi, Kamera, IMU, Status-LEDs | 1,1 A / 1,6 A |
| Nitecore NB10000, ein Ausgang | aktiver USB-Hub: LiDAR, Coral, Arduino mit Encodern, Xbox-Empfänger, später Mikrofon | 1,2 A / 2,1 A |
| 2S-LiPo 2200 mAh | Motoren über Sicherung, Motorschalter und VNH5019 | 1,5–3 A, blockiert bis 13 A |

Die Powerbanks halten grob 5–6 Stunden, der LiPo etwa eine Stunde reine Fahrzeit. Der Hub darf keinen Strom in den Pi zurückspeisen. Test: Nitecore an, Hama aus, die LEDs des Pi müssen dunkel bleiben.

**Einkaufsliste Motorkreis** (Preise vom 8. Oktober 2026, zusammen rund 50 € plus Kleinteile):

| Teil | Beispiel |
| --- | --- |
| 2S-LiPo | [Gens ace 2200 mAh 2S 60C Hardcase, XT60](https://gensace.de/collections/hardcase-lipo-batteries), 24,99 € |
| Ladegerät | [SkyRC e3](https://www.kotte-zeller.de/skyrc-e3-lipo-2-3s-balance-charger-ladegeraet-230v-sk100081), 24,98 € |
| XT60-Kabel | XT60-Buchse mit Kabel und offenem Ende, passend zum Akku-Stecker |
| Sicherung | Flachsicherungshalter mit Kabel und 10-A-Flachsicherung |
| Verbinder | WAGO-221-Hebelklemmen, etwas 1-mm²-Kabel |
| LiPo-Sack | zum Laden und Lagern |
| Spannungsalarm | wird auf den Balancer-Stecker gesteckt und piept, wenn der Akku leer wird |
| Klettband | hält den Akku im Chassis |

**Motorkreis verkabeln:** Akku (XT60) → XT60-Kabel → Sicherung 10 A → Motorschalter → Schraubklemmen VIN und GND am Shield. Die Kabel untereinander mit WAGO-Klemmen verbinden. Passt das dicke XT60-Kabel nicht in die Klemme am Shield, über eine WAGO-Klemme auf 1-mm²-Kabel wechseln.

**Regeln für den LiPo:**

- **Akku zuletzt einstecken:** Erst alles verkabeln, dann einstecken. Offene Kabelenden dürfen sich nie berühren, solange der Akku dran ist; ein Kurzschluss liefert über 100 A.
- **Sicherung nah an den Akku**, dann schützt sie die ganze Leitung. Rot an VIN, Schwarz an GND; das Shield hat einen Verpolungsschutz, trotzdem vorher prüfen.
- **Fest montieren:** Akku mit Klettband sichern, weg von Ketten und scharfen Kanten. Den Balancer-Stecker so verstauen, dass er nicht abreißt.
- **Laden:** Akku ausstecken, nur den Balancer-Stecker in den 2S-Anschluss des SkyRC e3. Im LiPo-Sack oder auf nicht brennbarer Unterlage und nie unbeaufsichtigt. Aufgeblähte oder beschädigte Akkus nicht mehr laden, sondern beim Wertstoffhof oder Händler abgeben.
- **Nicht leerfahren:** Unter 6,0 V (3,0 V pro Zelle) nimmt der Akku dauerhaft Schaden. Die Firmware warnt bei 7,0 V und schaltet die Motoren bei 6,6 V ab. Bis sie fertig ist, den Spannungsalarm auf den Balancer-Stecker stecken und nach dem Fahren wieder abziehen.
- **Nach dem Fahren:** Motorschalter aus, dann zieht nichts mehr am Akku. Bei mehreren Tagen Pause den Akku abstecken, bei mehreren Wochen halb voll lagern (etwa 7,6 V).

## Software-Stack

**Entscheidung: ROS 2 Jazzy auf Ubuntu 24.04**, auf Pi (Ubuntu Server, 64 Bit) und Laptop (Ubuntu Desktop). Jazzy ist ein LTS-Release mit Support bis Mai 2029 und hat die meisten Tutorials für genau diese Hardware.

Das neuere LTS [Lyrical Luth](https://discourse.openrobotics.org/t/ros-2-lyrical-luth-released/55021) (Mai 2026, Support bis 2031) zielt auf Ubuntu 26.04. Dagegen spricht hier der Coral-Stick: Die offiziellen PyCoral-Pakete enden bei Python 3.9, [Community-Builds](https://github.com/feranick/pycoral) reichen bis Python 3.12 – genau die Version von Ubuntu 24.04. Ein Umstieg auf Lyrical bleibt später möglich.

**Python oder C++:** Nur der ros2\_control-Hardwaretreiber muss C++ sein, weil ros2\_control Plugins in C++ lädt. Alles Rechenintensive (Nav2, SLAM Toolbox, LiDAR-Treiber, Kameratreiber) sind fertige C++-Pakete, die du nur konfigurierst. Eigene Logik schreibst du in Python.

| Paket | Sprache | Inhalt | Phase |
| --- | --- | --- | --- |
| `firmware/` (kein ROS-Paket) | Arduino C++ (PlatformIO) | Motor-PWM, Encoder, PID, serielles Protokoll, Watchdog | 1 |
| `tank_hardware` | C++ | ros2\_control-Hardwareinterface zum Arduino; Basis: [diffdrive\_arduino](https://github.com/joshnewans/diffdrive_arduino) | 1 |
| `tank_description` | URDF/Xacro | Robotermodell, Sensorpositionen, ros2\_control-Tags | 2 |
| `tank_bringup` | Python (Launch) | Startdateien, Controller- und EKF-Parameter | 1–2 |
| `tank_navigation` | YAML + Python (Launch) | SLAM-Toolbox- und Nav2-Parameter, gespeicherte Karten | 3–4 |
| `tank_interfaces` | IDL (ament\_cmake) | Eigene Messages, Services, Actions (z. B. `FollowPerson.action`) | 5 |
| `tank_perception` | Python | Coral-Personenerkennung, Tracking | 5 |
| `tank_follow` | Python | Folge-Verhalten als ROS-Action | 6 |
| `tank_assistant` | Python | Wake-Word, STT/TTS-Anbindung, LLM-Agent, Werkzeuge | 7 |
| `tank_missions` | Python | Benannte Orte, Missionen über `nav2_simple_commander` | 8 |

**Werkzeuge:** Git-Repository mit diesem Workspace, `colcon build --symlink-install` (Python-Änderungen ohne Neubau), VS Code mit Remote-SSH vom Laptop auf den Pi. Für das Netzwerk auf beiden Rechnern dieselbe `ROS_DOMAIN_ID` setzen; macht das WLAN Probleme mit der Discovery, auf Cyclone DDS oder rmw\_zenoh wechseln.

## Phase 0: Aufbau und Grundsetup

**Ziel:** Der Roboter ist mechanisch fertig, Pi und Laptop sprechen per ROS 2 miteinander. **Rechenort:** Pi und Laptop.

1. **Mechanik:** Bestehenden Aufbau übernehmen: Encoder-Motoren einbauen, L298N durch das VNH5019-Shield auf dem Arduino ersetzen, den LiPo-Anschluss mit Sicherung vor dem Motorschalter verkabeln (siehe *Stromversorgung und LiPo-Umgang*), beide Powerbanks, LiPo und Pi im Flirc-Gehäuse fest montieren. LiDAR und Kamera sind bereits montiert.
2. **Maße übernehmen:** Aus deinen alten Notizen: Grundfläche 225 × 225 mm, base\_link mittig 0,1 m über dem Boden, LiDAR-Mitte relativ dazu x = +7,5 mm, y = −29 mm, z = +68 mm. Aus den CAD-Daten: Kamera mittig, etwa 10 mm vor dem Frontblech und 17 mm unter dessen Oberkante; Sensorplatte 90 × 134 × 4 mm. Noch nachmessen: Spurweite (Abstand der Kettenmitten) und Lage der IMU.
3. **Pi:** Ubuntu Server 24.04 (64 Bit) mit dem Raspberry Pi Imager flashen, SSH und WLAN gleich im Imager einrichten, Hostname z. B. `tank`. Bei 4 GB RAM 2 GB Swap anlegen.
4. **ROS 2 Jazzy:** auf dem Pi `ros-jazzy-ros-base`, in WSL2 auf dem Laptop `ros-jazzy-desktop`. Dazu `python3-colcon-common-extensions` und `python3-rosdep`.
5. **Netzwerk:** Feste IP für den Pi im Router, gleiche `ROS_DOMAIN_ID` (z. B. 42) in der `~/.bashrc` beider Rechner. Am besten 5-GHz-WLAN.
6. **Entwicklung:** Git-Repo `robot_ws` anlegen, VS Code mit Remote-SSH auf den Pi. Unter Windows Foxglove installieren, auf dem Pi ros-jazzy-foxglove-bridge.

**Fertig wenn:** `ros2 run demo_nodes_cpp talker` auf dem Pi läuft und `ros2 run demo_nodes_py listener` auf dem Laptop die Nachrichten empfängt.

## Phase 1: Motorsteuerung und Teleop

**Ziel:** Der Roboter fährt per Xbox-Controller und meldet seine Odometrie. **Rechenort:** Arduino (Regelung), Pi (ros2\_control), Laptop (Überwachung).

1. **Firmware:** Ausgangspunkt ist [ros\_arduino\_bridge](https://github.com/joshnewans/ros_arduino_bridge) im Modus `POLOLU_VNH5019`; dafür die Arduino-Bibliothek `DualVNH5019MotorShield` von Pololu installieren. Das serielle Protokoll bleibt gleich (`e` liest Encoder, `m <links> <rechts>` setzt Sollgeschwindigkeiten), die PID-Regelung läuft auf dem Arduino. Anpassen: linker Encoder auf D3/D5, Auto-Stop auf 0,5 s, PWM-Obergrenze aus der gemessenen Akkuspannung (6 V geteilt durch die Akkuspannung, bei vollem LiPo 71 %), Unterspannungsschutz (Warnung bei 7,0 V, Motoren aus bei 6,6 V), Abschaltung bei blockierter Kette.
2. **Test ohne ROS:** Roboter aufbocken, Motorschalter an, mit dem seriellen Monitor jede Kette einzeln drehen. Prüfen, dass „vorwärts“ bei beiden Ketten wirklich vorwärts ist und beide Encoder dabei hochzählen.
3. **Kalibrieren:** Radius des Antriebsrads 21,5 mm (43 mm Durchmesser). Erwartet sind 979,62 Encoder-Zählschritte pro Kettenradumdrehung (48 je Motorumdrehung × 20,41). Nachmessen: Kettenrad mit einer Markierung 10 Umdrehungen langsam fahren lassen und den Zählerstand durch 10 teilen. Den gerundeten Wert (980) trägt das Hardwareinterface als `enc_counts_per_rev` ein.
4. **Hardwareinterface (C++):** [diffdrive\_arduino](https://github.com/joshnewans/diffdrive_arduino) als `tank_hardware` übernehmen und an Jazzy anpassen. Es übersetzt Radgeschwindigkeiten aus ros2\_control in das serielle Protokoll. Jazzy-taugliche Forks gibt es bereits auf GitHub.
5. **Controller:** `diff_drive_controller` und `joint_state_broadcaster` per Launch-Datei in `tank_bringup` starten. Den Kettenantrieb wie zwei Räder behandeln.
6. **Ketten-Kalibrierung:** Roboter 10-mal auf der Stelle drehen lassen. Die Abweichung über `wheel_separation_multiplier` korrigieren, Ketten haben effektiv eine größere Spurbreite als gemessen.
7. **Befehlsweiche:** `twist_mux` einrichten mit Priorität Not-Halt > Teleop > Folgen > Nav2. So kann eine manuelle Eingabe jede Automatik übersteuern.
8. **Teleop mit dem Xbox-Controller:** `joy` und `teleop_twist_joy` laufen auf dem Pi, der Controller funktioniert also auch ohne WLAN. `require_enable_button: true` setzen: Der Roboter fährt nur, solange LB gedrückt ist. Tastatur-Teleop vom Laptop bleibt als Reserve.
9. **Autostart und Status-LED:** systemd-Dienst und Knoten `status_led` einrichten, wie unter *Einschaltreihenfolge und Status-LED* beschrieben.

**PID abstimmen:** Die Firmware regelt mit 30 Hz und erwartet beim `m`-Befehl Zählschritte pro Regeltakt; `m 24 24` entspricht etwa 0,1 m/s. Sollwert vorgeben, Ist-Werte aus `e` mitschreiben, erst Kp erhöhen, bis die Kette zügig folgt, ohne zu schwingen, dann Ki gegen die bleibende Abweichung.

**Stolperfalle Jazzy:** Der [diff\_drive\_controller erwartet TwistStamped](https://docs.ros.org/en/jazzy/p/diff_drive_controller/doc/userdoc.html). Teleop mit `stamped:=true` starten und in Nav2 später `enable_stamped_cmd_vel: true` setzen, weil das in Jazzy noch [standardmäßig aus ist](https://docs.nav2.org/configuration/packages/configuring-velocity-smoother.html).

**Fertig wenn:** Der Roboter per Xbox-Controller geradeaus fährt und auf der Stelle dreht, bei abgezogenem USB-Kabel innerhalb von 0,5 s stoppt und nach 2 m Geradeausfahrt in `/odom` weniger als 5 % Abweichung zeigt. Nach dem Einschalten der Powerbanks leuchtet die Startup-LED ohne weiteres Zutun dauerhaft.

## Phase 2: Robotermodell, Odometrie und IMU

**Ziel:** ROS kennt die Geometrie des Roboters und schätzt seine Position auch in Kurven stabil. **Rechenort:** Pi; RViz und optional Simulation auf dem Laptop.

1. **URDF/Xacro in `tank_description`:** Frames `base_footprint` (Boden unter dem Drehpunkt), `base_link`, zwei virtuelle Antriebsräder, `laser_frame`, `camera_link`, `imu_link`. Rumpf als Quader mit den echten Außenmaßen; Deckblech und Sensorplatte als STL-Mesh (Einheit mm, im URDF scale 0,001). Den Gierwinkel des LiDAR einmal prüfen: Gegenstand vor den Bug stellen, im Scan muss er vorne erscheinen.
2. **ros2\_control-Tags** ins URDF eintragen, damit Controller und Hardwareinterface aus derselben Beschreibung starten. `robot_state_publisher` veröffentlicht daraus den TF-Baum.
3. **Prüfen in RViz:** TF-Baum `odom → base_footprint → base_link → laser_frame` muss lückenlos sein, das Modell muss sich beim Fahren mitbewegen.
4. **IMU einbinden:** Eigenen Python-Knoten für den ICM-20948 schreiben (SparkFun-Python-Bibliothek, Gyro und Beschleunigung als Imu-Message), dahinter imu\_filter\_madgwick ohne Magnetometer, dann, `/imu/data` prüfen. Beim Drehen um 90° muss die Gierrate sauber ansteigen und abfallen.
5. **Sensorfusion:** `robot_localization` (EKF) fusioniert Vorwärtsgeschwindigkeit aus der Rad-Odometrie mit der Gierrate der IMU. Im diff\_drive\_controller `enable_odom_tf: false` setzen, den TF `odom → base_footprint` liefert dann der EKF.
6. **Optional parallel:** Dasselbe URDF in Gazebo auf dem Laptop simulieren (`gz_ros2_control`). Damit kannst du Nav2 später gefahrlos vorab einstellen.

**Gegenprobe:** `rf2o_laser_odometry` schätzt die Bewegung allein aus den LiDAR-Scans. Läuft es testweise mit, zeigt der Vergleich mit `/odometry/filtered` schnell, ob Encoder-Vorzeichen oder Spurbreite falsch eingestellt sind.

**Fertig wenn:** Nach einer Fahrt von 2 m hin und zurück mit zwei 180°-Drehungen der Roboter in `/odometry/filtered` weniger als 10 cm und 5° vom Startpunkt entfernt ist.

## Phase 3: LiDAR und SLAM

**Ziel:** Der Roboter erstellt per Teleop eine saubere Karte deiner Wohnung und speichert sie. **Rechenort:** Pi (Treiber, SLAM), Laptop (RViz, Teleop).

1. **Treiber:** [sllidar\_ros2](https://github.com/Slamtec/sllidar_ros2) von Slamtec bauen, erst `view_sllidar_a1_launch.py` testen, dann `sllidar_a1_launch.py` mit `frame_id:=laser_frame` in den eigenen Bringup übernehmen. Der A1 läuft mit 115200 Baud.
2. **Feste Gerätenamen:** udev-Regeln für `/dev/rplidar` und `/dev/arduino` anlegen (das Repo liefert eine Vorlage). Sonst tauschen LiDAR und Arduino beim Neustart ihre `ttyUSB`-Nummern.
3. **Scan prüfen:** In RViz muss der Scan beim Drehen des Roboters fest an den Wänden stehen bleiben. Verschiebt er sich, stimmen Montagewinkel im URDF oder Odometrie nicht.
4. **Eigene Teile ausblenden:** Sieht der LiDAR Teile des Rumpfs, diese Winkel mit `laser_filters` entfernen.
5. **Kartieren:** `slam_toolbox` im Modus `online_async` starten. Wichtige Parameter: `base_frame: base_footprint`, `resolution: 0.05`, `max_laser_range: 12.0` (Reichweite des A1).
6. **Fahrweise:** Langsam fahren (unter 0,2 m/s, Drehungen unter 0,5 rad/s), Räume als Schleifen abfahren, damit der Algorithmus Schleifen schließen kann.
7. **Speichern:** Karte über das SLAM-Toolbox-Panel in RViz serialisieren und zusätzlich mit `map_saver_cli` als PGM/YAML in `tank_navigation/maps` sichern.

**Der A1 hat Grenzen:** Er scannt mit [5,5 Hz in einer einzigen Ebene](https://www.waveshare.com/wiki/RPLIDAR_A1) und sieht nichts darunter oder darüber. Tischplatten, Stuhlbeine und Glas erkennt er schlecht.

**Fertig wenn:** Die Karte deiner Wohnung zeigt gerade Wände ohne doppelte Konturen, und die CPU-Last des Pi bleibt unter 70 %.

## Phase 4: Autonome Navigation mit Nav2

**Ziel:** Du klickst in RViz ein Ziel, der Roboter plant selbst einen Weg und weicht neuen Hindernissen aus. **Rechenort:** Pi (gesamtes Nav2), Laptop (Ziele setzen, Überwachung).

1. **Lokalisierung:** Mit gespeicherter Karte `map_server` + AMCL nutzen. Für unbekannte Bereiche SLAM Toolbox und Nav2 gleichzeitig laufen lassen.
2. **Footprint:** Den Panzer als Rechteck-Polygon eintragen, nicht als Kreis. Etwas Rand zugeben, damit Kettenschlupf nicht zu Kollisionen führt.
3. **Controller:** Mit *Regulated Pure Pursuit* plus *Rotation Shim* beginnen. Beide sind leicht genug für den Pi 4; der Rotation Shim dreht den Panzer erst auf der Stelle in Fahrtrichtung, was Ketten gut können. MPPI ist präziser, aber auf dem Pi 4 rechenintensiv.
4. **Planer:** NavFn oder Smac Planner 2D für den globalen Weg.
5. **Costmaps:** Lokal ein mitwanderndes Fenster von 3 × 3 m mit Hindernissen aus `/scan`, global die statische Karte plus Hindernisse. Inflation auf etwa die halbe Rumpfbreite plus 10 cm.
6. **Sicherheitsnetz:** `velocity_smoother` für sanftes Anfahren und `collision_monitor` mit einer Stoppzone direkt vor dem Bug. Der Collision Monitor stoppt auch dann, wenn der Planer sich irrt.
7. **Raten an den Pi anpassen:** Controller 10–15 Hz, lokale Costmap 5 Hz, Höchstgeschwindigkeit 0,3 m/s in Innenräumen.
8. **Ziele aus Python:** Ein erstes Skript mit `nav2_simple_commander` schreiben, das drei Wegpunkte nacheinander anfährt. Daraus entsteht später `tank_missions`.

**Fertig wenn:** Der Roboter 10 Ziele in Folge in verschiedenen Räumen erreicht, einer Person ausweicht, die sich in den Weg stellt, und bei verstelltem Weg eine Alternative findet oder sauber abbricht.

## Phase 5: Kamera und Coral – Personenerkennung

**Ziel:** Der Roboter erkennt Personen im Bild und kennt ihre Position im Raum. **Rechenort:** Pi + Coral (Inferenz), Laptop (Modell kompilieren, Debug-Bild ansehen). Diese Phase kann parallel zu Phase 3–4 laufen.

1. **Kamera:** `camera_ros` installieren. Die apt-Version nutzt das Standard-libcamera, das nicht alle Pi-Kameramodule unterstützt. Klappt es nicht, den [Raspberry-Pi-Fork von libcamera im Workspace mitbauen](https://docs.ros.org/en/jazzy/p/camera_ros). Auflösung 640 × 480, 15 Bilder/s. Vorher prüfen, ob sich das Kamera-Flachbandkabel aus dem Flirc-Gehäuse führen lässt.
2. **Kamera kalibrieren:** Mit `camera_calibration` und einem Schachbrettmuster. Nötig, um Bildpositionen in Winkel umzurechnen.
3. **Coral einrichten:** `libedgetpu`-Runtime und ein PyCoral-Wheel für Python 3.12 / aarch64 aus den [Community-Builds](https://github.com/feranick/pycoral) installieren. Mit dem Beispiel `detect_image.py` testen.
4. **Modell:** Mit SSD MobileNet v2 (COCO, fertig für Edge TPU) starten, nur Klasse *person* auswerten. Später optional ein kleines YOLO-Modell mit Edge-TPU-Export. Der Edge-TPU-Compiler läuft nur auf x86-Linux, also auf dem Laptop.
5. **Knoten `person_detector` (Python):** Bild abonnieren, Inferenz, Ergebnis als `vision_msgs/Detection2DArray` plus Debug-Bild veröffentlichen.
6. **Entfernung über LiDAR:** Aus der Bildposition der Person den Winkel berechnen, im LiDAR-Scan in diesem Winkel den nächsten Punkt-Cluster suchen. Ergebnis: `/person_pose` als `PoseStamped` im Frame `base_link`.
7. **Tracking:** Personen über die Zeit einer ID zuordnen (Nächster-Nachbar-Abgleich oder SORT). Wichtig, damit der Roboter in Phase 6 nicht zu einer anderen Person wechselt.

**Fallback:** Macht die Pi-Kamera unter Ubuntu zu viel Ärger, eine USB-Webcam mit `v4l2_camera` nutzen. Läuft der Coral nicht stabil, die Erkennung vorübergehend auf dem Laptop rechnen.

**Fertig wenn:** Personen mit mindestens 10 Bildern/s erkannt werden und die per LiDAR bestimmte Entfernung auf 20 cm genau stimmt.

## Phase 6: Person Following

**Ziel:** Auf Befehl folgt der Roboter dir in 1–1,5 m Abstand durch die Wohnung und umfährt dabei Hindernisse. **Rechenort:** Pi.

1. **Aktion definieren:** `FollowPerson.action` in `tank_interfaces` mit Ziel (Abstand), Feedback (aktueller Abstand, Person sichtbar ja/nein) und Ergebnis. So kann später der KI-Assistent das Folgen starten und stoppen.
2. **Zielperson festlegen:** Beim Start wird die Person gewählt, die am nächsten direkt vor dem Roboter steht. Ihre Tracking-ID wird gemerkt.
3. **Variante A – direkter Regler (zum Einstieg):** P-Regler auf Winkel und Abstand, Ausgabe auf `cmd_vel` über `twist_mux` mit Priorität *Folgen*. Einfach und reaktionsschnell, aber ohne Wegplanung. Der Collision Monitor bleibt aktiv.
4. **Variante B – über Nav2 (Ziel):** Die Personenposition laufend als Ziel an Nav2 geben. Nav2 bringt dafür den Verhaltensbaum [Follow Dynamic Point](https://docs.nav2.org/jazzy/getting_started/nav2_behavior_trees/trees/follow_point/) mit: Er plant jede Sekunde neu und kürzt den Weg vor der Person, damit der Roboter Abstand hält. So umfährt der Roboter Möbel auf dem Weg zu dir.
5. **Person verloren:** Anhalten, sich langsam zur letzten bekannten Richtung drehen, nach 10 s aufgeben und das als Ergebnis melden. Ab Phase 7 sagt der Roboter dann "Ich sehe dich nicht mehr".

**Fertig wenn:** Der Roboter dir durch zwei Räume und eine Tür folgt, bei 1 m anhält, wenn du stehen bleibst, und stoppt, statt einer fremden Person zu folgen.

## Phase 7: KI-Assistent

**Ziel:** Du sprichst den Roboter mit einem Wake-Word an, er beantwortet Fragen und löst Roboter-Funktionen per Sprache aus. **Rechenort:** Pi (Wake-Word, Sprachausgabe, Werkzeug-Brücke), Cloud (Spracherkennung, Sprachmodell). Diese Phase kann schon nach Phase 0 als reiner Sprachassistent beginnen.

**Ablauf einer Anfrage:**

1. **Wake-Word** lokal auf dem Pi mit openWakeWord, z. B. ein eigenes Wort wie "Hey Panzer". Erst danach wird Audio aufgenommen.
2. **Aufnahme bis Sprechpause** mit einer Sprachaktivitätserkennung (VAD).
3. **Spracherkennung (STT):** Cloud-Dienst mit Whisper-Modell, alternativ `faster-whisper` auf dem Laptop.
4. **Sprachmodell mit Werkzeugen:** Der Text geht an ein LLM mit Tool-Use, z. B. Claude über die API. Ein schnelles Modell für Gespräche, ein stärkeres für mehrstufige Aufgaben. Lokale Alternative: Ollama auf dem Laptop, mit spürbar schwächerem Tool-Use.
5. **Werkzeug-Brücke (`assistant_bridge`, Python, Pi):** Übersetzt jeden Werkzeugaufruf in eine ROS-Action oder einen Service und meldet das Ergebnis zurück ans LLM.
6. **Sprachausgabe:** Piper mit deutscher Stimme lokal auf dem Pi.

**Werkzeuge, die das LLM bekommt:**

| Werkzeug | Wirkung | ROS-Schnittstelle |
| --- | --- | --- |
| `fahre_zu(ort)` | Fährt zu einem benannten Ort | Nav2 `NavigateToPose` |
| `folge_mir(start/stopp)` | Startet oder beendet das Folgen | `FollowPerson` (Phase 6) |
| `stopp()` | Bricht jede Bewegung ab | Abbruch aller Actions + Null-Geschwindigkeit |
| `ort_merken(name)` | Speichert die aktuelle Position unter einem Namen | Service in `tank_missions` |
| `status()` | Akkustand, Position, aktuelle Aufgabe | Topics `/battery_state`, `/amcl_pose` |
| `was_siehst_du()` | Schickt ein Kamerabild an ein Vision-Modell | Einzelbild aus `/camera/image_raw` |

**Sicherheitsregeln für die KI:**

- Das LLM bekommt nur diese Werkzeuge, nie direkten Zugriff auf `cmd_vel` oder beliebige Topics.
- Die Brücke prüft jeden Aufruf: Ort existiert, Akku reicht, Geschwindigkeit begrenzt.
- "Stopp" wird lokal als zweites Wake-Word erkannt und wirkt sofort, ohne Cloud.
- Audio verlässt den Roboter nur nach dem Wake-Word, Bilder nur bei `was_siehst_du()`. Der API-Schlüssel liegt in einer Umgebungsdatei, nicht im Git-Repo.

Zum schnellen Ausprobieren gibt es den [ROS MCP Server](https://github.com/robotmcp/ros-mcp-server), der einem LLM über rosbridge vollen Zugriff auf alle Topics gibt. Für Experimente am Laptop ist das praktisch, für den Alltagsbetrieb ist die eigene, eingeschränkte Werkzeug-Brücke sicherer.

**Fertig wenn:** Der Roboter auf "Hey Panzer, wie viel Akku hast du?" innerhalb von etwa 3 s antwortet und "Fahr in die Küche" korrekt ausführt.

## Phase 8: Kleine Aufgaben selbstständig erledigen

**Ziel:** Der Roboter führt mehrstufige Aufträge aus, die du in natürlicher Sprache gibst. **Rechenort:** Pi (Ausführung), Cloud (Zerlegung des Auftrags durch das LLM).

**Prinzip:** Das LLM zerlegt einen Auftrag in eine Folge der Werkzeuge aus Phase 7. Ein Missions-Knoten in `tank_missions` führt die Schritte aus, überwacht Fehler und meldet den Fortschritt. So bleibt die Ausführung deterministisch, auch wenn die Cloud kurz weg ist.

| Beispielauftrag | Ablauf | Braucht |
| --- | --- | --- |
| "Schau, ob in der Küche das Fenster offen ist" | `fahre_zu(Küche)` → `was_siehst_du()` → zurück → Antwort | Phasen 4, 5, 7 |
| "Sag Anna im Wohnzimmer, dass das Essen fertig ist" | `fahre_zu(Wohnzimmer)` → Person suchen → Satz sprechen → zurück | Phasen 4, 5, 7 |
| "Mach eine Runde durch alle Räume" | Alle gespeicherten Orte als Wegpunkte, an jedem kurz umsehen | Phasen 4, 8 |
| "Bring das ins Arbeitszimmer" | Du legst etwas auf eine Ablage, Roboter fährt hin und meldet sich | Phasen 4, 7 + Ablage am Rumpf |
| "Komm zu mir" | Zur letzten bekannten Position von dir fahren, dann suchen | Phasen 4, 5, 6 |
| "Fahr zum Laden" | Ladestation anfahren und andocken | Phasen 4 + Ladestation |

**Umsetzung in Schritten:**

1. **Orte verwalten:** Benannte Posen in einer YAML-Datei, gepflegt über `ort_merken(name)`.
2. **Missionsausführung:** Mit Python und `nav2_simple_commander` beginnen. Werden die Abläufe verzweigter, auf Verhaltensbäume mit `py_trees` umsteigen.
3. **Rückmeldungen:** Jeder Schritt meldet Erfolg oder Fehler, das LLM formuliert daraus eine verständliche Antwort.
4. **Autonom laden (optional):** Nav2 bringt seit Jazzy einen [Docking-Server](https://docs.nav2.org/migration/Iron.html) mit. Eine Ladestation mit AprilTag-Markierung lässt sich damit anfahren.

**Fertig wenn:** Drei der Beispielaufträge per Sprache zuverlässig klappen und der Roboter bei Fehlern sagt, was schiefging, statt stumm stehen zu bleiben.

## Risiken und Sicherheit

Die größten Risiken sind Kettenschlupf, die Rechenleistung des Pi 4 und Treiberprobleme bei Kamera und Coral. Für jedes gibt es einen Ausweg, der den Plan nicht umwirft.

| Risiko | Auswirkung | Gegenmaßnahme |
| --- | --- | --- |
| Kettenschlupf beim Drehen | Odometrie driftet, Karte verzerrt | IMU-Fusion, `wheel_separation_multiplier` kalibrieren, langsam drehen |
| CPU-Last auf dem Pi 4 | Nav2 reagiert träge, Pi drosselt | Raten senken, RPP statt MPPI, Kamera auf 640 × 480, SLAM notfalls auf den Laptop |
| Powerbank bricht unter Last ein | Pi startet neu, LiDAR oder Coral fallen aus | Zwei Powerbanks: Hama nur für den Pi, Nitecore für den USB-Hub; mit vcgencmd get\_throttled prüfen |
| Coral unter Python 3.12 | Erkennung startet nicht | Community-Builds; Fallback Docker-Container mit Python 3.9 oder Inferenz auf dem Laptop |
| Pi-Kamera unter Ubuntu | Kein Bild | libcamera-Fork mitbauen; Fallback USB-Webcam |
| WLAN-Aussetzer | Laptop-Ansicht friert ein, Sprachassistent stumm | Alles Sicherheitsrelevante läuft auf dem Pi; bei Discovery-Problemen Cyclone DDS oder rmw\_zenoh |
| 2D-LiDAR sieht nicht alles | Kollision mit Tischplatten, niedrigen Kanten, Glas | Footprint großzügig; später ToF- oder Ultraschallsensoren vorne ergänzen |
| LLM missversteht einen Befehl | Falsche Fahrt | Nur Whitelist-Werkzeuge, Prüfung in der Brücke, lokales "Stopp" |

**Sicherheitsgrundsätze, die ab Phase 0 gelten:**

- Der Motorschalter trennt den Motorstrom physisch, unabhängig von jeder Software. Er wird erst eingeschaltet, wenn die Startup-LED dauerhaft leuchtet.
- Watchdog im Arduino stoppt die Motoren nach 0,5 s ohne Befehl.
- Höchstgeschwindigkeit in Innenräumen 0,3 m/s, Collision Monitor immer aktiv.
- Den LiPo nur mit dem Balance-Lader laden, im LiPo-Sack und nie unbeaufsichtigt; nie unter 6,6 V entladen.

## Fahrplan und nächste Schritte

Der kritische Pfad läuft über Fahren, Kartieren und Navigieren (Phasen 0–4). Kamera/Coral und Sprachassistent können parallel dazu entstehen und treffen sich in den Phasen 6 und 8.

&#91;embedded content: Fahrplan · 9 Phasen in 3 Strängen\]

Kamera/Coral und Sprachassistent brauchen nur das Grundsetup aus Phase 0; ihre Fahr-Funktionen schalten sich erst mit Nav2 frei.

**Diese Woche:**

- [x] Hardware geklärt: Pi mit 4 GB, Devastator, Encoder-Motoren, VNH5019-Shield, Stromversorgung mit zwei Powerbanks und 2S-LiPo
- [ ] Platz für den LiPo ausmessen (ca. 92 × 31 × 17 mm) und eine Position abseits der Ketten festlegen
- [ ] Bestellen laut *Einkaufsliste Motorkreis*, dazu aktiver USB-Hub und 2 × 10-kΩ-Widerstand
- [ ] Encoder-Motoren probehalber einbauen: Passen 4-mm-D-Welle und Halterung an Antriebsrad und Chassis? Sonst einen Adapter für die zwei M3-Gewinde drucken.
- [ ] Ubuntu Server 24.04 auf den Pi, ROS 2 Jazzy auf Pi und Laptop installieren
- [ ] Hama-Powerbank am Pi unter Last testen: `vcgencmd get_throttled` muss `0x0` melden
- [ ] Git-Repo `robot_ws` anlegen und VS Code Remote-SSH einrichten
- [ ] Talker/Listener-Test zwischen Pi und Laptop

**Meilensteine:**

- [ ] M0: Pi und Laptop tauschen ROS-Nachrichten aus
- [ ] M1: Fahren per Xbox-Controller, Startup-LED zeigt Bereitschaft, Watchdog stoppt bei Verbindungsabbruch
- [ ] M2: TF-Baum vollständig, gefilterte Odometrie stabil
- [ ] M3: Karte der Wohnung gespeichert
- [ ] M4: 10 Navigationsziele in Folge erreicht
- [ ] M5: Personen mit Entfernung erkannt
- [ ] M6: Roboter folgt dir durch zwei Räume
- [ ] M7: Sprachbefehl "Fahr in die Küche" funktioniert
- [ ] M8: Drei mehrstufige Aufträge per Sprache erledigt
