# Dev environment: WSL2 Ubuntu or devcontainer?

Research for issue #5. Checked on 2026-10-18 against primary sources (listed at the end, cited inline as `[n]`). Where only community reports exist, that is said explicitly.

## Short answer

**Use both, in layers. The devcontainer is the source of truth for the toolchain; WSL2 Ubuntu is the host it runs on.**

- **Host (needed either way):** an Ubuntu WSL2 distro (`Ubuntu-24.04` for Jazzy, `Ubuntu-26.04` for Lyrical), with `networkingMode=mirrored`. GUI (WSLg), GPU (d3d12), USB (usbipd) and LAN access to the Pi all live in the WSL2 VM, so every option goes through it.
- **Toolchain source of truth:** a `.devcontainer/` (Dockerfile `FROM ros:<distro>-ros-base`, the multi-arch official image). One definition serves three uses: the human's GUI sessions, GitHub Actions CI (amd64 and arm64), and unattended Claude Code agents.
- **Container engine:** Docker Engine (`docker-ce`) installed **inside** the Ubuntu WSL distro, **not Docker Desktop**. Docker Desktop's containers cannot see the host's network interfaces, so DDS discovery to the Pi breaks [15][19]. Docker's own docs say a Desktop install and an Engine inside a distro conflict [12].
- **Pi:** run ROS natively on Ubuntu Server (apt) and build there with `colcon`. CI on GitHub's native arm64 runners checks that every change still builds for arm64. Don't cross-compile: ROS dropped its cross-compile tool [30].
- **Optional:** a native `ros-<distro>-desktop` apt install in the WSL distro as a quick GUI/CLI fallback (`rviz2`, `rqt`, talker/listener tests). Dual-boot native Ubuntu is a last-resort fallback if Gazebo under WSLg turns out unusable (see Risks).

Deciding facts:

1. **Networking to the Pi** rules out Docker Desktop. Its host networking "works on layer 4" and "the container has no direct access to the interfaces of the host" [15]. Community reports say Docker Desktop doesn't use WSL's mirrored interface, and the fix is `docker-ce` inside the distro [19]. `--net=host` in a `docker-ce` container shares the distro's (mirrored) network.
2. **CI and AFK agents need a container anyway.** Official `ros` images are multi-arch (amd64 and arm64v8) [29]. GitHub offers arm64 Linux runners for private repos [40]. The Claude Code docs say unattended `--dangerously-skip-permissions` use belongs in a dev container with a non-root user [27]. A bare WSL distro auto-mounts every Windows drive under `/mnt` by default [3], so an agent running there could reach your whole C: drive.
3. **The GUI/GPU path works in both setups, with one shared caveat.** WSLg's GPU path is Mesa's d3d12 driver [4], and the container recipe is documented by Microsoft [6]. Gazebo calls WSLg "still not an officially tested platform" [37], and there is an open, d3d12-specific Gazebo GUI memory leak [38]. A container neither fixes nor causes this.

## Inspected on this laptop (read-only, 2026-10-18)

| Item | Value | Note |
|---|---|---|
| WSL | 2.6.1.0, kernel 6.6.87.2-1, WSLg 1.0.66 | Latest stable WSL is 3.0.3 (2026-10-09) [48]. Run `wsl --update`. |
| Windows | 10.0.26200 (Windows 11) | Mirrored mode needs 22H2+ [2]. OK. |
| WSL distros | only `docker-desktop` (stopped) | `wsl --list --online` offers `Ubuntu-24.04` and `Ubuntu-26.04`. |
| `.wslconfig` | absent | So: NAT networking, 8 GB VM (50% of 16 GB) [3]. |
| Docker | Desktop, client 28.4.0, engine not running | |
| GPUs | NVIDIA RTX 3050 Laptop (driver 566.07, 4 GB), AMD Radeon iGPU | Two adapters, so the GPU must be selected explicitly (below). |

## Options compared

- **A:** native ROS in an Ubuntu WSL2 distro.
- **B:** devcontainer on Docker Desktop (WSL2 backend).
- **C (recommended):** devcontainer on Docker Engine inside the Ubuntu WSL2 distro.

