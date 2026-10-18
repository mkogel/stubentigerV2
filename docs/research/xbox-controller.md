# Xbox 360 wireless controller → ROS 2 on WSL2 and on the Pi

Research for issue #3. As of 2026-10-18. Sources are listed at the end; `[n]` marks a citation.

## Question

How does the **Xbox 360 wireless controller (USB receiver, `045e:0719`)** get to `sensor_msgs/Joy` in ROS 2 in two setups?

- **Virtual MVP:** Windows 11 laptop, WSL 2.6.1 with kernel 6.6.87.2, WSLg 1.0.66, Docker Desktop 28.4.
- **Physical MVP:** Raspberry Pi 4, Ubuntu Server, ROS 2 Jazzy or Lyrical.

Which path keeps the Teleop stack identical in both?

## Short answer

The stock WSL kernel has **no `xpad` driver**. Microsoft's x86 config sets `# CONFIG_INPUT_JOYSTICK is not set` in the 6.6.87.2 kernel you run now and in the 6.18.54.1 kernel that ships with WSL 3.0.3 [1][2][3]. The receiver is a vendor-specific USB device, not HID, and only `xpad` binds it [9]. So `usbipd-win` alone gets the receiver into WSL, but no `/dev/input` device ever appears.

**Recommendation:** use the same Linux driver path on both machines, so the ROS nodes and parameter files can be identical:

```
receiver → xpad (kernel) → /dev/input/eventN → joy game_controller_node → teleop_twist_joy → twist_mux → controller
```

- **Pi:** this works with the stock Ubuntu raspi kernel. `xpad.ko` and `joydev.ko` ship in the default `linux-modules-*-raspi` package for 24.04 (Jazzy) and for 26.04 (Lyrical) [17].
- **WSL2:** attach the receiver with `usbipd-win` and boot a **custom WSL kernel built from Microsoft's own config with `CONFIG_INPUT_JOYSTICK=y` and `CONFIG_JOYSTICK_XPAD=m` added** [5][6][7]. This is the only change you have to maintain.
- **Node:** use `joy`'s **`game_controller_node`** (SDL GameController API). Its button and axis indices are fixed by SDL's mapping table, not by the driver [12]. `joy_linux` and `joy_node` report raw driver order instead.

**Fallback:** the Foxglove "Joystick" extension (browser Gamepad API → `sensor_msgs/Joy` through `foxglove_bridge`) needs no kernel work. It does need its own index mapping, it stops publishing whenever the Foxglove window is in the background, and it has not been updated since 2024 [23][24]. Use it as a quick start or emergency path, not as the main sim Teleop.

## Verified facts

