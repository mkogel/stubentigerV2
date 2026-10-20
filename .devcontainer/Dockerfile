# Stubentiger dev image: the whole Jazzy toolchain for the laptop, CI and AFK agents.
# Published as ghcr.io/mkogel/stubentiger-dev:jazzy (amd64 + arm64) by .github/workflows/ci.yml.
# Any change in .devcontainer/ rebuilds the image; the weekly CI run rebuilds it from scratch.
FROM ros:jazzy-ros-base

ARG GITLEAKS_VERSION=8.30.1
ARG TARGETARCH

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive

# ROS: desktop (RViz2), Gazebo Harmonic, ros2_control, Teleop; C++ and Python tooling.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ros-jazzy-desktop \
      ros-jazzy-ros-gz \
      ros-jazzy-ros2-control \
      ros-jazzy-ros2-controllers \
      ros-jazzy-gz-ros2-control \
      ros-jazzy-diff-drive-controller \
      ros-jazzy-gpio-controllers \
      ros-jazzy-joy \
      ros-jazzy-teleop-twist-joy \
      ros-jazzy-twist-mux \
      ros-jazzy-foxglove-bridge \
      ros-jazzy-xacro \
      liburdfdom-tools \
      ccache \
      clang-format \
      clang-tidy \
      libxml2-utils \
      mesa-utils \
      python3-mypy \
      pipx \
      git \
      sudo \
      curl \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python CLIs in isolated venvs, on the PATH for every user.
ENV PIPX_HOME=/opt/pipx PIPX_BIN_DIR=/usr/local/bin
RUN pipx install pre-commit && pipx install ruff && pipx install platformio

# gitleaks, for the Claude Code guard (.claude/hooks/guard.py); pre-commit brings its own.
RUN case "${TARGETARCH}" in amd64) arch=x64 ;; arm64) arch=arm64 ;; *) exit 1 ;; esac \
    && base="https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}" \
    && tarball="gitleaks_${GITLEAKS_VERSION}_linux_${arch}.tar.gz" \
    && cd /tmp \
    && curl -fsSLO "${base}/${tarball}" \
    && curl -fsSL "${base}/gitleaks_${GITLEAKS_VERSION}_checksums.txt" | grep " ${tarball}\$" | sha256sum -c - \
    && tar -xzf "${tarball}" -C /usr/local/bin gitleaks \
    && rm "${tarball}"

# Non-root user `ubuntu` (uid 1000, from the base image); sudo for rosdep installs.
# Access to /dev/input comes from a udev rule in the WSL distro (docs/dev-setup.md).
RUN echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu \
    && chmod 0440 /etc/sudoers.d/ubuntu
USER ubuntu
RUN rosdep update --rosdistro jazzy \
    && echo "source /opt/ros/jazzy/setup.bash" >> /home/ubuntu/.bashrc
WORKDIR /home/ubuntu
