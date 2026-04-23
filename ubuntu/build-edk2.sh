#!/bin/sh
# Copyright (c) Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause-Clear

# ============================================================================
# Minimal edk2 ABL build script for Ubuntu (gen5 defaults)
# Includes:
#   - Optional patch application (DNM QcomModulePkg Keymaster patch)
#   - Signing step using Qualcomm sectools.
#
# Final outputs under ./out/:
#   - abl-unsigned.elf (raw build result)
#   - abl.elf          (signed image)
# ============================================================================

# ---------------------------------------------------------------------------
# Fixed configuration: always build for gen5
# ---------------------------------------------------------------------------

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
WORKSPACE=$(dirname "$(dirname "$SCRIPT_DIR")")

# edk2 source directory (Yocto: bootable/bootloader/edk2)
EDK2_DIR="${WORKSPACE}/bootable/bootloader/edk2"

# Build/output directories
BUILD_DIR="${EDK2_DIR}/out"
OUTPUT_DIR="${WORKSPACE}/out"
UNSIGNED_ABL="${OUTPUT_DIR}/abl-unsigned.elf"
SIGNED_ABL="${OUTPUT_DIR}/abl.elf"

# Always build for aarch64
TARGET_ARCHITECTURE="aarch64"

# Use serial build as in Yocto (PARALLEL_MAKE = "-j 1")
JOBS=1

# Path to DNM patch (from edk2_git.bbappend for gen5)
PATCH_PATH="${WORKSPACE}/layers/meta-qti-auto-kernel/recipes-kernel/edk2/files/0001-DNM-QcomModulePkg-Disable-Keymaster-Loading-for-SA87.patch"

# ---------------------------------------------------------------------------
# Simple logging
# ---------------------------------------------------------------------------

log() {
    echo "[build-edk2] $*" >&2
}

# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------

if [ ! -d "$EDK2_DIR" ]; then
    echo "ERROR: EDK2_DIR does not exist: $EDK2_DIR" >&2
    exit 1
fi

if [ ! -f "${EDK2_DIR}/makefile" ] && [ ! -f "${EDK2_DIR}/Makefile" ]; then
    echo "ERROR: edk2 makefile not found in: ${EDK2_DIR}" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Toolchain setup (clang)
# ---------------------------------------------------------------------------

CLANG_BIN=$(command -v clang || true)
CLANGXX_BIN=$(command -v clang++ || true)

if [ -z "$CLANG_BIN" ] || [ -z "$CLANGXX_BIN" ]; then
    echo "ERROR: clang/clang++ not found in PATH. Install with:" >&2
    echo "       sudo apt-get install -y clang" >&2
    exit 1
fi

export BUILD_CC="$CLANG_BIN"
export BUILD_CXX="$CLANGXX_BIN"

CLANG_BIN_DIR=$(dirname "$CLANG_BIN")


# ---------------------------------------------------------------------------
# Fixed build-time options (gen5 defaults from Yocto recipes)
# ---------------------------------------------------------------------------

# Effective values for gen5 in the Yocto edk2 recipes
EARLY_ETH=1
HIBERNATION=0
PVM_SKIP_DTBO=1
DISABLE_NONBOOTDEVICE_ENABLED=0
LOAD_KM_SET_ROT=1
SCMI_UPDATES_NEEDED=1
VERIFIED_BOOT_ENABLED=0
VERIFIED_BOOT_2=0

# goldcore-boot behavior (always enabled for this simplified gen5 build)
export LINUX_BOOT_CPU_SELECTION_ENABLED=1
export TARGET_LINUX_BOOT_CPU_ID=7

# ---------------------------------------------------------------------------
# EXTRA_OEMAKE equivalent (gen5 only)
# ---------------------------------------------------------------------------

