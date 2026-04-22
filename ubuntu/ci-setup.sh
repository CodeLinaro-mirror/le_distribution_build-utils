#!/bin/bash
# Copyright (c) Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause-Clear
# ci-setup.sh
#
# One-time setup script for CI build servers (bare metal or VM).
# Run this script once on each new CI server as root (or via sudo).
#
# Usage:
#   sudo bash build-utils/ubuntu/ci-setup.sh [BUILD_USER]
#
# Arguments:
#   BUILD_USER  The OS user account that will run the build (default: current user)
#
# This script:
#   1. Installs all required system packages
#   2. Configures /etc/subuid and /etc/subgid for the build user
#   3. Enables unprivileged user namespaces (persistent across reboots)
#   4. Verifies newuidmap/newgidmap have the setuid bit
#
# After running this script, the build user can run build.py without sudo.

set -e

BUILD_USER="${1:-$(logname 2>/dev/null || echo $SUDO_USER)}"

if [ -z "$BUILD_USER" ]; then
    echo "ERROR: Could not determine build user. Pass it as an argument: sudo bash ci-setup.sh <username>"
    exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: This script must be run as root (sudo bash ci-setup.sh)"
    exit 1
fi

echo "=== CI Build Server Setup ==="
echo "Build user: $BUILD_USER"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Install required packages
# ---------------------------------------------------------------------------
echo "[1/4] Installing required packages..."
apt-get update -qq
apt-get install -y \
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
    util-linux \
    git \
    wget \
    device-tree-compiler \
    curl

# Install Python packages
pip3 install --quiet gitpython requests 2>/dev/null || true

echo "    [OK] Packages installed."

# ---------------------------------------------------------------------------
# Step 2: Configure /etc/subuid and /etc/subgid
# ---------------------------------------------------------------------------
echo "[2/4] Configuring subuid/subgid for user '$BUILD_USER'..."

if grep -q "^${BUILD_USER}:" /etc/subuid 2>/dev/null; then
    echo "    [OK] /etc/subuid already configured for $BUILD_USER."
else
    usermod --add-subuids 100000-165535 "$BUILD_USER"
    echo "    [OK] Added subuid range 100000-165535 for $BUILD_USER."
fi

if grep -q "^${BUILD_USER}:" /etc/subgid 2>/dev/null; then
    echo "    [OK] /etc/subgid already configured for $BUILD_USER."
else
    usermod --add-subgids 100000-165535 "$BUILD_USER"
    echo "    [OK] Added subgid range 100000-165535 for $BUILD_USER."
fi

# ---------------------------------------------------------------------------
# Step 3: Enable unprivileged user namespaces (persistent)
# ---------------------------------------------------------------------------
echo "[3/4] Enabling unprivileged user namespaces..."
# Note: The sbuild base tarball (noble.tar.gz) is created automatically by
# build.py on first use and stored in <workspace>/.cache/sbuild/ via
# XDG_CACHE_HOME, keeping it project-local and out of ~/.cache.

SYSCTL_CONF="/etc/sysctl.d/99-userns.conf"
if [ -f "$SYSCTL_CONF" ] && grep -q "unprivileged_userns_clone=1" "$SYSCTL_CONF"; then
    echo "    [OK] Already configured in $SYSCTL_CONF."
else
    echo 'kernel.unprivileged_userns_clone=1' > "$SYSCTL_CONF"
    echo "    [OK] Written to $SYSCTL_CONF."
fi

# Apply immediately (don't fail if the key doesn't exist on this kernel)
sysctl -w kernel.unprivileged_userns_clone=1 2>/dev/null || true

CURRENT_VAL=$(cat /proc/sys/kernel/unprivileged_userns_clone 2>/dev/null || echo "N/A")
if [ "$CURRENT_VAL" = "1" ]; then
    echo "    [OK] unprivileged_userns_clone = 1"
else
    echo "    [WARN] unprivileged_userns_clone = $CURRENT_VAL"
    echo "           This kernel may not support this sysctl (Ubuntu 24.04+ allows"
    echo "           user namespaces unconditionally). Proceeding anyway."
fi

# ---------------------------------------------------------------------------
# Step 4: Ensure newuidmap/newgidmap have the setuid bit
# ---------------------------------------------------------------------------
echo "[4/4] Verifying newuidmap/newgidmap setuid bit..."

NEWUIDMAP=$(which newuidmap 2>/dev/null || true)
NEWGIDMAP=$(which newgidmap 2>/dev/null || true)

if [ -z "$NEWUIDMAP" ] || [ -z "$NEWGIDMAP" ]; then
    echo "    [ERROR] newuidmap or newgidmap not found. Install the 'uidmap' package."
    exit 1
fi

# Check and set setuid bit if missing
if [ ! -u "$NEWUIDMAP" ]; then
    chmod u+s "$NEWUIDMAP"
    echo "    [OK] Set setuid bit on $NEWUIDMAP"
else
    echo "    [OK] $NEWUIDMAP already has setuid bit."
fi

if [ ! -u "$NEWGIDMAP" ]; then
    chmod u+s "$NEWGIDMAP"
    echo "    [OK] Set setuid bit on $NEWGIDMAP"
else
    echo "    [OK] $NEWGIDMAP already has setuid bit."
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Setup Complete ==="
echo ""
echo "Verification:"
echo "  Build user  : $BUILD_USER"
echo "  subuid      : $(grep "^${BUILD_USER}:" /etc/subuid || echo 'NOT FOUND')"
echo "  subgid      : $(grep "^${BUILD_USER}:" /etc/subgid || echo 'NOT FOUND')"
echo "  userns      : $(cat /proc/sys/kernel/unprivileged_userns_clone 2>/dev/null || echo 'N/A')"
echo "  newuidmap   : $NEWUIDMAP (setuid: $([ -u "$NEWUIDMAP" ] && echo yes || echo no))"
echo "  newgidmap   : $NEWGIDMAP (setuid: $([ -u "$NEWGIDMAP" ] && echo yes || echo no))"
echo ""
echo "The user '$BUILD_USER' can now run build.py without sudo:"
echo "  python3 build-utils/ubuntu/build.py --workspace /path/to/workspace --gen-debians --pack-image"
