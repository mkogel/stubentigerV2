# Dev laptop setup

The Windows 11 laptop runs the devcontainer on **docker-ce inside an Ubuntu WSL2 distro**, never on Docker Desktop. Follow the steps in order; each one ends with a check. This guide is the checklist for the Dev laptop setup block (#27): record each run there as a comment with the date, the commit SHA and pass/fail or the measured value per step.

| Dev laptop setup criterion | Steps |
|---|---|
| Branch protection on `main` requires `ci` only | 12 |
| docker-ce with mirrored networking; the devcontainer opens and `colcon build` runs | 1–4, 9 |
| Gazebo Harmonic on WSLg, real-time factor recorded | 5, 10 |
| usbipd attaches the receiver, `xpad` loads, `/joy` shows the SDL indices | 6–8, 11 |

Commands marked **PowerShell** run on Windows; everything else runs in the Ubuntu distro unless it says "in the container".

## 1. Update WSL and install the Ubuntu distro

**PowerShell (admin):**

```powershell
wsl --update
wsl --version          # WSL 2.x is needed for mirrored networking
wsl --install -d Ubuntu-24.04
```

Create the Linux user when asked. Check that systemd runs (Ubuntu 24.04 enables it by default):

```bash
systemctl is-system-running    # "running" or "degraded" is fine
```

## 2. Give WSL memory and mirrored networking

Create or edit `%UserProfile%\.wslconfig` on Windows:

```ini
[wsl2]
# Gazebo, RViz2 and colcon builds need room; leave the rest to Windows.
memory=12GB
networkingMode=mirrored
```

Pick `memory` as about two thirds of the laptop's RAM. Then **PowerShell:** `wsl --shutdown`, and reopen the distro.

Check: `wslinfo --networking-mode` prints `mirrored`.

## 3. Install docker-ce in the distro

If Docker Desktop is installed, turn off its WSL integration for this distro (Docker Desktop → Settings → Resources → WSL integration), or quit it. Then install docker-ce from Docker's apt repository:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin
sudo usermod -aG docker "$USER"
```

Close and reopen the distro so the group applies.

Check: `docker run --rm --network=host hello-world` works, and `docker context show` prints `default` (not `desktop-linux`).

## 4. Use the NVIDIA GPU from WSL

Install the current NVIDIA driver **on Windows only** (GeForce/Studio driver from NVIDIA). Never install a Linux NVIDIA driver inside WSL; WSL maps the Windows driver into `/usr/lib/wsl/lib`.

Check: `ls /dev/dxg` exists and `/usr/lib/wsl/lib/nvidia-smi` lists the GPU.

The devcontainer passes `/dev/dxg` and `/usr/lib/wsl` through and sets `GALLIUM_DRIVER=d3d12` and `MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA`, so Mesa renders on the NVIDIA adapter rather than the integrated GPU. Step 10 checks it.

## 5. Make the dev image pullable

CI publishes `ghcr.io/mkogel/stubentiger-dev:jazzy`. A new GHCR package is private, so once, on GitHub: your profile → Packages → `stubentiger-dev` → Package settings → Change visibility → **Public**. The image holds only public toolchain packages, never secrets.

Check: `docker pull ghcr.io/mkogel/stubentiger-dev:jazzy` works without `docker login`.

## 6. Install usbipd-win and attach the Xbox receiver

**PowerShell (admin):**

```powershell
winget install --exact dorssel.usbipd-win
usbipd list                          # find the Xbox 360 receiver's BUSID
usbipd bind --busid <BUSID>          # once per device
usbipd attach --wsl --busid <BUSID>  # after every replug or WSL restart
```

`usbipd attach --wsl --busid <BUSID> --auto-attach` keeps it attached across replugs while the window stays open.

Check, in the distro: `lsusb` lists the Microsoft Xbox 360 receiver.

## 7. Build and load the custom WSL kernel with `xpad`

The stock WSL kernel has no joystick drivers. Build Microsoft's kernel for the running version with `CONFIG_INPUT_JOYSTICK=y` and `CONFIG_JOYSTICK_XPAD=m`:

```bash
sudo apt-get install -y build-essential flex bison dwarves libssl-dev libelf-dev bc cpio python3 git
version=$(uname -r | sed 's/-microsoft.*//')
git clone --depth 1 --branch "linux-msft-wsl-$version" \
  https://github.com/microsoft/WSL2-Linux-Kernel.git ~/wsl-kernel
cd ~/wsl-kernel
cp Microsoft/config-wsl .config
scripts/config --enable CONFIG_INPUT_EVDEV --enable CONFIG_INPUT_JOYSTICK --module CONFIG_JOYSTICK_XPAD
make olddefconfig
grep -E 'CONFIG_INPUT_JOYSTICK=|CONFIG_JOYSTICK_XPAD=' .config   # =y and =m
make -j"$(nproc)"
sudo make modules_install
mkdir -p /mnt/c/wsl && cp arch/x86/boot/bzImage /mnt/c/wsl/bzImage
echo xpad | sudo tee /etc/modules-load.d/xpad.conf
```

Point WSL at the new kernel in `%UserProfile%\.wslconfig`, under `[wsl2]`:

```ini
kernel=C:\\wsl\\bzImage
```

**PowerShell:** `wsl --shutdown`, reopen the distro, and attach the receiver again (step 6).

Check: `uname -v` shows today's build date, `lsmod | grep xpad` lists the module, and `ls /dev/input/` shows `js0` and an `event*` device once the controller is on.

When `wsl --update` moves WSL to a new kernel line, repeat this step for the new version.

## 8. Let the container user open the input devices

The devcontainer mounts `/dev/input` and allows input devices (major 13) through a device-cgroup rule, but the device files belong to root. A udev rule in the distro opens them to the container's `ubuntu` user:

```bash
echo 'SUBSYSTEM=="input", KERNEL=="event*|js*", MODE="0666"' \
  | sudo tee /etc/udev/rules.d/99-input.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Check: `ls -l /dev/input/js0` shows `crw-rw-rw-`.

## 9. Open the devcontainer and build

Clone the repo inside the distro's own filesystem (`~/`), not under `/mnt/c`:

```bash
git clone https://github.com/mkogel/stubentigerV2.git ~/stubentigerV2
code ~/stubentigerV2
```

In VS Code (with the WSL and Dev Containers extensions), run **Dev Containers: Reopen in Container**. The container runs as `ubuntu`, gets the Claude Code CLI from its devcontainer feature, and installs the pre-commit hook.

Check, in the container: the build, test and lint commands from `CLAUDE.md` ("Build and test") all pass.

## 10. Run Gazebo Harmonic on WSLg

In the container, check the renderer first:

```bash
glxinfo -B | grep -E 'OpenGL renderer'   # D3D12 (NVIDIA ...), not llvmpipe
```

Run the server and the GUI as separate processes (this contains a WSLg GUI memory leak), in two terminals:

```bash
gz sim -s -r shapes.sdf     # terminal 1: server
gz sim -g                   # terminal 2: GUI
```

Record the real-time factor shown in the GUI's bottom-right corner. If Gazebo does not render or runs far below real time, record that on the issue and open a new decision (dual-boot); it does not block the AFK sim blocks.

## 11. See the Xbox controller on `/joy`

With the receiver attached (step 6) and the controller on, in the container:

```bash
ros2 run joy game_controller_node      # terminal 1
ros2 topic echo /joy                    # terminal 2
```

Check against the SDL game-controller layout that the Teleop config uses, and record any index that differs:

| Input | `/joy` index |
|---|---|
| LB (Dead-man button) | `buttons[9]` |
| RB (Turbo) | `buttons[10]` |
| Left stick Y (speed) | `axes[1]` |
| Right stick X (turn) | `axes[2]` |

## 12. Protect `main`

On GitHub: repo Settings → Branches → Add branch protection rule (or a ruleset) for `main`:

- Require a pull request before merging.
- Require status checks to pass, with **`ci`** as the only required check. It appears in the search box once CI has run once.
- Do not allow bypassing the settings.

Check: an open PR shows `ci` as "Required".