EXTRA_MAKE_ARGS="\
 CLANG_BIN=${CLANG_BIN_DIR}/ \
 CLANG_PREFIX=${CLANG_BIN_DIR}/${TARGET_ARCHITECTURE}-linux-gnu- \
 TARGET_ARCHITECTURE=${TARGET_ARCHITECTURE} \
 BUILDDIR=${EDK2_DIR} \
 BOOTLOADER_OUT=${BUILD_DIR} \
 ENABLE_LE_VARIANT=true \
 HIBERNATION_SUPPORT=${HIBERNATION} \
 VERIFIED_BOOT_LE=0 \
 VERITY_LE=0 \
 FORCE_NO_PIE=1 \
 LOAD_KM_AND_SET_ROT=${LOAD_KM_SET_ROT} \
 INIT_BIN_LE=\"/sbin/init\" \
 EDK_TOOLS_PATH=${EDK2_DIR}/BaseTools \
 EARLY_ETH_ENABLED=${EARLY_ETH} \
 EARLY_ETH_AS_DLKM=1 \
 UBSAN_UEFI_GCC_FLAG_ALIGNMENT=-Wno-misleading-indentation \
 SUPPORT_DISABLE_NON_BOOTDEVICE=${DISABLE_NONBOOTDEVICE_ENABLED} \
 TARGET_BOARD_TYPE_AUTO=1 \
 SCMI_UPDATES_NEEDED=${SCMI_UPDATES_NEEDED} \
 PVM_SKIP_DTBO=${PVM_SKIP_DTBO} \
 VERIFIED_BOOT_ENABLED=${VERIFIED_BOOT_ENABLED} \
 VERIFIED_BOOT_2=${VERIFIED_BOOT_2} \
 SUPPORT_AB_BOOT_LXC=1 \
 ENABLE_LV_ATOMIC_AB=1 \
 ENABLE_SAIL_FLASHING=1 \
 ENABLE_SAIL_BOOT=1 \
 BOOTIMAGE_LOAD_VERIFY_IN_PARALLEL=1 \
 LOAD_TWO_KM_TAS=1 \
 SIGNED_KERNEL=1 \
 USER_BUILD_VARIANT=0 \
 DEVICE_STATUS=DEFAULT_UNLOCK=true \
"

# ---------------------------------------------------------------------------
# Try applying DNM patch before compile
# ---------------------------------------------------------------------------

if [ -f "$PATCH_PATH" ]; then
    log "Trying to apply patch: ${PATCH_PATH}"
    OLD_DIR=$(pwd)
    cd "${EDK2_DIR}" || exit 1
    if patch --dry-run -p1 < "$PATCH_PATH" >/dev/null 2>&1; then
        if patch -p1 < "$PATCH_PATH" >/dev/null 2>&1; then
            log "Patch applied successfully."
        else
            log "Patch application failed (non-critical). Continue without patch."
        fi
    else
        log "Patch does not apply cleanly (maybe already applied). Continue without patch."
    fi
    cd "$OLD_DIR" || exit 1
else
    log "Patch file not found at: ${PATCH_PATH}"
    log "Skipping patch step."
fi

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

log "EDK2_DIR    = ${EDK2_DIR}"
log "BUILD_DIR   = ${BUILD_DIR}"
log "OUTPUT_DIR  = ${OUTPUT_DIR}"
log "TARGET_ARCH = ${TARGET_ARCHITECTURE}"
log "clang       = ${CLANG_BIN}"
log "EXTRA_MAKE_ARGS = ${EXTRA_MAKE_ARGS}"

mkdir -p "${BUILD_DIR}"
mkdir -p "${OUTPUT_DIR}"

OLD_DIR=$(pwd)
cd "${EDK2_DIR}" || exit 1
log "Running make (serial, -j ${JOBS}) ..."
# EXTRA_MAKE_ARGS is a flat string; let sh split it into arguments
# shellcheck disable=SC2086
make -f makefile -j "${JOBS}" all ${EXTRA_MAKE_ARGS}
cd "$OLD_DIR" || exit 1

# ---------------------------------------------------------------------------
# Locate abl.elf (similar to Yocto do_deploy)
# ---------------------------------------------------------------------------

log "Locating abl.elf ..."

CANDIDATE1="${EDK2_DIR}/../abl.elf"
CANDIDATE2="${BUILD_DIR}/abl.elf"

