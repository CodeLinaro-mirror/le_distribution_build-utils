#!/bin/bash
# Copyright (c) Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause-Clear
#
# fetch-cntvct-log.sh
#
# Dynamically fetches the cntvct-log source files from their upstream
# CodeLinaro repo at build time, instead of keeping them vendored/committed
# under layers/meta-qti-automotive/recipes-core/cntvct-log/. This keeps the
# upstream-derived files out of the gated repo while it's blocked from
# merging.
#
# Only cntvct.c and cntvct@.service are fetched dynamically. README.md is
# already committed in place and is left alone, as is the debian/ packaging
# directory (control, rules, changelog, copyright, source/format), which is
# not upstream.
#
# Usage:
#   bash build-utils/ubuntu/fetch-cntvct-log.sh
#
# Intended to be run as part of the build (e.g. from build.py, the same way
# camx_copy_code.sh is invoked) before build_deb.py scans SOURCES_DIRS, so
# that cntvct.c / cntvct@.service exist on disk when debian/rules runs.
#
# Re-running this script re-fetches upstream and overwrites cntvct.c and
# cntvct@.service in place. It never touches README.md or debian/.

set -e

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
WORKSPACE=$(dirname "$(dirname "$SCRIPT_DIR")")

UPSTREAM_RAW_BASE="https://git.codelinaro.org/clo/le/platform/external/boot-time-analysis-tools/-/raw"
UPSTREAM_REV="9943935af12c09fb93228a087748d87151c3a9b5"
UPSTREAM_SUBDIR="cntvct-log"

DEST_DIR="${WORKSPACE}/layers/meta-qti-automotive/recipes-core/cntvct-log"

CNTVCT_C_URL="${UPSTREAM_RAW_BASE}/${UPSTREAM_REV}/${UPSTREAM_SUBDIR}/cntvct.c"
CNTVCT_SERVICE_URL="${UPSTREAM_RAW_BASE}/${UPSTREAM_REV}/${UPSTREAM_SUBDIR}/usr/lib/systemd/system/cntvct@.service"

echo "=== Fetching cntvct-log from upstream ==="
echo "Rev: $UPSTREAM_REV"
echo

mkdir -p "$DEST_DIR"

echo "=== Refreshing dynamically-fetched files in $DEST_DIR ==="
wget -q -O "$DEST_DIR/cntvct.c" "$CNTVCT_C_URL"
wget -q -O "$DEST_DIR/cntvct@.service" "$CNTVCT_SERVICE_URL"

echo "Done. Refreshed files:"
echo "  $DEST_DIR/cntvct.c"
echo "  $DEST_DIR/cntvct@.service"

echo
echo "Left untouched (already committed / not upstream-fetched):"
echo "  $DEST_DIR/README.md"
echo "  $DEST_DIR/debian/"