| Requirement | A: native WSL2 | B: Docker Desktop devcontainer | C: docker-ce-in-WSL devcontainer |
|---|---|---|---|
| **Gazebo + RViz2 with GPU** | Works through WSLg plus Mesa d3d12 [1][4]. Needs the GPU selected (below). | NVIDIA `--gpus` support is documented for CUDA [14]. OpenGL through WSLg from Desktop containers is not documented by Docker. Not verified. | Microsoft's WSLg container sample: bind-mount `/tmp/.X11-unix`, `/mnt/wslg`, `/usr/lib/wsl`; `--device=/dev/dxg`; `LD_LIBRARY_PATH=/usr/lib/wsl/lib` [6]. |
| **Joystick (Xbox 360 receiver)** | usbipd attaches the USB device to the WSL VM [7], but the stock WSL kernel has no joystick drivers (below). | Same kernel, plus an extra device-passthrough layer. | Same kernel, plus `--device` passthrough. |
| **Same toolchain in CI** | Only by duplicating the apt/rosdep steps. Will drift. | Yes (same image). | Yes (same image, `devcontainers/ci` [26] or `container:` jobs). |
| **Reproducible AFK agents** | Weak: no isolation, `/mnt/c` mounted [3]. | Yes [27]. | Yes [27]. |
| **Build for Pi 4 (arm64)** | No help. | buildx with QEMU is bundled [16]. | buildx works, QEMU installed manually [16]. Native arm64 CI runners are better [40]. |
| **Networking to the Pi** | Mirrored mode gives LAN access and multicast [2]. Hyper-V firewall rules needed (below). | Containers can't see host interfaces [15]. Community: Desktop ignores mirrored mode [19]. **Blocker.** | `--net=host` uses the distro's mirrored network. Same as A. |
| **VS Code** | WSL extension [22] | Dev Containers [20] | Dev Containers through the WSL extension: "you can use Docker installed in WSL" [21] |
| **Licence / cost** | Free | Free for personal use [18] | Free |

### Requirement details

**GUI and GPU.**

- WSLg needs a vGPU-capable Windows driver for "hardware accelerated OpenGL rendering" [1].
- The accelerated path is Mesa's d3d12 Gallium driver, upstream since Mesa 21.0 [4].
- On hybrid laptops, newer Mesa "will always default to the first enumerated integrated GPU". Set `MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA` and check with `glxinfo -B` [5]. On this laptop the default would otherwise be the AMD iGPU.
- Don't install a Linux NVIDIA driver inside WSL. The Windows driver is the only one needed [46].
- Gazebo's Ogre2 renderer "requires an OpenGL version higher than 3.3, preferably 4.3+" [36].
- Gazebo's maintainers' forum post says software rendering (`LIBGL_ALWAYS_SOFTWARE=1`) is no longer needed under WSLg for Garden/Harmonic. It also warns that WSLg is "still not an officially tested platform for Gazebo" [37].
- Distro pairing: Jazzy uses Gazebo Harmonic [33], Lyrical uses Gazebo Jetty [34].