ABL_SRC=""
if [ -f "$CANDIDATE1" ]; then
    ABL_SRC="$CANDIDATE1"
elif [ -f "$CANDIDATE2" ]; then
    ABL_SRC="$CANDIDATE2"
fi

if [ -z "$ABL_SRC" ]; then
    echo "ERROR: abl.elf not found after build." >&2
    echo "Checked:" >&2
    echo "  $CANDIDATE1" >&2
    echo "  $CANDIDATE2" >&2
    exit 1
fi

cp -f "$ABL_SRC" "$UNSIGNED_ABL"
log "Unsigned abl saved as: ${UNSIGNED_ABL}"

# ---------------------------------------------------------------------------
# Signing using Qualcomm sectools
# ---------------------------------------------------------------------------

SECTOOLS_DIR="${WORKSPACE}/vendor/qcom/proprietary/sectools/Linux_aarch64"
SECTOOLS_BIN="${SECTOOLS_DIR}/sectools"
SECTOOLS_LIB_DIR="${SECTOOLS_DIR}/lib"
SECTOOLS_SECURITY_PROFILE="${WORKSPACE}/security/securemsm/security_profiles/nord_tz_security_profile.xml"
HOST_CRYPT1="/usr/lib/aarch64-linux-gnu/libcrypt.so.1"
LOCAL_CRYPT2="${SECTOOLS_LIB_DIR}/libcrypt.so.2"

if [ ! -x "$SECTOOLS_BIN" ]; then
    log "sectools binary not found or not executable at:"
    log "  ${SECTOOLS_BIN}"
    log "Skipping signing step."
    log "Final unsigned image: ${UNSIGNED_ABL}"
    exit 0
fi

if [ ! -f "$SECTOOLS_SECURITY_PROFILE" ]; then
    log "Security profile not found at:"
    log "  ${SECTOOLS_SECURITY_PROFILE}"
    log "Skipping signing step."
    log "Final unsigned image: ${UNSIGNED_ABL}"
    exit 0
fi

mkdir -p "${SECTOOLS_LIB_DIR}"

if ldconfig -p 2>/dev/null | grep -q "libcrypt.so.2"; then
    log "System has libcrypt.so.2; no local symlink needed."
else
    if [ -e "${LOCAL_CRYPT2}" ]; then
        log "Local libcrypt.so.2 already exists at ${LOCAL_CRYPT2}; reuse it."
    elif [ -e "${HOST_CRYPT1}" ]; then
        log "Global libcrypt.so.2 not found, but ${HOST_CRYPT1} exists."
        log "Creating local symlink for sectools: ${LOCAL_CRYPT2} -> ${HOST_CRYPT1}"
        if ! ln -sf "${HOST_CRYPT1}" "${LOCAL_CRYPT2}"; then
            log "Failed to create local libcrypt.so.2 symlink (non-fatal)."
        fi
    else
        log "Neither system libcrypt.so.2 nor ${HOST_CRYPT1} found."
        log "sectools may fail due to missing libcrypt.so.2."
    fi
fi

log "Signing abl-unsigned.elf using sectools ..."

SIGNED_OUT_DIR="${OUTPUT_DIR}/boot"
SIGNED_OUT_PATH="${SIGNED_OUT_DIR}/abl.elf"

mkdir -p "${SIGNED_OUT_DIR}"

# Make sure sectools can see the local lib directory first
export LD_LIBRARY_PATH="${SECTOOLS_LIB_DIR}:${LD_LIBRARY_PATH:-}"

"$SECTOOLS_BIN" secure-image "${UNSIGNED_ABL}" \
    --image-id ABL \
    --security-profile "${SECTOOLS_SECURITY_PROFILE}" \
    --sign \
    --signing-mode TEST \
    --outfile "${SIGNED_OUT_PATH}"

cp -f "${SIGNED_OUT_PATH}" "${SIGNED_ABL}"

log "Signing completed."
log "Unsigned image: ${UNSIGNED_ABL}"
log "Signed image:   ${SIGNED_ABL}"
