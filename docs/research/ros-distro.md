# Research: Jazzy or Lyrical — which ROS 2 distro?

Resolves issue [#2](https://github.com/mkogel/stubentigerV2/issues/2). Researched 2026-10-18. Package data comes from the apt indexes on packages.ros.org dated 2026-10-05 (resolute) and 2026-10-06 (noble).

## Question

Should Stubentiger build on **ROS 2 Jazzy Jalisco** (Ubuntu 24.04 Noble) or **ROS 2 Lyrical Luth** (Ubuntu 26.04 Resolute)? Target hardware is a Raspberry Pi 4 (4 GB) on Ubuntu Server (arm64). The dev laptop runs Windows 11 with WSL2/WSLg (amd64) and simulates in Gazebo via `gz_ros2_control`.

## Answer

**Use Jazzy on Ubuntu 24.04.** Lyrical is a viable distro, and every core stack package is built for it on both architectures. Two of our hardware dependencies are the problem. The Coral Edge TPU runtime has no build for Ubuntu 26.04 or Python 3.14. The RPLidar driver binary `rplidar_ros` currently fails to build for Lyrical. Jazzy is supported until May 2029, which covers the whole build plan. Plan a migration to Lyrical (or the 2028 LTS) before then.

## Findings

### 1. Support windows and platforms

| | Jazzy Jalisco | Lyrical Luth |
| --- | --- | --- |
| Released / EOL | May 23, 2024 / May 2029 [1] | May 22, 2026 / May 2031 [1] |
| Tier 1 OS | Ubuntu Noble 24.04, amd64 + arm64, deb packages [2] | Ubuntu Resolute 26.04, amd64 + arm64, deb packages [3] |
| Other Ubuntu | Jammy 22.04: Tier 3 (source only) [2] | Noble 24.04: **Tier 3 (source only)**, until 2029-06-01 [3] |
| Ubuntu standard support | 24.04 LTS: until May 2029 [4] | 26.04 LTS: until May 2031 [4] |
| System Python | 3.12.3 [2] | 3.14.3 (Lyrical supports 3.12–3.14) [3] |
| Paired Gazebo | Harmonic (LTS), EOL May 2029 [5][6] | Jetty (LTS), EOL May 2031 [5][6] |
| `rmw_zenoh_cpp` tier | Not in the Jazzy middleware table [2]. Binary 0.2.11 is still built [7] | Tier 1 [3]. Binary 0.10.6 [8] |
| Released packages (arm64, excl. `-dbgsym`) | ~2,433 [7] | ~1,612 [8] |

Note: REP 2000 only covers distros up to Kilted. From Lyrical on, platform data lives in each release's docs [2][3].

On the support dates: Jazzy, Gazebo Harmonic and Ubuntu 24.04 all reach EOL in May 2029. Lyrical, Gazebo Jetty and Ubuntu 26.04 all reach EOL in May 2031 [1][4][5].

On Python: Lyrical binaries exist only for Resolute. Moving to Lyrical therefore also means moving to Ubuntu 26.04 and Python 3.14 [3].

### 2. Binary (apt) availability, amd64 and arm64

Sources: the `Packages` indexes of packages.ros.org for `noble` [7] and `resolute` [8], cross-checked against rosdistro `distribution.yaml` for Jazzy [9] and Lyrical [10]. Versions are the ones published on each arch.

| Package (apt name suffix) | Jazzy amd64 | Jazzy arm64 | Lyrical amd64 | Lyrical arm64 |
| --- | --- | --- | --- | --- |
| `ros2-control` | 4.48.1 | 4.48.1 | 6.10.1 | 6.10.1 |
| `ros2-controllers` | 4.42.1 | 4.42.1 | 6.9.0 | 6.9.0 |
| `diff-drive-controller` | 4.42.1 | 4.42.1 | 6.9.0 | 6.9.0 |
| `gz-ros2-control` | 1.2.20 | 1.2.20 | 3.0.9 | 3.0.9 |
| `ros-gz` / `ros-gz-sim` | 1.0.24 | 1.0.24 | 3.0.10 | 3.0.10 |
| `gz-sim-vendor` (Gazebo) | 0.0.13 (Harmonic) | 0.0.13 | 0.4.6 (Jetty) | 0.4.6 |
| `twist-mux` | 4.5.0 | 4.5.0 | 4.5.1 | 4.5.1 |
| `joy` | 3.3.0 | 3.3.0 | 3.3.0 | 3.3.0 |
| `teleop-twist-joy` | 2.6.5 | 2.6.5 | 2.6.5 | 2.6.5 |
| `navigation2` | 1.3.13 | 1.3.13 | 1.5.2 | 1.5.2 |
| `nav2-collision-monitor` | 1.3.13 | 1.3.13 | 1.5.2 | 1.5.2 |
| `opennav-docking` (Nav2 docking) | yes | yes | yes | yes |
| `slam-toolbox` | 2.8.5 | 2.8.5 | 2.10.0 | 2.10.0 |
| `robot-localization` | 3.8.3 | 3.8.3 | 3.10.0 | 3.10.0 |
| `sllidar-ros2` | **not released** | **not released** | **not released** | **not released** |
| `rplidar-ros` (Slamtec, supports A1) | 2.1.0 | 2.1.0 | **missing** | **missing** |
| `camera-ros` (+ `libcamera`) | 0.7.0 | 0.7.0 | 0.7.0 | 0.7.0 |
| `foxglove-bridge` | 3.6.0 | 3.6.0 | 3.6.0 | 3.6.0 |
| `rmw-zenoh-cpp` | 0.2.11 | 0.2.11 | 0.10.6 | 0.10.6 |
| `imu-filter-madgwick` (Phase 2) | 2.1.6 | 2.1.6 | 2.2.2 | 2.2.2 |
| `twist-stamper` | yes | yes | yes | yes |

Details:

- **`sllidar_ros2`** is not in either distribution file [9][10]. The Slamtec repo was last pushed in July 2024, and its README names only Foxy and Humble [11]. It has to be built from source on either distro.
- **`rplidar_ros`** is in Lyrical's `distribution.yaml` at 2.1.0-5. Its source there is the `allenh1/rplidar_ros` fork, not Slamtec [10]. The binary is still missing from the apt index [8]. The latest Lyrical build-farm jobs failed on both arches: [amd64](https://build.ros2.org/job/Lbin_uR64__rplidar_ros__ubuntu_resolute_amd64__binary/) build #186 and [arm64](https://build.ros2.org/job/Lbin_armv8_uRv8__rplidar_ros__ubuntu_resolute_arm64__binary/) build #181 [12]. On Jazzy the upstream Slamtec package is a ready binary fallback on both arches [7][9].
- **`rf2o_laser_odometry`** is used as a cross-check in Phase 2 of the build plan. It is not released for either distro [7][8], so it is a source build in both cases.
- **`camera_ros`** works the same way on both distros. The bloomed `libcamera` is upstream libcamera, and it "may not contain full support for all Raspberry Pi camera modules". Full support needs the `raspberrypi/libcamera` fork built from source [13].

### 3. Ubuntu Server on Raspberry Pi 4 (4 GB)

- Canonical ships `preinstalled-server-arm64+raspi` images for 24.04.5 and for 26.04 / 26.04.1 [14][15]. Its supported-models table marks the Pi 4B as Server/Desktop/Core ("SDC") for both 24.04 LTS and 26.04 LTS [15].
- Certification:
  - The ubuntu.com Raspberry Pi page lists the Pi 4B as "Yes, certified" for Ubuntu 26.04 LTS [16].
  - The certification record for the "Raspberry Pi 4 Model B 4 GB" currently lists 20.04 and 24.04 LTS (plus Core 20/22/24) and does not list 26.04 yet [17].
- **Ubuntu 26.04 requires a Pi 4B boot EEPROM dated 2022-11-25 or later. Ubuntu 24.04 has no minimum.** Canonical's documented fix is to boot a 24.04 image, run `sudo rpi-eeprom-update -a`, and reboot [15].

Both OSes are officially supported on our Pi. 26.04 adds one EEPROM check, which is a small one-time step.

### 4. Python version and the Coral USB Accelerator

- **Official Coral stack:**
  - Coral's getting-started guide requires "Python 3.6 - 3.9" on Debian 10 derivatives [18].
  - `google-coral/pycoral` is archived. Its last release is v2.0.0 from July 2021, with classifiers for Python 3.6–3.9 [19].
  - The official `tflite-runtime` on PyPI stops at 2.14.0 (2023) with aarch64 wheels for cp38–cp311 [20].
  - Neither official stack runs on Jazzy's Python 3.12 or on Lyrical's Python 3.14.
- **Community builds (feranick):**
  - `feranick/pycoral` 2.0.3 (Oct 2024) ships aarch64 wheels for cp39–**cp312** [21].
  - `feranick/TFlite-builds` 2.17.1 also ships aarch64 wheels for cp39–cp312 [22].
  - `feranick/libedgetpu` 16.0 (TF 2.19.1, Sep 2025) ships arm64 debs for `ubuntu22.04`, **`ubuntu24.04`**, bookworm, bullseye and trixie. It ships **no `ubuntu26.04` build** [23].
  - So a working Edge TPU runtime path exists for Ubuntu 24.04 + Python 3.12 (Jazzy), but not for 26.04 + 3.14 (Lyrical).
- **LiteRT (`ai-edge-litert`)** is Google's successor to `tflite-runtime`. Version 2.3.0 (2026-10-06) ships aarch64 wheels for cp310–**cp314** [24]. Whether `libedgetpu`'s delegate loads into LiteRT 2.3 is **not established** by any primary source found. The community `libedgetpu` is built per TF version (release names like "16.0TF2.19.1"), which points to a tight ABI coupling [23].

### 5. Official Docker images for CI

| Image | Jazzy | Lyrical |
| --- | --- | --- |
| `ros:<distro>-ros-core` / `-ros-base` / `-perception` (Docker Official Image) | amd64 + arm64v8, updated 2026-10-17 | amd64 + arm64v8, updated 2026-10-17 |
| `osrf/ros:<distro>-desktop` / `-desktop-full` | amd64 only, updated 2026-09-10 | amd64 only, updated 2026-09-10 |

Source: the Docker Hub tag API for `library/ros` and `osrf/ros` [25]. The two distros are at parity, so CI does not decide the question.

### 6. Dev laptop (WSL2)

Microsoft's WSL distribution list offers both `Ubuntu-24.04` and `Ubuntu-26.04` [26]. Either distro works on the laptop, so this does not decide the question either.

## Recommendation: Jazzy (Ubuntu 24.04)

Deciding facts:

1. **Coral runtime.** The only maintained Edge TPU path is the feranick community stack (`libedgetpu`, `pycoral`, `tflite_runtime`). It ships for Ubuntu 24.04 / Python 3.12 and has no Ubuntu 26.04 / Python 3.14 build [21][22][23]. Lyrical runs only on 26.04 / Python 3.14 [3].
2. **LiDAR driver.** Jazzy has a working `rplidar_ros` binary on amd64 and arm64 [7]. On Lyrical the package is in the distro file, but its build-farm jobs fail on both arches and no binary is published [8][10][12].
3. **Long enough support.** Jazzy (May 2029), Gazebo Harmonic (May 2029) and Ubuntu 24.04 (May 2029) cover the whole build plan [1][4][5].
4. **The rest of the stack is equal.** `ros2_control`, `diff_drive_controller`, `gz_ros2_control`, `twist_mux`, `joy`, `teleop_twist_joy`, Nav2 (collision monitor, docking), `slam_toolbox`, `robot_localization`, `camera_ros`, `foxglove_bridge` and `rmw_zenoh_cpp` are all binaries on amd64 and arm64 for **both** distros [7][8]. So Jazzy gives up no required package.
5. **Pi 4 support.** Both OSes support the Pi 4B [15]. 24.04 needs no EEPROM check, while 26.04 needs an EEPROM dated 2022-11-25 or later [15].
6. **Larger ecosystem.** Jazzy has about 50% more released packages on arm64 (~2,433 vs ~1,612) [7][8]. This makes it more likely that later-phase packages (perception, voice) already exist as binaries.

What Lyrical would give us: two more years of support (to May 2031), newer Nav2 (1.5.x) and ros2_control (6.x), and Tier 1 `rmw_zenoh` [1][3][8]. None of these is needed for the Virtual MVP or the Physical MVP.

This agrees with the decision already in `docs/initial-buildplan.md` ("Software-Stack"). The Coral argument there now has primary-source backing.

## Open risks

- **Jazzy EOL is May 2029.** The ROS distro, Gazebo Harmonic and Ubuntu 24.04 all end at the same time [1][4][5]. Moving to Lyrical later also means a Pi OS reinstall to 26.04, because Lyrical on Noble is Tier 3, source only [3]. The ros2_control 4.x → 6.x and Nav2 1.3 → 1.5 jumps will need config migration.
- **The Coral path depends on one community maintainer** (feranick) [21][23]. The last `pycoral` wheel is from Oct 2024 and the last `libedgetpu` from Sep 2025. If it breaks, fall back to CPU inference or a different accelerator. Coral is optional in the plan.
- **LiteRT + Edge TPU delegate compatibility is unverified** [24]. Prototype it on the Pi before Phase 5.
- **Pi camera:** the binary `libcamera` may not fully support Pi camera modules, so a source build of the `raspberrypi/libcamera` fork may be needed. This applies to both distros [13]. Test the Camera v2 (IMX219) early.
- **`sllidar_ros2` is unreleased** and the Slamtec repo has been inactive since mid-2024 [11]. Plan to build it from source, or use the `rplidar_ros` binary on Jazzy [7].
- **Changing package state:** the Lyrical `rplidar_ros` failure may get fixed. Package availability can change with each sync, so re-check before any future migration.

## Sources

1. ROS 2 Releases list (release and EOL dates): https://docs.ros.org/en/rolling/Releases.html
2. REP 2000, ROS 2 Releases and Target Platforms (Jazzy section; scope note "up to Kilted Kaiju"): https://reps.openrobotics.org/rep-2000/
3. Lyrical Luth Supported Platforms: https://docs.ros.org/en/lyrical/Releases/lyrical/supported-platforms.html
4. Ubuntu release cycle: https://ubuntu.com/about/release-cycle
5. Gazebo Releases (Harmonic EOL May 2029, Jetty EOL May 2031): https://gazebosim.org/docs/latest/releases/
6. Installing Gazebo with ROS (Jazzy ↔ Harmonic, Lyrical ↔ Jetty): https://gazebosim.org/docs/latest/ros_installation/
7. ROS 2 apt index, Ubuntu noble (amd64/arm64): http://packages.ros.org/ros2/ubuntu/dists/noble/main/binary-arm64/Packages.gz and `.../binary-amd64/Packages.gz`
8. ROS 2 apt index, Ubuntu resolute (amd64/arm64): http://packages.ros.org/ros2/ubuntu/dists/resolute/main/binary-arm64/Packages.gz and `.../binary-amd64/Packages.gz`
9. rosdistro Jazzy distribution file: https://github.com/ros/rosdistro/blob/master/jazzy/distribution.yaml
10. rosdistro Lyrical distribution file: https://github.com/ros/rosdistro/blob/master/lyrical/distribution.yaml
11. Slamtec/sllidar_ros2 (README, last push 2024-07-12): https://github.com/Slamtec/sllidar_ros2
12. ROS 2 build farm, `rplidar_ros` Lyrical binary jobs: https://build.ros2.org/job/Lbin_uR64__rplidar_ros__ubuntu_resolute_amd64__binary/ and https://build.ros2.org/job/Lbin_armv8_uRv8__rplidar_ros__ubuntu_resolute_arm64__binary/
13. camera_ros README (libcamera note): https://github.com/christianrauch/camera_ros
14. Ubuntu image directories: https://cdimage.ubuntu.com/releases/24.04/release/ and https://cdimage.ubuntu.com/releases/26.04/release/
15. Canonical hardware docs, Install Ubuntu on the Raspberry Pi (supported models, minimum EEPROM dates): https://canonical-ubuntu-hardware-support.readthedocs-hosted.com/boards/how-to/ubuntu_supported/raspberry-pi/
16. Ubuntu for Raspberry Pi download page: https://ubuntu.com/download/raspberry-pi
17. Ubuntu certification, Raspberry Pi 4 Model B 4 GB: https://ubuntu.com/certified/201911-27455
18. Coral USB Accelerator getting started: https://coral.ai/docs/accelerator/get-started/
19. google-coral/pycoral (archived; v2.0.0 release; `setup.py` classifiers): https://github.com/google-coral/pycoral
20. PyPI `tflite-runtime`: https://pypi.org/project/tflite-runtime/
21. feranick/pycoral releases: https://github.com/feranick/pycoral/releases
22. feranick/TFlite-builds releases: https://github.com/feranick/TFlite-builds/releases
23. feranick/libedgetpu releases: https://github.com/feranick/libedgetpu/releases
24. PyPI `ai-edge-litert`: https://pypi.org/project/ai-edge-litert/
25. Docker Hub `ros` official image and `osrf/ros`: https://hub.docker.com/_/ros and https://hub.docker.com/r/osrf/ros
26. Microsoft WSL distribution list: https://github.com/microsoft/WSL/blob/master/distributions/DistributionInfo.json