**Joystick (interaction with issue #3).**

- The WSL 6.6 kernel config has `# CONFIG_INPUT_JOYSTICK is not set` and `# CONFIG_INPUT_JOYDEV is not set` [11].
- The Xbox driver `JOYSTICK_XPAD` lives in that disabled joystick menu [49].
- So the Xbox 360 wireless receiver gets no driver after `usbipd attach` without a custom kernel (`.wslconfig` `kernel=` [3]). A custom kernel applies to the whole WSL VM, so it covers options A and C equally.
- Once attached, a USB device is unavailable to Windows and is shared by all WSL 2 distros [7].
- The build plan runs `joy` on the Pi anyway, so this only affects laptop-side sim teleop. Issue #3 decides.

**Networking to the Pi.**

- Mirrored mode lists "Multicast support" and "Connect to WSL directly from your local area network" [2].
- With the default `firewall=true`, Windows Firewall and Hyper-V firewall rules filter WSL traffic [3]. Inbound needs an explicit Hyper-V rule (`Set-NetFirewallHyperVVMSetting … -DefaultInboundAction Allow` or `New-NetFirewallHyperVRule …`) [2].
- A community report (June 2026) fixed WSL2 (mirrored) ↔ Jetson ROS 2 discovery by adding inbound and outbound UDP rules restricted to the remote device's IP [47].
- Multicast **between Windows and its own WSL distro** is still broken in mirrored mode (microsoft/WSL#12344, open) [10]. That doesn't matter here: Foxglove on Windows talks to `foxglove_bridge` on the Pi over WebSocket, not DDS.
- Discovery that doesn't depend on multicast:
  - `ROS_STATIC_PEERS=<pi-ip>`, with `ROS_AUTOMATIC_DISCOVERY_RANGE` [32].
  - `rmw_zenoh`, which needs a router (TCP 7447) and has multicast scouting off by default [35]. Note: `ROS_STATIC_PEERS` and `ROS_AUTOMATIC_DISCOVERY_RANGE` "are not supported by rmw_zenoh" [32].
  - The middleware choice belongs to the architecture ticket (#6).

**CI.**

- GitHub-hosted labels include `ubuntu-24.04`, `ubuntu-26.04`, `ubuntu-24.04-arm` and `ubuntu-26.04-arm`. arm64 is available to private repos (2 vCPU / 8 GB) [40].
- GitHub Free includes 2,000 private-repo minutes per month. Linux arm64 is billed below x64 ($0.005 vs $0.006 per minute) [41].
- GHCR container storage is currently free [42].
- No GPU on standard runners [40], so CI runs Gazebo headless or not at all.
- `ros-tooling/setup-ros` recommends running inside a Docker container rather than on the bare runner [43]. The devcontainer image does this automatically.

**AFK agents.**

- Add Claude Code to the image with the Dev Container Feature. For a pinned version, install a fixed `@anthropic-ai/claude-code@X.Y.Z` from the Dockerfile and set `DISABLE_AUTOUPDATER=1` [27].
- `--dangerously-skip-permissions` is refused as root, so the image needs a non-root `remoteUser` [27].
- Pair it with egress restrictions (reference `init-firewall.sh`). Don't mount `~/.ssh` [27].
- Headless start: `devcontainer up` / `devcontainer exec` from `@devcontainers/cli` [25].
- Caveat: agent containers on the laptop share the WSL VM's RAM with Gazebo.

**VS Code.**

- WSL extension: the VS Code Server runs inside WSL [22].
- Dev Containers: "Reopen in Container" from a WSL folder [20]. With Docker in WSL, enable systemd so `dockerd` starts [21].
- Pi: Remote-SSH supports Ubuntu ARMv8l/AArch64 hosts (glibc ≥ 2.28) [23].
- Keep the repo in the Linux filesystem (`~/…`), not `/mnt/c`. Microsoft [8] and Docker [13] both say this, for speed and file-change events.

## How the Pi build and deploy works

1. **Pi runtime:** Ubuntu Server arm64 plus ROS from apt (`ros-<distro>-ros-base`).
   - Jazzy: Ubuntu 24.04, arm64 Tier 1 [33].
   - Lyrical: Ubuntu 26.04, arm64 Tier 1 [34]. Lyrical on 24.04 is only Tier 3, which means building from source [34].
   - Pi images: ubuntu.com currently lists 26.04.1 for the Pi 4 [45]. 24.04.x Pi images are still on cdimage [45].
2. **Build on the Pi:** `git pull` and `colcon build`. The default parallelism is the number of CPU cores [44]. On a 4 GB Pi 4, limit it with `--parallel-workers 1` and `MAKEFLAGS=-j2` when compiling the C++ hardware interface. That is a judgement call, not a sourced number. Edit over VS Code Remote-SSH [23].
3. **Guarantee in CI:** a matrix job on `ubuntu-<ver>-arm` that runs `colcon build && colcon test` inside `ros:<distro>-ros-base` (arm64 variant [29]). It catches arm64 breakage before it reaches the Pi.
4. **Not recommended now:**
   - Cross-compilation. "The cross_compile tool is not supported anymore"; ROS points to `docker buildx` multi-platform images instead [30].
   - buildx under QEMU on the laptop. Docker warns emulation "can be much slower than native builds, especially for compute-heavy tasks" [16].
5. **Optional later:** build arm64 images on the arm64 runner, push to GHCR, run on the Pi with Docker. Only worth it if the Pi's own build time becomes painful. It adds device passthrough (serial, `/dev/input`, camera, GPIO) and RAM overhead on a 4 GB Pi. The build plan's Coral fallback (Python 3.9 container) is a separate, narrow use.

## Open risks

| Risk | Impact | Mitigation |
|---|---|---|
| **Gazebo GUI memory leak under WSLg/d3d12** (gz-sim#2873, open; reproduced on Ubuntu 24.04 + Jazzy, NVIDIA; ~7–15 MB/min in an Oct 2026 measurement, 5 MB/s with heavy meshes in another) [38] | Long sim sessions eat the 16 GB laptop | Run `gz sim -s` (server) separately from the GUI and restart the GUI as needed. Keep worlds light. Raise the WSL memory cap. Watch the issue. Fallback: dual-boot native Ubuntu. |
| **Gazebo GUI crashes intermittently on WSLg** (gz-sim#3335, open; maintainer saw "Texture memory budget exceeded") [39] | Flaky sim startup | Try Ogre1 (`--render-engine ogre`) [36]. 4 GB VRAM is small. |
| **Mesa picks the AMD iGPU** [5] | Slow or failed rendering | `MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA` in the container env and `~/.bashrc`. Verify with `glxinfo -B`. |
| **OpenGL in a container through WSLg: d3d12 without `--gpus all`** | Microsoft's sample also uses `--gpus all` [6], which needs the NVIDIA Container Toolkit (min v2.6.0 [46]) | Spike in Phase 0: try without, add the toolkit if needed. |
| **Hyper-V firewall blocks DDS** [2][3][47] | Pi and laptop don't see each other | Hyper-V firewall UDP rules scoped to the Pi's IP. Static peers or Zenoh (#6). |
| **WSL kernel lacks joystick drivers** [11] | Laptop-side joystick won't work | Issue #3 (custom kernel vs. joystick only on the Pi / Windows). |
| **Docker Desktop vs docker-ce conflict** [12] | Two engines fight over `docker` | Turn off Desktop's WSL integration for the Ubuntu distro and its autostart, or uninstall Desktop. Both run in the same WSL VM and share `.wslconfig` limits [3][12]. |
| **16 GB RAM**: WSL defaults to 8 GB [3]; Gazebo, RViz, a colcon build and an agent container all share it | Out of memory or swapping | `memory=10GB`, `swap=8GB`, `autoMemoryReclaim=gradual` [3]. Don't run AFK agents during sim sessions. |
| **Old WSL (2.6.1) and NVIDIA driver (566.07)** | Missing fixes. WSL containers (`wslc`) need WSL ≥ 2.9.3 [9] | `wsl --update`; update the NVIDIA driver. |
| **Free CI minutes** (2,000/month, private) [41] | A cold ROS image build per run burns minutes | Prebuild and push the image to GHCR (`devcontainers/ci` `push`/`cacheFrom` [26]). GHCR storage is currently free [42]. |
| **Lyrical tooling is newer**: `setup-ros` lists Lyrical only in an example, not its support matrix [43]; Lyrical is Tier 3 on 24.04 [34] | Rough edges if Lyrical is chosen | The devcontainer avoids `setup-ros`. Choose the WSL distro to match #2. |

Watch item, not for now: WSL now ships its own container CLI, `wslc.exe` (WSL ≥ 2.9.3) [9]. It is a possible future replacement for docker-ce in WSL, but there is no Dev Containers integration or WSLg recipe documented yet.

## Setup outline for the recommendation

Phase 0, after issue #2 picks the distro. `<distro>`/`<ubuntu>` = `jazzy`/`24.04` or `lyrical`/`26.04`.

1. **Windows:**
   - Update: `wsl --update`, plus the latest NVIDIA driver.
   - Docker Desktop: turn off autostart and its WSL integration, or uninstall it [12].
   - Install the distro: `wsl --install -d Ubuntu-<ubuntu>`.
2. **`%UserProfile%\.wslconfig`** [3]:
   ```ini
   [wsl2]
   networkingMode=mirrored
   memory=10GB
   swap=8GB
   [experimental]
   autoMemoryReclaim=gradual
   ```
   Then run `wsl --shutdown`.
3. **Hyper-V firewall** (admin PowerShell) [2]. Allow inbound UDP from the Pi only. This adapts the documented `New-NetFirewallHyperVRule` example:
   ```powershell
   New-NetFirewallHyperVRule -Name "ROS-from-Pi" -DisplayName "ROS from Pi" -Direction Inbound `
     -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -Protocol UDP -RemoteAddresses <pi-ip>
   ```
   For Zenoh, add TCP 7447 [35].
4. **In the Ubuntu distro:**
   - Enable systemd (`/etc/wsl.conf` `[boot] systemd=true`) [3][21].
   - Install Docker Engine from Docker's apt repo [17].
   - Clone the repo to `~/stubentigerV2` [8].
   - Verify the GPU: `MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA glxinfo -B` should show the D3D12 NVIDIA adapter [5].
5. **`.devcontainer/`** (exact layout decided in #7):
   - Dockerfile `FROM ros:<distro>-ros-base`.
   - `rosdep install` of the workspace deps.
   - A non-root user.
   - Claude Code pinned [27].
   - Simulation/desktop packages in a GUI layer or a separate config. `osrf/ros:<distro>-desktop-full` exists but is amd64-only [28].
   - For the human GUI config, add `--net=host`, `--device=/dev/dxg`, the WSLg/`/usr/lib/wsl` mounts and env vars from [6], and `MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA` [5]. These go in `runArgs`/`mounts`/`containerEnv` [24]. ROS's own VS Code devcontainer guide also uses `--net=host` [31].
   - The CI/agent config stays headless.
6. **CI:**
   - An amd64 job and an arm64 job (`ubuntu-<ubuntu>-arm`) build and test in the same image [40][26].
   - Push the prebuilt image to GHCR [42].
7. **Pi:**
   - Ubuntu Server arm64 [45] and `ros-<distro>-ros-base` from apt.
   - Clone, `colcon build --symlink-install --parallel-workers 1` [44].
   - VS Code Remote-SSH [23].
8. **Phase 0 acceptance (from the build plan):** talker on the Pi, listener in the WSL container with `--net=host`. Then the reverse direction.

## Sources

1. Microsoft, *Run Linux GUI apps with WSL*. https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps
2. Microsoft, *Accessing network applications with WSL* (mirrored mode, Hyper-V firewall). https://learn.microsoft.com/en-us/windows/wsl/networking
3. Microsoft, *Advanced settings configuration in WSL* (`.wslconfig`, `wsl.conf`; updated 2026-10-16). https://learn.microsoft.com/en-us/windows/wsl/wsl-config
4. microsoft/wslg README (vGPU, Mesa d3d12). https://github.com/microsoft/wslg
5. microsoft/wslg wiki, *GPU selection in WSLg*. https://github.com/microsoft/wslg/wiki/GPU-selection-in-WSLg
6. microsoft/wslg, *Containerizing GUI applications with WSLg*. https://github.com/microsoft/wslg/blob/main/samples/container/Containers.md
7. Microsoft, *Connect USB devices*. https://learn.microsoft.com/en-us/windows/wsl/connect-usb
8. Microsoft, *Working across file systems*. https://learn.microsoft.com/en-us/windows/wsl/filesystems
9. Microsoft, *WSL container* (`wslc`, WSL ≥ 2.9.3). https://learn.microsoft.com/en-us/windows/wsl/wsl-container
10. microsoft/WSL#12344, *WSL2 networking mirrored - multicast support (Windows host <> WSL distro)* (open). https://github.com/microsoft/WSL/issues/12344
11. WSL kernel config, branch `linux-msft-wsl-6.6.y`. https://github.com/microsoft/WSL2-Linux-Kernel/blob/linux-msft-wsl-6.6.y/arch/x86/configs/config-wsl
12. Docker, *Docker Desktop WSL 2 backend on Windows*. https://docs.docker.com/desktop/features/wsl/
13. Docker, *WSL best practices*. https://docs.docker.com/desktop/features/wsl/best-practices/
14. Docker, *GPU support in Docker Desktop for Windows*. https://docs.docker.com/desktop/features/gpu/
15. Docker, *Host network driver* (Docker Desktop section). https://docs.docker.com/engine/network/drivers/host/
16. Docker, *Multi-platform builds*. https://docs.docker.com/build/building/multi-platform/
17. Docker, *Install Docker Engine on Ubuntu*. https://docs.docker.com/engine/install/ubuntu/
18. Docker, *Docker Desktop license agreement*. https://docs.docker.com/subscription/desktop-license/
19. Docker Community Forums (community, not official), *Host networking not working on Docker Desktop in WSL2 with mirrored mode*, May 2025. https://forums.docker.com/t/host-networking-not-working-on-docker-desktop-in-wsl2-with-mirrored-mode/147994
20. VS Code, *Developing inside a Container*. https://code.visualstudio.com/docs/devcontainers/containers
21. VS Code, *Alternative Docker options* (Docker in WSL). https://code.visualstudio.com/remote/advancedcontainers/docker-options
22. VS Code, *Developing in WSL*. https://code.visualstudio.com/docs/remote/wsl
23. VS Code, *Remote Development with Linux* (host prerequisites). https://code.visualstudio.com/docs/remote/linux
24. Dev Container spec, *devcontainer.json reference*. https://containers.dev/implementors/json_reference/
25. devcontainers/cli. https://github.com/devcontainers/cli
26. devcontainers/ci GitHub Action. https://github.com/devcontainers/ci
27. Anthropic, *Claude Code: Development containers*. https://code.claude.com/docs/en/devcontainer
28. osrf/docker_images (README; `ros/jazzy/ubuntu/noble/*`, `ros/lyrical/ubuntu/resolute/*`, `platform.yaml` arch amd64). https://github.com/osrf/docker_images
29. Docker Hub, official `ros` image (tags `jazzy-*`, `lyrical-*`; amd64 and arm64v8). https://hub.docker.com/_/ros
30. ROS 2 docs, *Cross-compilation* / *About Cross-compilation* (source, rolling branch). https://github.com/ros2/ros2_documentation/blob/rolling/source/Developer-Tools/Build/About-Cross-Compilation.rst
31. ROS 2 docs, *Setup ROS 2 with VSCode and Docker* (source). https://github.com/ros2/ros2_documentation/blob/rolling/source/Developer-Tools/Build/Setup-ROS-2-with-VSCode-and-Docker-Container.rst
32. ROS 2 docs, *Improved Dynamic Discovery* (source). https://github.com/ros2/ros2_documentation/blob/rolling/source/Developer-Tools/Introspection-and-analysis/Improved-Dynamic-Discovery.rst
33. REP 2000, Jazzy Jalisco targeted platforms. https://github.com/ros-infrastructure/rep/blob/master/rep-2000.rst
34. ROS 2 docs, *Lyrical Luth Supported Platforms* (source). https://github.com/ros2/ros2_documentation/blob/rolling/source/Releases/lyrical/supported-platforms.rst
35. ros2/rmw_zenoh README. https://github.com/ros2/rmw_zenoh
36. Gazebo, *Troubleshooting* (Harmonic). https://gazebosim.org/docs/harmonic/troubleshooting/
37. Open Robotics Discourse, *WSLg with GPU support available on latest version of Gazebo Garden and Harmonic* (Nov 2023). https://discourse.openrobotics.org/t/wslg-with-gpu-support-available-on-latest-version-of-gazebo-garden-and-harmonic/48128
38. gazebosim/gz-sim#2873, *Gazebo Harmonic WSLg memory leak* (open; comment of 2026-10-03). https://github.com/gazebosim/gz-sim/issues/2873
39. gazebosim/gz-sim#3335, *Gazebo GUI intermittently crashes or fails to open on WSLg* (open). https://github.com/gazebosim/gz-sim/issues/3335
40. GitHub Docs, *GitHub-hosted runners reference*. https://docs.github.com/en/actions/reference/runners/github-hosted-runners
41. GitHub Docs, *GitHub Actions billing*. https://docs.github.com/en/billing/concepts/product-billing/github-actions
42. GitHub Docs, *GitHub Packages billing*. https://docs.github.com/en/billing/concepts/product-billing/github-packages
43. ros-tooling/setup-ros README. https://github.com/ros-tooling/setup-ros
44. colcon, *Executor arguments*. https://colcon.readthedocs.io/en/released/reference/executor-arguments.html
45. Canonical, *Ubuntu for Raspberry Pi* downloads, https://ubuntu.com/download/raspberry-pi, and 24.04 image index, https://cdimage.ubuntu.com/releases/24.04/release/
46. NVIDIA, *CUDA on WSL User Guide*. https://docs.nvidia.com/cuda/wsl-user-guide/index.html
47. Open Robotics Discourse (community), *ROS2 multi-machine with WSL2 + Linux (NVIDIA Jetson Orin Nano)*, June 2026. https://discourse.openrobotics.org/t/ros2-multi-machine-with-wsl2-linux-nvidia-jetson-orin-nano/55452
48. microsoft/WSL releases (3.0.3, 2026-10-09). https://github.com/microsoft/WSL/releases
49. Linux kernel, `drivers/input/joystick/Kconfig` (`JOYSTICK_XPAD`). https://github.com/torvalds/linux/blob/master/drivers/input/joystick/Kconfig
