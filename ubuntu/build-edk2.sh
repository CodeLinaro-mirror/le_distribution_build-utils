#!/usr/bin/env bash
# Copyright (c) Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause-Clear
set -euo pipefail

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

# edk2 source directory (Yocto: bootable/bootloader/edk2)
EDK2_DIR="${EDK2_DIR:-$(pwd)/bootable/bootloader/edk2}"

# Build/output directories
BUILD_DIR="${BUILD_DIR:-${EDK2_DIR}/out}"
OUTPUT_DIR="${OUTPUT_DIR:-$(pwd)/out}"
UNSIGNED_ABL="${UNSIGNED_ABL:-${OUTPUT_DIR}/abl-unsigned.elf}"
SIGNED_ABL="${SIGNED_ABL:-${OUTPUT_DIR}/abl.elf}"

# Always build for aarch64
TARGET_ARCHITECTURE="aarch64"

# Use serial build as in Yocto (PARALLEL_MAKE = "-j 1")
JOBS=1

# Path to DNM patch (from edk2_git.bbappend for gen5)
PATCH_PATH="${PATCH_PATH:-$(pwd)/layers/meta-qti-auto-kernel/recipes-kernel/edk2/files/0001-DNM-QcomModulePkg-Disable-Keymaster-Loading-for-SA87.patch}"

# ---------------------------------------------------------------------------
# Simple logging
# ---------------------------------------------------------------------------

log() {
    echo "[build-edk2] $*" >&2
}

# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------

if [[ ! -d "$EDK2_DIR" ]]; then
    echo "ERROR: EDK2_DIR does not exist: $EDK2_DIR" >&2
    exit 1
fi

if [[ ! -f "${EDK2_DIR}/makefile" && ! -f "${EDK2_DIR}/Makefile" ]]; then
    echo "ERROR: edk2 makefile not found in: ${EDK2_DIR}" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Toolchain setup (clang)
# ---------------------------------------------------------------------------

CLANG_BIN="$(command -v clang || true)"
CLANGXX_BIN="$(command -v clang++ || true)"

if [[ -z "$CLANG_BIN" || -z "$CLANGXX_BIN" ]]; then
    echo "ERROR: clang/clang++ not found in PATH. Install with:" >&2
    echo "       sudo apt-get install -y clang" >&2
    exit 1
fi

export BUILD_CC="$CLANG_BIN"
export BUILD_CXX="$CLANGXX_BIN"

CLANG_BIN_DIR="$(dirname "$CLANG_BIN")"

# Do not force any absolute-path -fuse-ld here
export LD="${LD:-}"
export LDFLAGS="$(echo "${LDFLAGS:-}" | sed 's/-fuse-ld=[^ ]*//g')"

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
VERIFIED_BOOT_ENABLED=1
VERIFIED_BOOT_2=1

# goldcore-boot behavior (always enabled for this simplified gen5 build)
export LINUX_BOOT_CPU_SELECTION_ENABLED=1
export TARGET_LINUX_BOOT_CPU_ID=7

# ---------------------------------------------------------------------------
# EXTRA_OEMAKE equivalent (gen5 only)
# ---------------------------------------------------------------------------

EXTRA_MAKE_ARGS=(
    "CLANG_BIN=${CLANG_BIN_DIR}/"
    "CLANG_PREFIX=${CLANG_BIN_DIR}/${TARGET_ARCHITECTURE}-linux-gnu-"
    "TARGET_ARCHITECTURE=${TARGET_ARCHITECTURE}"
    "BUILDDIR=${EDK2_DIR}"
    "BOOTLOADER_OUT=${BUILD_DIR}"
    "ENABLE_LE_VARIANT=true"
    "HIBERNATION_SUPPORT=${HIBERNATION}"
    "VERIFIED_BOOT_LE=0"
    "VERITY_LE=0"
    "FORCE_NO_PIE=1"
    "LOAD_KM_AND_SET_ROT=${LOAD_KM_SET_ROT}"
    "INIT_BIN_LE=\"/sbin/init\""
    "EDK_TOOLS_PATH=${EDK2_DIR}/BaseTools"
    "EARLY_ETH_ENABLED=${EARLY_ETH}"
    "EARLY_ETH_AS_DLKM=1"
    "UBSAN_UEFI_GCC_FLAG_ALIGNMENT=-Wno-misleading-indentation"
    "SUPPORT_DISABLE_NON_BOOTDEVICE=${DISABLE_NONBOOTDEVICE_ENABLED}"
    "TARGET_BOARD_TYPE_AUTO=1"
    "SCMI_UPDATES_NEEDED=${SCMI_UPDATES_NEEDED}"
    "PVM_SKIP_DTBO=${PVM_SKIP_DTBO}"
    "VERIFIED_BOOT_ENABLED=${VERIFIED_BOOT_ENABLED}"
    "VERIFIED_BOOT_2=${VERIFIED_BOOT_2}"
    # gen5 specific flags from EXTRA_OEMAKE:append:gen5
    "SUPPORT_AB_BOOT_LXC=1"
    "ENABLE_LV_ATOMIC_AB=1"
    "ENABLE_SAIL_FLASHING=1"
    "ENABLE_SAIL_BOOT=1"
    "BOOTIMAGE_LOAD_VERIFY_IN_PARALLEL=1"
    "LOAD_TWO_KM_TAS=1"
    "SIGNED_KERNEL=1"
    "USER_BUILD_VARIANT=0"
    "DEVICE_STATUS=DEFAULT_UNLOCK=true"
)

