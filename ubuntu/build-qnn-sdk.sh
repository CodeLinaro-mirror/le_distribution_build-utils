#!/bin/sh
# Copyright (c) Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause-Clear

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
WORKSPACE=$(dirname "$(dirname "$SCRIPT_DIR")")


create_qnn_sdk_package() {
    QNN_URL="https://softwarecenter.qualcomm.com/api/download/software/sdks/Qualcomm_AI_Runtime_Community/All/2.46.0.260424/v2.46.0.260424.zip"
    QNN_ZIP="${SCRIPT_DIR}/qnn-sdk.zip"
    QNN_SDK_ROOT="qairt/2.46.0.260424"
    rm -rf ${WORKSPACE}/sources/quic-qrb-ros/qnn-sdk
    wget -c --timeout=10 -O "$QNN_ZIP.tmp" "$QNN_URL" || {
      echo "ERROR: qnn-sdk download failed"
      rm -rf "$QNN_ZIP.tmp"
      exit 1
    }
    mv "$QNN_ZIP.tmp" "$QNN_ZIP"
    mkdir -p ${WORKSPACE}/sources/quic-qrb-ros/qnn-sdk/usr/lib/aarch64-oe-linux-gcc11.2
    unzip -j "$QNN_ZIP" "${QNN_SDK_ROOT}/lib/aarch64-oe-linux-gcc11.2/*.so" -d ${WORKSPACE}/sources/quic-qrb-ros/qnn-sdk/usr/lib/
    chmod 0644 ${WORKSPACE}/sources/quic-qrb-ros/qnn-sdk/usr/lib/*.so
    mkdir -p ${WORKSPACE}/sources/quic-qrb-ros/qnn-sdk/usr/lib/rfsa/adsp/hexagon-v81
    unzip -j "$QNN_ZIP" "${QNN_SDK_ROOT}/lib/hexagon-v81/unsigned/*" -d ${WORKSPACE}/sources/quic-qrb-ros/qnn-sdk/usr/lib/rfsa/adsp/hexagon-v81/
    chmod 0644 ${WORKSPACE}/sources/quic-qrb-ros/qnn-sdk/usr/lib/rfsa/adsp/hexagon-v81/*
    mkdir -p ${WORKSPACE}/sources/quic-qrb-ros/qnn-sdk/usr/include
    unzip -Z1 "$QNN_ZIP" | grep "^${QNN_SDK_ROOT}/include/QNN/.*\.h$" | while read f; do
        [ -z "$f" ] && continue
        newpath=${f#${QNN_SDK_ROOT}/include/QNN}
        mkdir -p ${WORKSPACE}/sources/quic-qrb-ros/qnn-sdk/usr/include/$(dirname "$newpath")
	chmod 0755 ${WORKSPACE}/sources/quic-qrb-ros/qnn-sdk/usr/include/$(dirname "$newpath")
        unzip -p "$QNN_ZIP" "$f" > ${WORKSPACE}/sources/quic-qrb-ros/qnn-sdk/usr/include/$newpath
	chmod 0644 ${WORKSPACE}/sources/quic-qrb-ros/qnn-sdk/usr/include/$newpath
    done
    rm -rf "${QNN_ZIP}"
    mkdir -p ${WORKSPACE}/sources/quic-qrb-ros/qnn-sdk/DEBIAN
    touch ${WORKSPACE}/sources/quic-qrb-ros/qnn-sdk/DEBIAN/control
    chmod 0755 ${WORKSPACE}/sources/quic-qrb-ros/qnn-sdk/DEBIAN
    chmod 0755 ${WORKSPACE}/sources/quic-qrb-ros/qnn-sdk/DEBIAN/control
    cat <<EOF > ${WORKSPACE}/sources/quic-qrb-ros/qnn-sdk/DEBIAN/control
Package: qnn-sdk
Section: base
Version: 2.46.0
Priority: optional
Architecture: all
Maintainer: xrao <xrao@qti.qualcomm.com>
Homepage: https://softwarecenter.qualcomm.com
Description: qnn sdk code package deployed without compilation.
EOF

    cd ${WORKSPACE}/sources/quic-qrb-ros
    fakeroot dpkg-deb --build qnn-sdk
}

# reoragnize qnn-sdk packages
reorganize_qnn_sdk_deb() {
    rm -rf ${WORKSPACE}/debian_packages/oss/qnn-sdk/
    mkdir -p ${WORKSPACE}/debian_packages/oss/qnn-sdk/
    cp ${WORKSPACE}/sources/quic-qrb-ros/qnn-sdk.deb ${WORKSPACE}/debian_packages/oss/qnn-sdk/
}

create_qnn_sdk_package
reorganize_qnn_sdk_deb
