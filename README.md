qcom-build-utils
--------

Overview
--------
build.py is a Python-based build orchestration script designed for end-to-end management of kernel building,
packaging, and system image creation in an embedded Linux or Debian-based environment.
It supports kernel compilation, Debian package generation, and packing custom system images using multiple
configurable options via command-line arguments.

No root / sudo required: the script runs entirely as a normal user. The rootfs is built inside a Linux
user namespace via mmdebstrap --mode=unshare, and Debian packages are built via sbuild --chroot-mode=unshare.

Branches
--------
main: Primary development branch. Contributors should develop submissions based on this branch, and submit pull requests to this branch.

Features
--------
- Build Linux kernel with custom sources.
- Generate Debian binary packages.
- Install and organize Debian packages for the root file system.
- Pack a system.img (system image) including the generated packages.
- Image and build flavor configuration (server/desktop, base/qcom).
- Automated workspace cleanup.

Prerequisites
-------------
The following packages must be installed on the build host before running the script.
Run the one-time setup command below (Ubuntu/Debian):

  sudo apt-get install -y \
      mmdebstrap \
      uidmap \
      sbuild \
      mtools \
      e2fsprogs \
      dosfstools \
      dpkg-dev \
      python3 \
      python3-pip \
      python3-git \
      python3-requests \
      uuid-runtime \
      util-linux

Then install the required Python packages:

  pip3 install gitpython requests

User Namespace Configuration (one-time, per user)
--------------------------------------------------
mmdebstrap --mode=unshare and sbuild --chroot-mode=unshare require Linux user namespace support.
Perform the following one-time setup for each developer account:

1. Verify user namespace support is enabled:

     cat /proc/sys/kernel/unprivileged_userns_clone
     # Must output: 1
     # If it outputs 0, run: sudo sysctl -w kernel.unprivileged_userns_clone=1
     # To make it permanent: echo 'kernel.unprivileged_userns_clone=1' | sudo tee /etc/sysctl.d/99-userns.conf

2. Verify /etc/subuid and /etc/subgid entries exist for your user:

     grep $(whoami) /etc/subuid   # e.g. kmeng:100000:65536
     grep $(whoami) /etc/subgid   # e.g. kmeng:100000:65536

     # If missing, add them:
     sudo usermod --add-subuids 100000-165535 $(whoami)
     sudo usermod --add-subgids 100000-165535 $(whoami)

3. Verify newuidmap / newgidmap are installed and have the setuid bit:

     ls -la $(which newuidmap)    # Should show -rwsr-xr-x
     ls -la $(which newgidmap)    # Should show -rwsr-xr-x

     # If missing the setuid bit:
     sudo chmod u+s $(which newuidmap) $(which newgidmap)

Once the above is configured, no further setup is needed for subsequent builds.

CI / Automation Environment Setup
----------------------------------
For CI servers (bare metal or VM) that run builds automatically, use the provided setup script
to configure each server in one step:

  sudo bash build-utils/ubuntu/ci-setup.sh [BUILD_USER]

  # Example: configure for the 'jenkins' CI user
  sudo bash build-utils/ubuntu/ci-setup.sh jenkins

The script performs all four steps above automatically (package install, subuid/subgid,
unprivileged_userns_clone, newuidmap/newgidmap setuid) and prints a verification summary.
It is idempotent — safe to run multiple times on the same server.

For Ansible/Puppet/Chef deployments, the script can be called as a task:

  - name: Configure CI build server for no-sudo builds
    command: bash /path/to/build-utils/ubuntu/ci-setup.sh {{ ci_build_user }}
    become: yes

NOTE — Docker-based CI environments:
  mmdebstrap --mode=unshare requires Linux user namespace support, which Docker containers
  restrict by default. If your CI runs inside Docker containers, one of the following is needed:
    a) Run the container with --privileged (simplest, but reduces isolation)
    b) Run with --security-opt seccomp=unconfined --security-opt apparmor=unconfined
       and mount /etc/subuid and /etc/subgid into the container
    c) Use a pre-configured Docker image that has user namespace support enabled
  Kubernetes pods require a privileged security context for the same reason.