| # | Fact | Source |
|---|---|---|
| F1 | WSL kernel 6.6.87.2 (x86): `CONFIG_INPUT_EVDEV=m`, `CONFIG_INPUT_UINPUT=m`, `CONFIG_HID=m`, `CONFIG_USB=m`, `CONFIG_USBIP_VHCI_HCD=m`, **`# CONFIG_INPUT_JOYDEV is not set`**, **`# CONFIG_INPUT_JOYSTICK is not set`** (so no `xpad`), `# CONFIG_MODULE_SIG is not set`. | [1] |
| F2 | WSL kernel 6.18.54.1 (shipped with WSL 3.0.3, released 2026-10-09) adds `CONFIG_INPUT_JOYDEV=m`. It still has `# CONFIG_INPUT_JOYSTICK is not set`. | [2][3] |
| F3 | The kernel update that added JOYDEV (6.18.20.3, PR #40161) closed the long-running WSL issue "Gamepad support in WSL2 (/dev/jsx)" (#7747). That fix gives `/dev/input/js*` for HID gamepads only. `xpad` was not enabled. | [4] |
| F4 | `xpad` lists `045e:0719` "Xbox 360 Wireless Receiver" as `XTYPE_XBOX360W`. It matches vendor-specific interfaces (`USB_CLASS_VENDOR_SPEC`, subclass 93, protocol 129 for wireless). It creates or destroys the input device when a pad connects or disconnects ("presence" packets). It reports every wireless pad with product ID `0x02a1`. | [9] |
| F5 | usbipd-win needs WSL kernel ≥ 5.10.60.1. `usbipd bind` needs admin rights; `usbipd attach --wsl` does not. While a device is attached to WSL, Windows cannot use it. The device detaches on unplug or WSL restart. `usbipd attach --auto-attach` re-attaches it automatically. | [5][8] |
| F6 | `.wslconfig` supports `kernel=` (custom kernel), `kernelModules=` (modules VHDX), and `loadKernelModules=` (modules loaded at VM start). Microsoft's kernel repo documents `make KCONFIG_CONFIG=Microsoft/config-wsl` plus `gen_modules_vhdx.sh`. | [6][7] |
| F7 | All WSL 2 distros share one VM, one kernel and one device tree. That includes the `docker-desktop` distro present on this laptop. A custom kernel therefore applies to Docker Desktop containers too. | [25] |
| F8 | `joy` (SDL) reads `/dev/input/event*` (evdev). `joy_linux` reads `/dev/input/js*` (joydev). | [12] |
| F9 | When the device disappears, `joy_node` and `game_controller_node` stop publishing. `joy_linux` closes the device and retries opening it every second. All three default to `autorepeat_rate` 20 Hz in code. The `joy_linux` README says the default is 0, but the code sets 20. | [14][15] |
| F10 | `twist_mux` replaces an input that has been silent longer than its `timeout` (0.5 s in the example config) with 0.0 speed. `diff_drive_controller` has `cmd_vel_timeout` (default 0.5 s). | [21] |
| F11 | Ubuntu raspi kernels ship `xpad.ko.zst` and `joydev.ko.zst` in the base `linux-modules` package: `6.8.0-1065-raspi` (noble-updates, the Jazzy platform) and `7.0.0-1009-raspi` (resolute, the Lyrical platform). | [17][16] |
| F12 | SDL2 has a HIDAPI driver for the 360 wireless receiver. On Linux it would need the libusb backend, which SDL limits by default to a whitelist containing only the GameCube adapter. Ubuntu's `libsdl2` build does not declare `libusb-1.0-0-dev` as a build dependency. So on Ubuntu, SDL depends on `xpad`. | [18][19] |
| F13 | SDL2 2.30's built-in Linux controller DB has a mapping for GUID `…5e040000a1020000…` ("Xbox 360 Wireless Receiver (XBOX)"), which is the ID `xpad` gives each wireless pad. So `game_controller_node` gets the standard layout. | [18][9] |
| F14 | Foxglove's built-in Teleop panel publishes only `Twist` from on-screen buttons. No gamepad support is documented. | [22] |
| F15 | Local state of this laptop (read-only check, 2026-10-18): WSL 2.6.1, kernel 6.6.87.2-1. Only the `docker-desktop` WSL distro is installed (no Ubuntu yet). `usbipd` is not installed. Windows has never enumerated a `045e:0719` receiver on this machine. | local `wsl --version`, `wsl -l -v`, `Get-PnpDevice` |

## Candidate paths

### A. usbipd-win with the stock WSL kernel: not feasible

- **Feasibility:** the receiver shows up in `lsusb`, but no driver binds it. The kernel has no `xpad` (F1, F2). `hid-generic` cannot help because the receiver is not HID-class (F4).
- **Identical Teleop?** No, because it does not work at all.

### B. usbipd-win with a custom WSL kernel that includes `xpad`: recommended

- **Feasibility:** high. Microsoft documents building the kernel and modules VHDX and booting them via `.wslconfig` [6][7]. The usbipd-win wiki says a custom kernel is exactly the route for devices "that need special drivers" [8]. `xpad`'s dependencies (`CONFIG_USB`, `CONFIG_INPUT_FF_MEMLESS`, `CONFIG_LEDS_CLASS`) are already modules in the stock config (F1).
  - Config delta for 6.6: `CONFIG_INPUT_JOYSTICK=y`, `CONFIG_JOYSTICK_XPAD=m`, `CONFIG_JOYSTICK_XPAD_FF=y`, `CONFIG_JOYSTICK_XPAD_LEDS=y`, and `CONFIG_INPUT_JOYDEV=m` if you also want `js0`/`joy_linux`.
  - For 6.18 the delta is the same minus JOYDEV, which is already enabled.
- **Effort:**
  - One-time: install an Ubuntu WSL distro, build the kernel and modules VHDX, then edit `.wslconfig`. Expect roughly an afternoon, mostly compile time. This is an estimate, not measured.
  - Ongoing: rebuild when you want to follow a Microsoft kernel update. Inference from [6]: with `kernel=` set, WSL keeps booting your kernel after `wsl --update`, so nothing breaks silently; you just stay on the old kernel. Note that WSL 3.0.x has moved to 6.18 [3].
- **Latency/robustness:**
  - The input path is the same kernel driver as on the Pi. The USB/IP hop adds some latency over virtual networking that no primary source quantifies, so measure it (see Risks).
  - Losing the pad or the receiver produces the same removal events as on the Pi (F4, F9). The node stops, and `twist_mux` zeroes the output after 0.5 s (F10).
  - Unplugging the receiver or restarting WSL detaches the device; `--auto-attach` covers that (F5).
- **Identical Teleop:** yes. Same driver, same `/dev/input` device, same node, same YAML.

### B'. Out-of-tree `xpad.ko` for the stock kernel: unverified variant

The stock kernel has `CONFIG_MODULE_SIG` unset but `CONFIG_MODVERSIONS=y` (F1). A matching `xpad.ko` (and `joydev.ko` on 6.6) built from the exact `linux-msft-wsl-<ver>` tag could probably be loaded with `insmod` into Microsoft's kernel without replacing it.

- It still requires a configured kernel tree with `Module.symvers` (practically the same build).
- It breaks on every kernel update because of the vermagic/CRC mismatch.
- Microsoft does not document it.

Only worth a prototype if replacing the kernel turns out to break Docker Desktop (see Risks).

### C. usbipd-win with the `xboxdrv` userspace driver: possible, not recommended

- **Feasibility:** medium. `xboxdrv` supports the 360 wireless receiver via libusb and creates a virtual pad through `uinput` [27]. `uinput` is a module in the stock WSL kernel (F1), so no kernel build is needed. It produces evdev only, so on 6.6 it works with `joy`/SDL but not with `joy_linux`.
- **Effort:** low setup (`xboxdrv` 0.8.8 is in Ubuntu universe [27]) plus udev rules for USB access.
- **Robustness:**
  - The last tagged release is from 2015-11-09 [27].
  - It is a different driver from the Pi's `xpad`, so the virtual device name, IDs and possibly the layout differ. Identical Teleop would then require running `xboxdrv` on the Pi too, replacing a stock kernel driver with an old userspace one.
- **Identical Teleop:** only if you also adopt `xboxdrv` on the robot.

### D. Foxglove Joystick extension (browser Gamepad API) via `foxglove_bridge`: fallback

- **Feasibility:** high, with no USB passthrough at all. The receiver stays on Windows, Foxglove desktop reads it through the Gamepad API, and the community extension `joshnewans/foxglove-joystick` publishes `sensor_msgs/Joy` to the bridge (`context.advertise(topic, "sensor_msgs/Joy")`) [23]. `foxglove_bridge` 3.6.1 is released for both Jazzy and Lyrical [16].
- **Caveat:** Windows' own driver for the 360 receiver is not verified on this laptop (F15), and I found no primary Microsoft source for it.
- **Effort:** low. Install the extension, enable client publishing, write a remap.
- **Latency/robustness:**
  - The extension polls on `requestAnimationFrame` (~display rate) and publishes on every poll [23]. Browsers pause `requestAnimationFrame` in background windows [24]. So when Gazebo or another window covers Foxglove, Joy stops and the sim robot halts after the 0.5 s `twist_mux` timeout. That is fail-safe but annoying.
  - It maps only `gamepad.axes` (sticks), sends buttons as 0/1 (triggers lose their analog value), and does "direct mapping" with no custom remap yet. The README lists remapping and deadzones as open items. Last commit 2024-07-04 [23].
  - The Gamepad "standard" layout [24] differs from SDL's `game_controller_node` order [12]. For example, LB is button 4 in the browser and 9 in `game_controller_node`.
- **Identical Teleop:** no. Downstream nodes are the same, but the Joy producer and the index map differ, so sim needs its own `teleop_twist_joy` YAML or an extra remap node. It is still useful on the Physical MVP as a laptop-side backup controller.

### E. Windows-side bridge (custom script, or native ROS 2 on Windows): not recommended

- **Custom script:** a Python/SDL or XInput script on Windows publishing Joy through rosbridge (`rosbridge_suite` 2.7.1 Jazzy / 4.2.1 Lyrical [16]) or a `foxglove_bridge` client.
  - Low latency on localhost, but it is extra product code that exists only in sim.
  - It could copy `game_controller_node`'s index table, but that is a re-implementation, not the same stack.
- **Native ROS 2 on Windows:** run `joy game_controller_node` itself on Windows. Jazzy is Tier 1 on Windows 10/amd64 [28]. This would be the real node with the real mapping (SDL GameController DB on Windows). The costs:
  - a second full ROS install;
  - DDS discovery between Windows and WSL (mirrored networking plus firewall, which the buildplan already flags as fragile);
  - unclear Lyrical Windows support [28].
- **Identical Teleop:** partially (native ROS) or no (custom script).

### F. Docker / devcontainer

Containers use the WSL kernel (F7), so path B is a prerequisite here too. Docker Desktop's own USB/IP feature also depends on the drivers the kernel has, and its docs promise only "built-in drivers for many common USB devices" [26].

To reach the pad from a container, pass the input devices and allow hotplug, because Docker only creates device nodes at container creation time [26]:

```
-v /dev/input:/dev/input --device-cgroup-rule='c 13:* rmw'
```

Input devices are char major 13 [11].

Path D needs nothing in the container except network access to the bridge.

### G. Raspberry Pi 4 (Ubuntu Server): works with the stock kernel

- **Driver:** `xpad` and `joydev` ship in the default modules package for 24.04 and 26.04 (F11). The receiver gets one input device per connected pad (F4).
- **Node:**
  - `joy` 3.3.0 (Jazzy 3.3.0-3, Lyrical 3.3.0-4 [16]) provides both `joy_node` and `game_controller_node` [12][14].
  - `joy_linux` is the lightweight, joydev-only alternative. Its README itself recommends `joy_node` "for all other use cases" [13].
  - The buildplan's "lief im alten Aufbau schon mit ROS 2" ("already worked with ROS 2 in the old setup") fits this.

## Which `joy` node

| Node | Reads | Index order | Disconnect behaviour | Verdict |
|---|---|---|---|---|
| `game_controller_node` | evdev via SDL GameController | Fixed table: A=0, B=1, X=2, Y=3, BACK=4, GUIDE=5, START=6, LS=7, RS=8, LB=9, RB=10, D-pad 11–14; axes LX=0, LY=1, RX=2, RY=3, LT=4, RT=5 [12] | Stops publishing on `SDL_CONTROLLERDEVICEREMOVED` [14] | **Use this.** The layout is independent of the driver. |
| `joy_node` | evdev via SDL Joystick | Raw driver order ("depends on the manufacturer") [12] | Stops publishing [14] | Acceptable if both sides use `xpad`. |
| `joy_linux_node` | `/dev/input/js*` (joydev) | Raw joydev order | Closes and retries every 1 s [15] | Needs JOYDEV in WSL (not in 6.6). No benefit here. |

Notes:

- `game_controller_node` scales every axis by −1/32767 [14]. Sticks follow the ROS convention (up and left are positive), and triggers run 0 → −1.
- Both Teleop buttons should be **buttons** (for example LB = dead-man, RB = Turbo) to avoid trigger-sign quirks. The final mapping belongs to issue #8.
- `teleop_twist_joy`'s shipped `xbox.config.yaml` (enable 2, turbo 5) targets the raw `joy_node` layout [20]. Do not reuse it with `game_controller_node`.

## Recommendation

1. **Robot:** `xpad` (stock) → `joy game_controller_node` → `teleop_twist_joy` (`require_enable_button: true`, `enable_turbo_button`, `publish_stamped_twist: true` for Jazzy's `diff_drive_controller`) [20] → `twist_mux`.
2. **Sim:** exactly the same launch file and YAML, running in WSL2. The receiver comes in through `usbipd-win` and a custom WSL kernel with `xpad` (path B).
3. **Safety chain, identical in both:**
   - A lost pad or receiver stops Joy (F9).
   - `teleop_twist_joy` publishes zero once when the dead-man button is released [20].
   - `twist_mux` 0.5 s timeout → zero, then `diff_drive_controller` `cmd_vel_timeout` 0.5 s (F10). This chain gives the buildplan's "stops within 0.5 s after unplugging".
   - Keep `autorepeat_rate` at 20 Hz, otherwise a steadily held stick looks like silence to `twist_mux`.
4. **Fallback** while the kernel isn't built yet: Foxglove Joystick extension (path D) with a sim-only remap, or keyboard teleop.

## Setup outline (recommended path)

**WSL2 laptop (one-time):**

1. `wsl --install -d Ubuntu-24.04` (or 26.04 for Lyrical). Install ROS and `ros-<distro>-joy`, `teleop-twist-joy`, `twist-mux`.
2. In Ubuntu, check out the kernel tag that matches `wsl --version`, for example `linux-msft-wsl-6.6.87.2` [7].
   - Install the build dependencies listed in the kernel README [7].
   - Add `CONFIG_INPUT_JOYSTICK=y`, `CONFIG_JOYSTICK_XPAD=m`, `CONFIG_JOYSTICK_XPAD_FF=y`, `CONFIG_JOYSTICK_XPAD_LEDS=y` (plus `CONFIG_INPUT_JOYDEV=m` on 6.6) to `Microsoft/config-wsl`, then run `make olddefconfig KCONFIG_CONFIG=Microsoft/config-wsl`.
   - Run `make -j$(nproc) KCONFIG_CONFIG=Microsoft/config-wsl && make INSTALL_MOD_PATH=$PWD/modules modules_install`.
   - Run `sudo ./Microsoft/scripts/gen_modules_vhdx.sh $PWD/modules $(make -s kernelrelease) modules.vhdx` [7].
3. Copy `arch/x86/boot/bzImage` and `modules.vhdx` to Windows. In `%UserProfile%\.wslconfig` under `[wsl2]`, set `kernel=`, `kernelModules=`, and `loadKernelModules=xpad` [6]. Then run `wsl --shutdown`.
4. Check that `uname -r` shows the custom build and that `docker run hello-world` still works (Risk R1).
5. Run `winget install usbipd` [8]. In an admin shell, run `usbipd bind --busid <id>` once (the binding persists across reboots [8]). Then run `usbipd attach --wsl --busid <id> --auto-attach` [5][8].
6. In WSL, run `lsusb` (expect `045e:0719`), then `ros2 run joy joy_enumerate_devices`, then `ros2 run joy game_controller_node` and `ros2 topic echo /joy`.
7. If not running as root, add a udev rule or use the `input` group for `/dev/input/event*` [5].

**Pi:**

1. `ros-<distro>-joy` and the rest of the stack.
2. Plug in the receiver.
3. Check `lsmod | grep xpad`, then run the same launch file.

**Containers:** add `-v /dev/input:/dev/input --device-cgroup-rule='c 13:* rmw'` (path F).

## Open risks / verify in a prototype

- **R1, custom kernel vs Docker Desktop:** a user in WSL #7747 reported that Docker Desktop stopped working with a community-built joystick kernel (2025-05-05) [4]. Building from Microsoft's own config for the *same* tag should avoid that, but verify it.
- **R2, USB/IP latency and jitter:** not quantified by any primary source. Measure the delay from `evtest` timestamp to `/joy` arrival in WSL against the Pi. The acceptance bar is the buildplan's 0.5 s stop.
- **R3, kernel drift:** WSL 3.0.x ships 6.18 [3]. Decide whether to pin the custom 6.6 build or move to 6.18 (which brings JOYDEV) when you upgrade WSL.
- **R4, WSL VM lifetime:** usbipd needs a running WSL VM, and the VM idles out [5][6]. Keep a WSL shell or the sim running. `--auto-attach` covers the restarts [8].
- **R5, `game_controller_node` mapping on the real receiver:** expected from SDL's DB entry (F13), but not yet observed. Confirm the indices with `ros2 topic echo /joy` once on the Pi and once in WSL.
- **R6, Windows driver for the receiver:** only matters for path D or E, and is unverified on this laptop (F15).
- **R7, Foxglove extension maintenance:** the extension is a single-author community project with its last commit in 2024 [23]. Don't build the main path on it.

## Sources

1. WSL kernel x86 config, tag `linux-msft-wsl-6.6.87.2`, `Microsoft/config-wsl`, lines 908, 3097–3189, 5373–5626: https://github.com/microsoft/WSL2-Linux-Kernel/blob/linux-msft-wsl-6.6.87.2/Microsoft/config-wsl
2. WSL kernel x86 config, tag `linux-msft-wsl-6.18.54.1`, lines 2893–2982: https://github.com/microsoft/WSL2-Linux-Kernel/blob/linux-msft-wsl-6.18.54.1/Microsoft/config-wsl
3. WSL release 3.0.3 ("Update Microsoft.WSL.Kernel to 6.18.54.1"): https://github.com/microsoft/WSL/releases/tag/3.0.3
4. WSL PR #40161 (6.18.20.3, adds `CONFIG_INPUT_JOYDEV`, closes #7747): https://github.com/microsoft/WSL/pull/40161 and issue https://github.com/microsoft/WSL/issues/7747
5. Microsoft Learn, "Connect USB devices" (updated 2026-06-02): https://learn.microsoft.com/en-us/windows/wsl/connect-usb
6. Microsoft Learn, "Advanced settings configuration in WSL" (`kernel`, `kernelModules`, `loadKernelModules`, `vmIdleTimeout`; updated 2026-10-16): https://learn.microsoft.com/en-us/windows/wsl/wsl-config
7. WSL2-Linux-Kernel README, build instructions: https://github.com/microsoft/WSL2-Linux-Kernel/blob/linux-msft-wsl-6.6.y/README.md
8. usbipd-win: README https://github.com/dorssel/usbipd-win, wiki "WSL support" https://github.com/dorssel/usbipd-win/wiki/WSL-support, `--auto-attach` option https://github.com/dorssel/usbipd-win/blob/master/Usbipd/Program.cs (latest release v5.3.0)
9. Linux `xpad.c` v6.6, lines 146, 152, 432–448, 899–960, 1889–1894: https://github.com/torvalds/linux/blob/v6.6/drivers/input/joystick/xpad.c
10. Linux docs, `xpad.rst`: https://github.com/torvalds/linux/blob/master/Documentation/input/devices/xpad.rst
11. Linux docs, `devices.txt` (char major 13 = input core): https://github.com/torvalds/linux/blob/master/Documentation/admin-guide/devices.txt
12. `joy` README (ros2 branch): https://github.com/ros-drivers/joystick_drivers/blob/ros2/joy/README.md
13. `joy_linux` README: https://github.com/ros-drivers/joystick_drivers/blob/ros2/joy_linux/README.md
14. `joy` 3.3.0 sources: `joy.cpp` L75, L405, L476 https://github.com/ros-drivers/joystick_drivers/blob/3.3.0/joy/src/joy.cpp ; `game_controller.cpp` L76, L157–180, L378, L411 https://github.com/ros-drivers/joystick_drivers/blob/3.3.0/joy/src/game_controller.cpp ; `CMakeLists.txt` (executables `joy_node`, `game_controller_node`) https://github.com/ros-drivers/joystick_drivers/blob/3.3.0/joy/CMakeLists.txt
15. `joy_linux_node.cpp` 3.3.0, L215, L331, L538: https://github.com/ros-drivers/joystick_drivers/blob/3.3.0/joy_linux/src/joy_linux_node.cpp
16. rosdistro `jazzy/distribution.yaml` and `lyrical/distribution.yaml` (`joystick_drivers`, `teleop_twist_joy`, `twist_mux`, `foxglove-sdk`, `rosbridge_suite`; Lyrical targets Ubuntu resolute): https://github.com/ros/rosdistro/blob/master/jazzy/distribution.yaml , https://github.com/ros/rosdistro/blob/master/lyrical/distribution.yaml
17. Ubuntu packages: `linux-modules-6.8.0-1065-raspi` file list (noble-updates/arm64) https://packages.ubuntu.com/noble-updates/arm64/linux-modules-6.8.0-1065-raspi/filelist ; resolute contents search for `xpad.ko.zst` and `joydev.ko.zst` (finds `linux-modules-7.0.0-1009-raspi`) https://packages.ubuntu.com/search?searchon=contents&keywords=xpad.ko.zst&mode=exactfilename&suite=resolute&arch=arm64
18. SDL 2.30: `src/hidapi/SDL_hidapi.c` L891–913 (libusb whitelist) https://github.com/libsdl-org/SDL/blob/release-2.30.x/src/hidapi/SDL_hidapi.c ; `src/joystick/hidapi/SDL_hidapi_xbox360w.c` L62–77 https://github.com/libsdl-org/SDL/blob/release-2.30.x/src/joystick/hidapi/SDL_hidapi_xbox360w.c ; `src/joystick/SDL_gamecontrollerdb.h` L529–876 (Linux section), L861 https://github.com/libsdl-org/SDL/blob/release-2.30.x/src/joystick/SDL_gamecontrollerdb.h
19. Ubuntu `libsdl2` source package, noble (build dependencies): https://packages.ubuntu.com/source/noble/libsdl2
20. `teleop_twist_joy` README and `config/xbox.config.yaml` (rolling; Jazzy 2.6.5): https://github.com/ros2/teleop_twist_joy
21. `twist_mux` `config/twist_mux_topics.yaml` https://github.com/ros-teleop/twist_mux/blob/rolling/config/twist_mux_topics.yaml ; `diff_drive_controller` parameters (jazzy) `cmd_vel_timeout` https://github.com/ros-controls/ros2_controllers/blob/jazzy/diff_drive_controller/src/diff_drive_controller_parameter.yaml
22. Foxglove docs, Teleop panel: https://docs.foxglove.dev/docs/visualization/panels/teleop
23. `joshnewans/foxglove-joystick`: README, `src/JoyPanel.tsx`, `src/hooks/useGamepad.ts`: https://github.com/joshnewans/foxglove-joystick ; announcement https://discourse.openrobotics.org/t/new-foxglove-extension-joystick-panel/35600
24. MDN, "Using the Gamepad API" https://developer.mozilla.org/en-US/docs/Web/API/Gamepad_API/Using_the_Gamepad_API and `requestAnimationFrame` https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame
25. Microsoft Learn, "What is WSL" (WSL 2 distros share kernel and device tree): https://learn.microsoft.com/en-us/windows/wsl/about
26. Docker docs, `docker run --device-cgroup-rule` https://docs.docker.com/reference/cli/docker/container/run/ ; Docker Desktop USB/IP https://docs.docker.com/desktop/features/usbip/
27. `xboxdrv` README and tags (v0.8.8, 2015-11-09) https://github.com/xboxdrv/xboxdrv ; Ubuntu package https://packages.ubuntu.com/noble/xboxdrv
28. REP 2000 (Jazzy: Windows 10 amd64 Tier 1, Ubuntu 24.04 arm64 Tier 1; Lyrical platforms moved to the release docs): https://reps.openrobotics.org/rep-2000/