# ---------------------------------------------------------------------------
# Try applying DNM patch before compile
# ---------------------------------------------------------------------------

if [[ -f "$PATCH_PATH" ]]; then
    log "Trying to apply patch: ${PATCH_PATH}"
    pushd "${EDK2_DIR}" >/dev/null
    # Try dry-run first to detect if applicable. If not, do not block build.
    if patch --dry-run -p1 < "$PATCH_PATH" >/dev/null 2>&1; then
        if patch -p1 < "$PATCH_PATH" >/dev/null 2>&1; then
            log "Patch applied successfully."
        else
            log "Patch application failed (non-critical). Continue without patch."
        fi
    else
        log "Patch does not apply cleanly (maybe already applied). Continue without patch."
    fi
    popd >/dev/null
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
log "EXTRA_MAKE_ARGS = "${EXTRA_MAKE_ARGS[@]}""

mkdir -p "${BUILD_DIR}"
mkdir -p "${OUTPUT_DIR}"

pushd "${EDK2_DIR}" >/dev/null
log "Running make (serial, -j ${JOBS}) ..."
make -f makefile -j "${JOBS}" all "${EXTRA_MAKE_ARGS[@]}"
popd >/dev/null

# ---------------------------------------------------------------------------
# Locate abl.elf (similar to Yocto do_deploy)
# ---------------------------------------------------------------------------

log "Locating abl.elf ..."

CANDIDATE1="${EDK2_DIR}/../abl.elf"
CANDIDATE2="${BUILD_DIR}/abl.elf"

ABL_SRC=""
if [[ -f "$CANDIDATE1" ]]; then
    ABL_SRC="$CANDIDATE1"
elif [[ -f "$CANDIDATE2" ]]; then
    ABL_SRC="$CANDIDATE2"
fi

if [[ -z "$ABL_SRC" ]]; then
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

# sectools path from your tree:
#   vendor/qcom/proprietary/sectools/Linux/sectools
SECTOOLS_BIN="${SECTOOLS_BIN:-$(pwd)/vendor/qcom/proprietary/sectools/Linux_aarch64/sectools}"

# Security profile from your tree:
#   security/securemsm/security_profiles/nord_tz_security_profile.xml
SECTOOLS_SECURITY_PROFILE="${SECTOOLS_SECURITY_PROFILE:-$(pwd)/security/securemsm/security_profiles/nord_tz_security_profile.xml}"

if [[ ! -x "$SECTOOLS_BIN" ]]; then
    log "sectools binary not found or not executable at:"
    log "  ${SECTOOLS_BIN}"
    log "Skipping signing step."
    log "Final unsigned image: ${UNSIGNED_ABL}"
    exit 0
fi

if [[ ! -f "$SECTOOLS_SECURITY_PROFILE" ]]; then
    log "Security profile not found at:"
    log "  ${SECTOOLS_SECURITY_PROFILE}"
    log "Skipping signing step."
    log "Final unsigned image: ${UNSIGNED_ABL}"
    exit 0
fi

log "Signing abl-unsigned.elf using sectools ..."

SIGNED_OUT_DIR="${OUTPUT_DIR}/boot"
SIGNED_OUT_PATH="${SIGNED_OUT_DIR}/abl.elf"

mkdir -p "${SIGNED_OUT_DIR}"

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