Usage
-----
Run the script as a normal user (no sudo):

  python3 build-utils/ubuntu/build.py --workspace /absolute/path/to/workspace [options]

Example:
--------
  python3 build-utils/ubuntu/build.py \
      --workspace /local/mnt/workspace/user/project \
      --gen-debians \
      --pack-image

Arguments
---------

Argument                  Type    Default                                                                    Description
--workspace               string  required                                                                   Absolute path to the workspace directory.
--build-kernel            flag    False                                                                      Build the kernel.
--kernel-src-dir          string  <workspace>/kernel                                                        Directory containing kernel sources.
--kernel-dest-dir         string  <workspace>/debian_packages/oss                                           Output directory for built kernel .deb files.
--flavor                  string  server                                                                     Image flavor: server or desktop.
--debians-path            string  -                                                                          Directory with additional Debian packages to install.
--gen-debians             flag    False                                                                      Generate Debian binary packages.
--pack-image              flag    False                                                                      Pack a system.img with generated Debian packages.
--pack-variant            string  qcom                                                                       Pack variant: base or qcom.
--output-image-file       string  <workspace>/out/system.img                                                Path for output system image.
--package                 string  -                                                                          Name of a specific package to build.
--nocleanup               flag    False                                                                      Skip workspace cleanup after build.
--prepare-sources         flag    False                                                                      Prepare sources but do not build.
--no-abi-check            flag    False                                                                      Skip ABI compatibility check.
--apt-server-config       string  deb [arch=arm64 trusted=yes] http://ports.ubuntu.com/ubuntu-ports noble main restricted universe multiverse
                                                                                                             APT server configuration(s).
--build-full-image        flag    False                                                                      Full build: equivalent to --build-kernel --gen-debians --pack-image.

Deprecated:
-----------
Argument              Description
--chroot-name         No longer used (sbuild now uses --chroot-mode=unshare, no pre-configured schroot needed).
--skip-starter-image  Build starter image (deprecated).
--input-image-file    Input system image (deprecated).

Common Workflows
----------------
Generate Debian Packages only:

  python3 build-utils/ubuntu/build.py --workspace /path/to/workspace --gen-debians

Pack System Image only (downloads Ubuntu packages from the internet):

  python3 build-utils/ubuntu/build.py --workspace /path/to/workspace --pack-image

Generate Debian Packages and Pack System Image:

  python3 build-utils/ubuntu/build.py --workspace /path/to/workspace --gen-debians --pack-image

Full build (kernel + packages + image):

  python3 build-utils/ubuntu/build.py --workspace /path/to/workspace --build-full-image

Directory Structure
-------------------
Directory                            Purpose
<workspace>/kernel                   Kernel sources
<workspace>/system                   Source code for Debian packages (OSS)
<workspace>/vendor/qcom              Source code for Debian packages (Qualcomm)
<workspace>/debian_packages          Output directory for Debian packages
<workspace>/debian_packages/oss      Open-source Debian package output
<workspace>/debian_packages/prop     Proprietary Debian package output
<workspace>/debian_packages/temp     Temporary files for build process (build logs, rootfs tar, etc.)
<workspace>/build/mount              Temporary rootfs directory used by mmdebstrap (cleaned after build)
<workspace>/out                      Output directory (system.img, efi.bin, server.manifest)

Notes
-----
- No root required: All build steps run as a normal user via Linux user namespaces.
- Internet access: --pack-image downloads Ubuntu Noble packages from ports.ubuntu.com during the build.
- Interrupted builds: If a build is interrupted, the next run will automatically clean up any leftover
  rootfs_extracted directory before proceeding. No manual cleanup is needed in normal cases.
  If build/mount cannot be cleaned (files owned by subuid-mapped UIDs), run: sudo rm -rf <workspace>/build/mount
- Workspace cleanup: Controlled by --nocleanup flag. Without it, build/mount is removed after each build.

License
-------
qcom-build-utils is licensed under the BSD-3-clause-clear License. See LICENSE for the full license text.
