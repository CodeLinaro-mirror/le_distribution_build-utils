#!/bin/sh
# Copyright (c) Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause-Clear
set -x
PACKAGE_ONLY=false
BUILD_VARIANT=""
while getopts "pv:" opt; do
  case $opt in
    p) PACKAGE_ONLY=true ;;
    v) BUILD_VARIANT="$OPTARG" ;;
    \?) echo "Invalid option" ; exit 1 ;;
  esac
done

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
WORKSPACE=$(dirname "$(dirname "$SCRIPT_DIR")")
KERNEL_PLATFORM_DIR="${WORKSPACE}/kernel/kernel_platform"
# perf and debug builds use separate output directories so their artifacts
# don't collide when copied into the same CRM on the EC servers.
if [ "${BUILD_VARIANT}" = "perf" ]; then
    OUTPUT_DIR="${WORKSPACE}/out-perf"
else
    OUTPUT_DIR="${WORKSPACE}/out"
fi
apply_patch() {
    patch=$1
    if git apply --check "${patch}" > /dev/null 2>&1; then
        git apply "${patch}"
    fi
}
do_kernel_patch() {
    downstream_rt_patch_path="${WORKSPACE}/layers/meta-qti-realtime/recipes-kernel/linux/linux-qcom-custom-rt"
    downstream_qc_patch_path="${WORKSPACE}/layers/meta-qti-auto-kernel/recipes-kernel/linux/files"
    cd "${OUTPUT_DIR}"
    if [ ! -f "${OUTPUT_DIR}/patch-6.6.119-rt67.patch.gz" ]; then
        wget https://cdn.kernel.org/pub/linux/kernel/projects/rt/6.6/older/patch-6.6.119-rt67.patch.gz
        if [ "$(md5sum "patch-6.6.119-rt67.patch.gz" | awk '{print $1}')" != "e78f515f30aa9fb315f36ce38bcf7932" ]; then
            echo "Error: md5sum check error"
            exit 1
        fi
        gunzip -k patch-6.6.119-rt67.patch.gz
    fi
    cd "${KERNEL_PLATFORM_DIR}"/kernel
    # Apply upstream RT patch
    apply_patch "${OUTPUT_DIR}"/patch-6.6.119-rt67.patch
    # Apply downstream RT patches
    apply_patch ${downstream_rt_patch_path}/0001-arch-Kconfig-Add-RT-kernel-support.patch
    apply_patch ${downstream_rt_patch_path}/0001-QCLINUX-Disable-bcl-driver-config-for-RT-kernel.patch
    # Apply other downstream patches
    apply_patch ${downstream_qc_patch_path}/0001-QCLINUX-vfio-Disable-iommu_group_claim_dma_owner-tem.patch
    apply_patch ${downstream_qc_patch_path}/qup/0001-PENDING-soc-qcom-geni-se-Enable-QUPs-on-SA8255p-Qual.patch
    apply_patch ${downstream_qc_patch_path}/qup/0002-PENDING-serial-qcom-geni-Enable-Serial-on-SA8255p-pl.patch
    apply_patch ${downstream_qc_patch_path}/qup/0003-PENDING-i2c-qcom-geni-Enable-I2C-on-SA8255p-Qualcomm.patch
    apply_patch ${downstream_qc_patch_path}/qup/0004-PENDING-spi-geni-qcom-Enable-SPI-on-SA8255p-Qualcomm.patch
    apply_patch ${downstream_qc_patch_path}/qup/0005-PENDING-spi-geni-qcom-Enable-SPI-GSI-mode-for-SA8255.patch
    apply_patch ${downstream_qc_patch_path}/qup/0009-PENDING-i2c-qcom-geni-cleanup-in-probe-function.patch
    apply_patch ${downstream_qc_patch_path}/qup/0010-PENDING-i2c-qcom-geni-Add-support-for-S2R-feature.patch
    apply_patch ${downstream_qc_patch_path}/qup/0011-PENDING-serial-qcom-geni-Add-support-for-S2R-feature.patch
    apply_patch ${downstream_qc_patch_path}/qup/0012-PENDING-spi-spi-geni-qcom-Add-support-for-S2R-featur.patch
    apply_patch ${downstream_qc_patch_path}/qup/0013-PENDING-spi-spi-geni-qcom-set-lowest-OPP-during-susp.patch
    apply_patch ${downstream_qc_patch_path}/qup/0014-PENDING-serial-qcom-geni-set-lowest-OPP-during-suspe.patch
    apply_patch ${downstream_qc_patch_path}/qup/0015-PENDING-spi-qcom-geni-Allow-SPI-mode-reconfiguration.patch
    apply_patch ${downstream_qc_patch_path}/qup/0016-PENDING-serial-Ensure-DMA-buffer-is-synced-before-CP.patch
    apply_patch ${downstream_qc_patch_path}/qup/0017-PENDING-dmaengine-qcom-gpi-Handle-GPII-channel-recon.patch
    apply_patch ${downstream_qc_patch_path}/qup/0017-serial-qcom_geni-Fix-TX-interrupt-setup-and-spurious.patch
    apply_patch ${downstream_qc_patch_path}/0007-PENDING-scsi-ufs-qcom-Enable-sa8255p-platform.patch
    apply_patch ${downstream_qc_patch_path}/0001-PENDING-ufs-ufs-qcom-Skip-hibern8-FSM-state-check-fo.patch
    apply_patch ${downstream_qc_patch_path}/0001-PENDING-firmware-extend-vmid-support-to-128.patch
    apply_patch ${downstream_qc_patch_path}/usb/0001-PENDING-usb-dwc3-qcom-Ensure-VBUS_VALID-is-set-after.patch
    apply_patch ${downstream_qc_patch_path}/usb/0002-PENDING-usb-dwc3-qcom-Ensure-PIPE_UTMI_CLK_SEL-is-pr.patch
    apply_patch ${downstream_qc_patch_path}/usb/0003-PENDING-usb-dwc3-drd-expose-role-switch-control-to-u.patch
    apply_patch ${downstream_qc_patch_path}/usb/0004-PENDING-usb-dwc3-qcom-Trivial-code-cleanup.patch
    apply_patch ${downstream_qc_patch_path}/usb/0005-PENDING-usb-dwc3-Enable-role-switch-control-from-use.patch
    apply_patch ${downstream_qc_patch_path}/usb/0006-PENDING-usb-host-xhci-plat-Trivial-code-cleanup.patch
    apply_patch ${downstream_qc_patch_path}/usb/0007-PENDING-usb-host-xhci-plat-Trivial-code-cleanup.patch
    apply_patch ${downstream_qc_patch_path}/usb/0008-PENDING-usb-host-xhci-plat-Add-support-for-XHCI_RESE.patch
    apply_patch ${downstream_qc_patch_path}/usb/0009-PENDING-usb-dwc3-host-Set-XHCI_RESET_ON_RESUME-for-x.patch
    apply_patch ${downstream_qc_patch_path}/usb/0010-PENDING-phy-qcom-qmp-usb-Call-qmp_usb_remove-during-.patch
    apply_patch ${downstream_qc_patch_path}/usb/0011-PENDING-phy-qcom-qmp-usb-Add-support-for-SA8255P.patch
    apply_patch ${downstream_qc_patch_path}/usb/0012-PENDING-usb-dwc3-qcom-Add-support-for-sa8255p-for-qc.patch
    apply_patch ${downstream_qc_patch_path}/usb/0013-PENDING-phy-qcom-snps-femto-v2-Call-qcom_snps_hsphy_.patch
    apply_patch ${downstream_qc_patch_path}/usb/0014-PENDING-phy-qcom-snps-femto-v2-Add-support-for-SA825.patch
    apply_patch ${downstream_qc_patch_path}/pcie/0001-PCIe_RC_Add-Qualcomm-PCIe-ECAM-root-complex-driv.patch
    apply_patch ${downstream_qc_patch_path}/pcie/0002-PCIe_RC_Add-pcie-module-dependency.patch
    apply_patch ${downstream_qc_patch_path}/pcie/0004-MHI_RC_bus-mhi-host-pci_generic-Disable-auto-suspen.patch
    apply_patch ${downstream_qc_patch_path}/0001-FROMLIST-of-of_reserved_mem-Increase-limit-for-reser.patch
    apply_patch ${downstream_qc_patch_path}/0013-net-stmmac-dwmac-qcom-ethqos-Enable-SCMI-ETH.patch
    apply_patch ${downstream_qc_patch_path}/0014-PENDING-qcom-Add-sa7255p-compatibles-for-core-driver.patch
    apply_patch ${downstream_qc_patch_path}/0016-PENDING-ice-Enable-ICE-on-SA8255p-Qualcomm-platforms.patch
    apply_patch ${downstream_qc_patch_path}/scm_adci/0001-QCLINUX-arm64-dts-qcom-sa8255p-Modify-correct-dt-nam.patch
    apply_patch ${downstream_qc_patch_path}/scm_adci/0002-QCLINUX-arm64-dts-qcom-sa8775p-Modify-correct-dt-nam.patch
    apply_patch ${downstream_qc_patch_path}/scm_adci/0003-QCLINUX-arm64-dts-qcom-sa7255p-Modify-correct-dt-nam.patch
    apply_patch ${downstream_qc_patch_path}/scm_adci/0004-BACKPORT-FROMLIST-firmware-qcom-scm-Support-multiple.patch
    apply_patch ${downstream_qc_patch_path}/scm_adci/0005-PENDING-firmware-qcom-scm-Add-support-for-WAITQ_WAKE.patch
    apply_patch ${downstream_qc_patch_path}/scm_adci/0006-PENDING-firmware-qcom-scm-Add-new-lock-and-selective.patch
    apply_patch ${downstream_qc_patch_path}/scm_adci/0007-QCLINUX-arm64-dts-qcom-qcs9100-Modify-correct-dt-nam.patch
    apply_patch ${downstream_qc_patch_path}/scm_adci/0008-PENDING-firmware-qcom-scm-Fix-race-in-qcom_scm_get_c.patch
    apply_patch ${downstream_qc_patch_path}/scm_adci/0009-QCLINUX-firmware-qcom-scm-Fix-Makefile-for-trace-hea.patch
    apply_patch ${downstream_qc_patch_path}/0001-mm-memblock-enable-memory-hotplug.patch
    apply_patch ${downstream_qc_patch_path}/0001-PENDING-defer-no-map-memory-init-process.patch
    apply_patch ${downstream_qc_patch_path}/0003-scsi-ufs-Disable-auto-hibern8-feature.patch
    apply_patch ${downstream_qc_patch_path}/usb/0016-usb-dwc3-qcom-Add-support-for-sa8775p-for-qcom-usb.patch
    apply_patch ${downstream_qc_patch_path}/usb/0017-usb-phy-Add-snapshot-of-USB-PHY-EMU-driver.patch
    apply_patch ${downstream_qc_patch_path}/0008-Window-Watchdog-support-for-Sa8797.patch
    apply_patch ${downstream_qc_patch_path}/usb/0018-phy-qcom-phy-qcom-snps-eusb2-Add-support-for-SA8797P.patch
    apply_patch ${downstream_qc_patch_path}/usb/0019-usb-phy-qmp-combo-Add-scmi-related-changes-for-SA879.patch
    apply_patch ${downstream_qc_patch_path}/usb/0020-PENDING-phy-core-Introduce-PHY-type-and-helper-API.patch
    apply_patch ${downstream_qc_patch_path}/usb/0021-PENDING-phy-snps-eusb2-Set-PHY-type-for-Synopsys-eUS.patch
    apply_patch ${downstream_qc_patch_path}/usb/0022-PENDING-usb-dwc3-Program-eUSB2-UTMI-opmode-in-host-m.patch
    apply_patch ${downstream_qc_patch_path}/usb/0023-phy-phy-qcom-snps-eusb2-Add-register-sequence-to-fix.patch
    apply_patch ${downstream_qc_patch_path}/usb/0024-dwc3-gadget-Fix-compliance-TD-9.23-compliance-issue.patch
    apply_patch ${downstream_qc_patch_path}/usb/0025-PENDING-usb-phy-qmp-combo-Update-PHY-init-sequence.patch
    apply_patch ${downstream_qc_patch_path}/usb/0026-PENDING-phy-ptn3222-Add-support-to-parse-the-param-f.patch
    apply_patch ${downstream_qc_patch_path}/usb/0027-phy-qcom-snps-eusb2-Allow-missing-repeater-for-fw-ma.patch
    apply_patch ${downstream_qc_patch_path}/0014-mailbox-qcom-cpucp-restructure-the-cpucp-mailbox-dri.patch
    apply_patch ${downstream_qc_patch_path}/0015-scmi-support-for-scmi-vendor-protocol-and-log-driver.patch
    apply_patch ${downstream_qc_patch_path}/0016-QCLINUX-MPAM-Snapshot-of-QCOM-MPAM-Driver.patch
    apply_patch ${downstream_qc_patch_path}/0017-QCLINUX-MPAM-Snapshot-of-QCOM-SLC-MPAM-Driver.patch
    apply_patch ${downstream_qc_patch_path}/0018-QCLINUX-MPAM-Add-CPU-map-partid-for-CPU-MPAM-Driver.patch
    apply_patch ${downstream_qc_patch_path}/qup/0006-PENDING-soc-qcom-geni-se-Add-compatible-field-for-SA.patch
    apply_patch ${downstream_qc_patch_path}/qup/0007-PENDING-i2c-i2c-qcom-geni-Add-compatible-field-for-S.patch
    apply_patch ${downstream_qc_patch_path}/qup/0008-PENDING-spi-spi-geni-qcom-Add-compatible-field-for-S.patch
    apply_patch ${downstream_qc_patch_path}/qup/0013-PENDING-dmaengine-gpi-Add-new-register-offset-to-sup.patch
    apply_patch ${downstream_qc_patch_path}/qup/0014-PENDING-i2c-i2c-qcom-geni-Add-data-transfer-support-.patch
    apply_patch ${downstream_qc_patch_path}/qup/0015-PENDING-dmaengine-gpi-Add-new-API-to-enhance-CCU-QUP.patch
    apply_patch ${downstream_qc_patch_path}/qup/0016-PENDING-i2c-i2c-qcom-geni-Add-APIs-to-support-CCU-QU.patch
    apply_patch ${downstream_qc_patch_path}/qup/0017-PENDING-soc-qcom-ccu-qup-Add-CCU-QUP-platform-driver.patch
    apply_patch ${downstream_qc_patch_path}/qup/0018-PENDING-i2c-i2c-qcom-geni-Add-async-write-support.patch
    apply_patch ${downstream_qc_patch_path}/qup/0018-i2c-qcom-geni-Remove-redundant-runtime_resume-fallba.patch
    apply_patch ${downstream_qc_patch_path}/qup/0019-PENDING-soc-qcom-ccu-qup-Add-read-and-poll-API-suppo.patch
    apply_patch ${downstream_qc_patch_path}/qup/0020-PENDING-i2c-i2c-qcom-geni-Update-counter-setting-for.patch
    apply_patch ${downstream_qc_patch_path}/qup/0021-meta-qti-auto-kernel-Fix-cyclic-depedancy-between-CC.patch
    apply_patch ${downstream_qc_patch_path}/qup/0022-meta-qti-auto-kernel-Fix-double-unmap-issue-for-DMA-.patch
    apply_patch ${downstream_qc_patch_path}/qup/0023-i2c-qcom-geni-Fix-I2C-multi-message-write-and-DMA-bu.patch
    apply_patch ${downstream_qc_patch_path}/qup/0024-i2c-Enable-multi-random-write-feature.patch
    apply_patch ${downstream_qc_patch_path}/qup/0025-i2c-i2c-qcom-geni-Fix-NULL-pointer-dereference-issue.patch
    apply_patch ${downstream_qc_patch_path}/qup/0026-dmaengine-qcom-gpi-Add-I2C-bus-clear-and-bus-stop-su.patch
    apply_patch ${downstream_qc_patch_path}/qup/0027-ccu-Add-support-to-load-the-CCU-QUP-FW.patch
    apply_patch ${downstream_qc_patch_path}/qup/0028-i2c-Add-support-for-NOP-Frame.patch
    apply_patch ${downstream_qc_patch_path}/qup/0029-i2c-Fix-the-I2c-probe-issue.patch
    apply_patch ${downstream_qc_patch_path}/qup/0030-i2c-Add-validation-checks-and-fix-inter-frame-delay-.patch
    apply_patch ${downstream_qc_patch_path}/qup/0031-dmaengine-qcom-gpi-Add-premature-cancel-support-for-.patch
    apply_patch ${downstream_qc_patch_path}/qup/0032-PENDING-i2c-qcom-geni-Add-GSI-S2R-support-for-CCU-QU.patch
    apply_patch ${downstream_qc_patch_path}/pcie/0003-PCIe_RC_Patch-PCIe-Fix-Safety-Features-for-sa8797p.patch
    apply_patch ${downstream_qc_patch_path}/pcie/0005-MHI_RC_bus-mhi-host-pci_generic-Add-supoprt-for-SA8797P.patch
    apply_patch ${downstream_qc_patch_path}/pcie/0007-PCIe_EP_qcom-ep-Add-support-for-SCMI-based-PCIe-EP-for-Nords.patch
    apply_patch ${downstream_qc_patch_path}/pcie/0008-MHI_EP_dmaengine-dw-edma-Add-correct-offsets-for-HDMA-RD-WR.patch
    apply_patch ${downstream_qc_patch_path}/pcie/0001-pci-Add-pcie-module-dependency.patch
    apply_patch ${downstream_qc_patch_path}/pcie/0009-MHI_RC_bus-mhi-host-pci_generic-Add-support-for-FN990B40-modem.patch
    apply_patch ${downstream_qc_patch_path}/0020-serial-qcom-geni-Increase-UART-ports-to-7.patch
    apply_patch ${downstream_qc_patch_path}/minidump/0001-PENDING-kallsyms-Export-kallsyms_lookup_name.patch
    apply_patch ${downstream_qc_patch_path}/minidump/0002-PENDING-printk-sched-Export-internal-symbols-require.patch
    apply_patch ${downstream_qc_patch_path}/qup/0033-meta-qti-auto-kernel-ccu-Add-Ftrace-support-for-CCU.patch
    apply_patch ${downstream_qc_patch_path}/qup/0034-i2c-qcom-geni-Skip-TX-DMA-TRE-for-I2C-read-operation.patch
    apply_patch ${downstream_qc_patch_path}/qup/0035-i2c-qcom-geni-Add-asynchronous-read-support-for-CCU-.patch
    apply_patch ${downstream_qc_patch_path}/qup/0036-ccu-Optimize-interrupt-handling-and-improve-GSI-reso.patch
    apply_patch ${downstream_qc_patch_path}/qup/0037-ccu-Refactor-response-list-handling-to-prevent-corru.patch
    apply_patch ${downstream_qc_patch_path}/qup/0038-ccu-Add-support-for-passing-error-notification-event.patch
    apply_patch ${downstream_qc_patch_path}/qup/0039-ccu-Initialize-CCU-QUP-core-during-firmware-load-and.patch
    apply_patch ${downstream_qc_patch_path}/qup/0040-i2c-Prevent-kernel-panic-by-handling-ERR_PTR-from-dm.patch
    apply_patch ${downstream_qc_patch_path}/qup/0041-i2c-Update-clock-cycle-formula-per-latest-HPG-specif.patch
    apply_patch ${downstream_qc_patch_path}/qup/0042-ccu-WARN_ON-once-at-CCU_RETRY_CNT-during-GSI-pdev-lo.patch
    apply_patch ${downstream_qc_patch_path}/bluetooth/0001-Bluetooth-qca-add-support-for-QCA-automotive-BT-chip.patch
    apply_patch ${downstream_qc_patch_path}/wlan/0001-net-wireless-Enable-WEXT-legacy-support-for-kernel-6.patch
    apply_patch ${downstream_qc_patch_path}/wlan/0002-wifi-cfg80211-ignore-non-TX-BSSs-in-per-STA-profile.patch
}
do_generate_base_defconfig() {
    cd "${KERNEL_PLATFORM_DIR}"
    export KCONFIG_CONFIG=${KERNEL_PLATFORM_DIR}/kernel/arch/arm64/configs/defconfig
    rm -f ${WORKSPACE}/layers/meta-qti-auto-kernel/recipes-kernel/linux/files/no-earlyramdisk.cfg
    cat <<EOF > ${WORKSPACE}/layers/meta-qti-auto-kernel/recipes-kernel/linux/files/no-earlyramdisk.cfg
CONFIG_SCSI_UFS_QCOM=y
CONFIG_SCSI_UFSHCD=y
CONFIG_SCSI_UFSHCD_PLATFORM=y
CONFIG_QCOM_IPCC=y
CONFIG_SERIAL_QCOM_GENI=y
CONFIG_PINCTRL_MSM=y
CONFIG_PINCTRL_SECA=y
CONFIG_QCOM_CCU_QUP=y
CONFIG_QCOM_GPI_DMA=y
CONFIG_I2C_QCOM_GENI=y
CONFIG_I2C_MUX_PCA954x=y
CONFIG_OVERLAY_FS=y
CONFIG_GENERIC_PHY=y
CONFIG_PHY_QCOM_USB_EMU_PHY=y
CONFIG_PHY_QCOM_QMP_UFS=y
CONFIG_PHY_QCOM_QMP=y
CONFIG_PHY_QCOM_QMP_COMBO=y
CONFIG_PHY_QCOM_QMP_PCIE=y
CONFIG_PHY_QCOM_QMP_UFS=y
CONFIG_SCSI_UFSHCD_PCI=y
CONFIG_PCIE_QCOM_EP=y
CONFIG_PHY_QCOM_QMP_USB=y
CONFIG_USB_CONFIGFS=y
CONFIG_USB_CONFIGFS_F_FS=y
CONFIG_USB_F_FS=y
CONFIG_USB_DWC3_DUAL_ROLE=y
CONFIG_USB_DWC3_QCOM=y
CONFIG_USB_GADGET=y
CONFIG_USB_LIBCOMPOSITE=y
CONFIG_PINCTRL_SA8797P=y
CONFIG_PINCTRL_SCMI=y
CONFIG_MODULE_FORCE_LOAD=y
CONFIG_IGC=m
CONFIG_RTC_LIB=y
CONFIG_RTC_DRV_RV8803=y
CONFIG_STMMAC_ETH=y
CONFIG_STMMAC_PLATFORM=y
CONFIG_AQUANTIA_PHY=y
CONFIG_MARVELL_PHY=y
CONFIG_PCS_XPCS=y
CONFIG_QCOM_MDT_LOADER=y
CONFIG_VFIO_PLATFORM=y
CONFIG_VFIO_PLATFORM_BASE=y
CONFIG_QCOM_SOCINFO=y
CONFIG_NR_CPUS=32
CONFIG_MHI_BUS=y
CONFIG_RMNET=y
CONFIG_QRTR=y
CONFIG_QRTR_MHI=y
CONFIG_WWAN=y
CONFIG_WWAN_CORE=y
CONFIG_MHI_WWAN_CTRL=y
CONFIG_MHI_WWAN_MBIM=y
CONFIG_MHI_BUS_DEBUG=y
CONFIG_CAN_M_CAN=m
CONFIG_CAN_M_CAN_TCAN4X5X=m
EOF
    base_defconfig=${KERNEL_PLATFORM_DIR}/kernel/arch/arm64/configs/qcom_defconfig
    if [ "${BUILD_VARIANT}" = "perf" ]; then
        variant_cfg="${WORKSPACE}/layers/meta-qti-auto-kernel/recipes-kernel/linux/files/perf.cfg"
    else
        variant_cfg="${WORKSPACE}/layers/meta-qti-auto-kernel/recipes-kernel/linux/files/devmem.cfg"
    fi
    kernel_arch_config="${KERNEL_PLATFORM_DIR}/kernel/arch/arm64/configs/qcom_gen4auto.config  ${KERNEL_PLATFORM_DIR}/kernel/arch/arm64/configs/qcom_gen4auto_debug.config  ${WORKSPACE}/layers/meta-qti-realtime/recipes-kernel/linux/linux-qcom-custom-rt/qcom_rt.cfg  ${WORKSPACE}/layers/meta-qti-auto-kernel/recipes-kernel/linux/files/sa8797p-generic.cfg ${WORKSPACE}/layers/meta-qti-auto-kernel/recipes-kernel/linux/files/iqx.cfg ${WORKSPACE}/layers/meta-qti-auto-kernel/recipes-kernel/linux/files/generic.cfg ${WORKSPACE}/layers/meta-qti-auto-kernel/recipes-kernel/linux/files/selinux.cfg ${variant_cfg} ${WORKSPACE}/layers/meta-qti-auto-kernel/recipes-kernel/linux/files/no-earlyramdisk.cfg"
    # Disable early-ramdisk for now (-y)
    ${KERNEL_PLATFORM_DIR}/kernel/scripts/kconfig/merge_config.sh -m -r -y ${base_defconfig} ${kernel_arch_config}
}
build_kernel() {
    KERNELRELEASE=$(awk '/^VERSION =|^PATCHLEVEL =|^SUBLEVEL =/ {print $3}' ${KERNEL_PLATFORM_DIR}/kernel/Makefile | paste -sd '.' -)
    do_kernel_patch

    set -e
    do_generate_base_defconfig
    cd "${KERNEL_PLATFORM_DIR}"/kernel
    make defconfig
    make scripts
    make -j 16 \
        CC=gcc LD=ld.bfd OBJCOPY=objcopy STRIP=strip KERNELRELEASE=${KERNELRELEASE}\
        dtbs
    make -j 16 \
        CC=gcc LD=ld.bfd OBJCOPY=objcopy STRIP=strip KERNELRELEASE=${KERNELRELEASE}\
        KCFLAGS="-I$(pwd)/drivers/soc/qcom" \
        Image
    make -j 16 \
        CC=gcc LD=ld.bfd OBJCOPY=objcopy STRIP=strip KERNELRELEASE=${KERNELRELEASE}\
        KCFLAGS="-I$(pwd)/drivers/soc/qcom" \
        INSTALL_MOD_STRIP=1 modules
}
match_dtb_to_dtbo () {
    dtb=$1
    dtbo=$2
    dtbo_compatible=$(fdtget -t s $dtbo / "compatible" | sed -e 's/\"//g' -e 's/[;\,]//g')
    dtbo_model=$(fdtget -t s $dtbo / "model" | sed -e 's/\"//g' -e 's/[;\,]//g')
    dtb_compatible=$(fdtget -t s $dtb / "compatible" | sed -e 's/\"//g' -e 's/[;\,]//g')
    dtb_model=$(fdtget -t s $dtb / "model" | sed -e 's/\"//g' -e 's/[;\,]//g')
    if [ "$dtb_model" = "$dtbo_model" ]; then
        return 0
    fi
    for dtb in $dtb_compatible; do
        for dtbo in $dtbo_compatible; do
            if [ "$dtb" = "$dtbo" ]; then
                return 0
            fi
        done
    done
    return 1
}
merge_dtbos () {
    dtb_dir=$1
    dtbo_dir=$2
    out_dir=$3
    matched_dtbos=""
    dtb_files=$(find $dtb_dir -name "*.dtb*")
    dtbo_files=$(find $dtbo_dir -name "*.dtbo")
    if [ -z "$dtb_files" ]; then
        echo "ERR : Base DTB files NOT found"
        exit 1
    fi
    if [ -z "$dtbo_files" ]; then
        echo "WARN: Overlay DTB files not found"
        cp $dtb_dir/* $out_dir
        return 0
    fi
    for dtb_file in $dtb_files; do
        matched_dtbos=""
        for dtbo_file in $dtbo_files; do
            if match_dtb_to_dtbo $dtb_file $dtbo_file; then
                matched_dtbos="${matched_dtbos} ${dtbo_file}"
            fi
        done
        base_name=$(basename $dtb_file)
        base_dtb_name=$(echo "$base_name" | sed -e 's/\.[^.]*$//')
        out_dtb=${base_dtb_name}-overlay.dtb
        if [ "$matched_dtbos" != ""  ]; then
            # execute the command in verbose mode(-v)
            fdtoverlay -i $dtb_file -o ${out_dir}/${out_dtb} -v $matched_dtbos
            #exit in case of failure
            if [ $? -ne 0 ]; then
                exit 1
            fi
        else
            cp $dtb_file ${out_dir}/${out_dtb}
        fi
    done
}
merge_dtbos_single () {
    dtb_dir=$1
    dtbo_dir=$2
    out_dir=$3
    dtb_files=$(find $dtb_dir -name "*.dtb*")
    dtbo_files=$(find $dtbo_dir -name "*.dtbo")
    if [ -z "$dtb_files" ]; then
        echo "ERR : Base DTB files NOT found"
        exit 1
    fi
    if [ -z "$dtbo_files" ]; then
        echo "WARN: Overlay DTB files not found"
        cp $dtb_dir/* $out_dir
        return 0
    fi
    for dtb_file in $dtb_files; do
        dtbo_matched=""
        for dtbo_file in $dtbo_files; do
            if match_dtb_to_dtbo $dtb_file $dtbo_file; then
                dtbo_matched="true"
                dtbo_string=$(basename $dtbo_file)
                dtbo_string=$(echo "$dtbo_string" | sed -e 's/\.[^.]*$//')
                out_dtb=${dtbo_string}.dtb
                # execute the command in verbose mode(-v)
                fdtoverlay -i $dtb_file -o ${out_dir}/${out_dtb} -v $dtbo_file
                #exit in case of failure
                if [ $? -ne 0 ]; then
                    exit 1
                fi
            fi
        done
        if [ -z "$dtbo_matched" ]; then
            base_name=$(basename $dtb_file)
            base_dtb_name=$(echo "$base_name" | sed -e 's/\.[^.]*$//')
            out_dtb=${base_dtb_name}-overlay.dtb
            cp $dtb_file ${out_dir}/${out_dtb}
        fi
    done
}
merge_ddr_dtbos_single () {
    dtb_dir=$1
    dtbo_dir=$2
    out_dir=$3
    ddr_sizes="64gb:0x700 48gb:0x600 36gb:0x500 32gb:0x500 24gb:0x400 16gb:0x300 12gb:0x200 8gb:0x100"
    dtb_files=$(find $dtb_dir -name "*.dtb")
    dtbo_files=$(find $dtbo_dir -name "*.dtbo")
    if [ -z "$dtb_files" ]; then
        echo "ERR : Base DTB files NOT found"
        exit 1
    fi
    if [ -z "$dtbo_files" ]; then
        echo "WARN: Overlay DTB files not found"
        cp $dtb_dir/* $out_dir
        return 0
    fi
    for dtb_file in $dtb_files; do
        for dtbo_file in $dtbo_files; do
            dtbo_string=$(basename $dtbo_file)
            prefix2=$(echo "$dtbo_string" | sed -e 's/-.*//')
            dtbo_string=$(echo "$dtbo_string" | sed -e 's/\.[^.]*$//')
            input_dtb=$(basename "$dtb_file")
            prefix1=$(echo "$input_dtb" | sed -e 's/-.*//')
            if [ "$prefix1" != "$prefix2" ]; then
                cp $dtb_file $out_dir
                continue
            fi
            # Extract a suffix from the input DTB filename by:
            # 1. Removing the base name up to the first '-' or '_' character.
            # 2. Removing any 'overlay' tokens surrounded by '-', '_', or nothing.
            # 3. Stripping the file extension.
            # Example:
            #   input_dtb="sa8775p-sw-eth-phy_overlay-overlay.dtb"
            #   Resulting suffix="sw-eth-phy"
            suffix=$(echo $input_dtb | sed -n 's/^[^\(-\|_\)]*[\(-\|_\)]\(.*\)/\1/p' \
                     | sed 's/\(-\|_\|\)overlay\(-\|_\|\)//g' | sed 's/\..*//')
            if [ -z "$suffix" ]; then
                out_dtb=${dtbo_string}.dtb
            else
                out_dtb=${dtbo_string}-${suffix}.dtb
            fi
            for i in $ddr_sizes; do
               ddr_size=$(echo $i | sed 's,:.*,,g')
               ddr_type=$(echo $i | sed 's,.*:,,g')
               if [[ "$dtbo_file" == *"$ddr_size"* ]]; then
                  subtype="$ddr_type"
                  break
               fi
            done
            fdtoverlay -i $dtb_file -o ${out_dir}/${out_dtb} -v $dtbo_file
            #get board-id from dtb files and replace with updated value
            #OR operation of board id subtype and ddr type is performed.
            board_id=$(fdtget -t x ${out_dir}/${out_dtb} / qcom,board-id )
            updated_bid=$(echo "$board_id" | awk -v mask_hex="$subtype" '
            BEGIN {
                mask = strtonum(mask_hex)
            }
            {
                for (i = 1; i <= NF; i++) {
                    val = strtonum("0x" $i)
                    if (i % 2 == 0) {
                        val = or(val, mask)
                    }
                    printf "0x%X ", val
                }
            }')
            # execute the command in verbose mode(-v)
            fdtput -t x  ${out_dir}/${out_dtb} / qcom,board-id $updated_bid
            #exit in case of failure
            if [ $? -ne 0 ]; then
                exit 1
            fi
        done
    done
}
build_oot_dtbo() {
    rm -rf "${OUTPUT_DIR}/build-dtb-artifacts"
    cd "${WORKSPACE}/vendor/qcom/opensource/base-devicetree"
    make -j 16 \
        dtbos \
        KDIR="${KERNEL_PLATFORM_DIR}"/kernel \
        CC=gcc LD=ld.bfd OBJCOPY=objcopy STRIP=strip
    cd "${WORKSPACE}/vendor/qcom/proprietary/mm-vfio-devicetree/"
    make -j 16 \
        KERNEL_SRC="${KERNEL_PLATFORM_DIR}"/kernel \
        M="${WORKSPACE}/vendor/qcom/proprietary/mm-vfio-devicetree/" \
        CC=gcc LD=ld.bfd OBJCOPY=objcopy STRIP=strip \
        dtbs
    cd "${WORKSPACE}/vendor/qcom/opensource/audiolite/devicetree"
    mkdir -p safelinux-system-cfg
    ln -sf ${WORKSPACE}/vendor/qcom/opensource/safelinux-system-cfg/devicetree/oot-dt-bindings safelinux-system-cfg/oot-dt-bindings
    make -j 16 \
        KERNEL_SRC="${KERNEL_PLATFORM_DIR}"/kernel \
        AUDIOLITE_DTC_INCLUDE="${KERNEL_PLATFORM_DIR}/kernel/include ${WORKSPACE}/vendor/qcom/opensource/audiolite/devicetree" \
        M="${WORKSPACE}/vendor/qcom/opensource/audiolite/devicetree" \
        CC=gcc LD=ld.bfd OBJCOPY=objcopy STRIP=strip \
        dtbs
    mkdir -p "${OUTPUT_DIR}/build-dtb-artifacts"
    mkdir -p "${OUTPUT_DIR}/build-dtb-artifacts/ddrdtbos"
    mkdir -p "${OUTPUT_DIR}/build-dtb-artifacts/ddrdtbosflex"
    mkdir -p "${OUTPUT_DIR}/build-dtb-artifacts/dtb"
    mkdir -p "${OUTPUT_DIR}/build-dtb-artifacts/techpack-dtbs"
    cp -f ${WORKSPACE}/vendor/qcom/opensource/base-devicetree/arch/arm64/boot/dts/qcom/sa8797p-ddr*.dtbo "${OUTPUT_DIR}/build-dtb-artifacts/ddrdtbos"
    cp -f ${WORKSPACE}/vendor/qcom/opensource/base-devicetree/arch/arm64/boot/dts/qcom/sa8x97p-flex*.dtbo "${OUTPUT_DIR}/build-dtb-artifacts/ddrdtbosflex"
    cp -f ${WORKSPACE}/vendor/qcom/opensource/base-devicetree/arch/arm64/boot/dts/qcom/*.dtb "${OUTPUT_DIR}/build-dtb-artifacts/dtb"
    cp -f ${WORKSPACE}/vendor/qcom/opensource/base-devicetree/arch/arm64/boot/dts/qcom/sa8397p-overlay.dtbo "${OUTPUT_DIR}/build-dtb-artifacts/techpack-dtbs"
    cp -f ${WORKSPACE}/vendor/qcom/opensource/base-devicetree/arch/arm64/boot/dts/qcom/sa8797p-overlay.dtbo "${OUTPUT_DIR}/build-dtb-artifacts/techpack-dtbs"
    cp -f ${WORKSPACE}/vendor/qcom/opensource/base-devicetree/arch/arm64/boot/dts/qcom/qcs8797-iqx-evk-overlay.dtbo "${OUTPUT_DIR}/build-dtb-artifacts/techpack-dtbs"
    cp -f ${WORKSPACE}/vendor/qcom/proprietary/mm-vfio-devicetree/sa8797p-mm-vfio-iqx.dtbo "${OUTPUT_DIR}/build-dtb-artifacts/techpack-dtbs"
    cp -f ${WORKSPACE}/vendor/qcom/proprietary/mm-vfio-devicetree/sa8797p-mm-vfio.dtbo "${OUTPUT_DIR}/build-dtb-artifacts/techpack-dtbs"
    cp -f ${WORKSPACE}/vendor/qcom/opensource/audiolite/devicetree/*audiolite*.dtbo "${OUTPUT_DIR}/build-dtb-artifacts/techpack-dtbs"
    rm -f "${OUTPUT_DIR}/build-dtb-artifacts/dtb/sa8797p-qvp.dtb"
    rm -f "${OUTPUT_DIR}/build-dtb-artifacts/dtb/seca-rumi.dtb"
    rm -f "${OUTPUT_DIR}/build-dtb-artifacts/dtb/sa8x97p-non-safe-ivi-qam-pats.dtb"
    rm -f "${OUTPUT_DIR}/build-dtb-artifacts/dtb/sa8x97p-qam-pats.dtb"
    rm -f "${OUTPUT_DIR}/build-dtb-artifacts/dtb/sa8x97p-safe-ivi-qam-pats.dtb"
    mkdir -p "${OUTPUT_DIR}/build-dtb-artifacts/interout"
    mkdir -p "${OUTPUT_DIR}/build-dtb-artifacts/dtbs"
    mkdir -p "${OUTPUT_DIR}/build-dtb-artifacts/flexdtb"
    merge_dtbos "${OUTPUT_DIR}/build-dtb-artifacts/dtb" "${OUTPUT_DIR}/build-dtb-artifacts/techpack-dtbs" "${OUTPUT_DIR}/build-dtb-artifacts/interout"
    #Copy flex dtb from interout to separate directory
    for file in "${OUTPUT_DIR}/build-dtb-artifacts/interout"/*flex*; do
         if [ -f "$file" ]; then
             mv "$file" "${OUTPUT_DIR}/build-dtb-artifacts/flexdtb"
         fi
    done
    merge_ddr_dtbos_single "${OUTPUT_DIR}/build-dtb-artifacts/interout" "${OUTPUT_DIR}/build-dtb-artifacts/ddrdtbos" "${OUTPUT_DIR}/build-dtb-artifacts/dtbs"
    # Apply overlay for flex dtb
    if ! [[ -z "$(ls -A "${OUTPUT_DIR}/build-dtb-artifacts/flexdtb")" || -z "$(ls -A "${OUTPUT_DIR}/build-dtb-artifacts/ddrdtbosflex")" ]]; then
        merge_ddr_dtbos_single "${OUTPUT_DIR}/build-dtb-artifacts/flexdtb" "${OUTPUT_DIR}/build-dtb-artifacts/ddrdtbosflex" "${OUTPUT_DIR}/build-dtb-artifacts/dtbs"
    elif ! [[ -z "$(ls -A "$flex_directory")" ]]; then
        cp -r "${OUTPUT_DIR}/build-dtb-artifacts/flexdtb"/* "${OUTPUT_DIR}/build-dtb-artifacts/dtbs"/
    fi
    cat "${OUTPUT_DIR}/build-dtb-artifacts/dtbs"/*.dtb* > "${OUTPUT_DIR}/build-dtb-artifacts/dtbs"/dtb.img
}
build_bootimg() {
    cmdline=' rootwait firmware_class.path=/firmware/vm/boot systemd.gpt_auto=0 cgroup.memory=nokmem,nosocket qcom_scm.download_mode=1 rcupdate.rcu_expedited=1 rcu_nocbs=0-17 rcupdate.rcu_normal_after_boot=0 fsck.repair=yes systemd.service_watchdogs=0 driver_async_probe=scmi-hwmon androidboot.slot_suffix=_a root=PARTLABEL=system_a modprobe.blacklist=dm-multipath systemd.machine-id=512cec5b6c9547259d2c6ff2baf84f7e net.ifnames=0 biosdevname=0'
    if [ "${BUILD_VARIANT}" != "perf" ]; then
        cmdline="console=ttyMSM0,115200,n8 page_owner=on${cmdline}"
    fi
    # perf/debug outputs live in separate OUTPUT_DIRs (out-perf/ vs out/),
    # so the filenames no longer need a -perf suffix.
    boot_img="${OUTPUT_DIR}/boot.img"
    cp ${KERNEL_PLATFORM_DIR}/kernel/vmlinux ${OUTPUT_DIR}/vmlinux
    ${WORKSPACE}/mkbootimg/mkbootimg.py --header_version 2 \
        --kernel  "${KERNEL_PLATFORM_DIR}"/kernel/arch/arm64/boot/Image \
        --dtb  "${OUTPUT_DIR}"/build-dtb-artifacts/dtbs/dtb.img \
        --pagesize 4096 \
        --base 0x80000000 \
        --ramdisk_offset 0x0 \
        --cmdline "${cmdline}" \
        --output  ${boot_img}
}
# create kernal package manually, Depends on kernel build
create_kernel_package() {
    export KERNELRELEASE=`grep 'UTS_RELEASE' ${KERNEL_PLATFORM_DIR}/kernel/include/generated/utsrelease.h | cut -d'"' -f2`
    echo $KERNELRELEASE
    MAKEFILE=${KERNEL_PLATFORM_DIR}/kernel/Makefile
    export KERNELVERSION=$(awk '/^VERSION =|^PATCHLEVEL =|^SUBLEVEL =/ {print $3}' "$MAKEFILE" | paste -sd '.' -)
    echo $KERNELVERSION
    export KCONFIG_CONFIG=${KERNEL_PLATFORM_DIR}/kernel/arch/arm64/configs/defconfig
    export srctree=${KERNEL_PLATFORM_DIR}/kernel/
    export KBUILD_DEBARCH=arm64
    export ARCH=arm64

    rm -rf  ${WORKSPACE}/kernel/kernel_platform/source
    mkdir -p ${WORKSPACE}/kernel/kernel_platform/source/usr/src
    cp -r ${WORKSPACE}/kernel/kernel_platform/kernel/ ${WORKSPACE}/kernel/kernel_platform/source/usr/src
    chmod -R a+rX ${WORKSPACE}/kernel/kernel_platform/source/usr/src/kernel/
    mkdir ${WORKSPACE}/kernel/kernel_platform/source/DEBIAN
    touch ${WORKSPACE}/kernel/kernel_platform/source/DEBIAN/control
    chmod 0755 ${WORKSPACE}/kernel/kernel_platform/source/DEBIAN
    chmod 0755 ${WORKSPACE}/kernel/kernel_platform/source/DEBIAN/control
    cat <<EOF > ${WORKSPACE}/kernel/kernel_platform/source/DEBIAN/control
Package: linux-qcom-source
Section: base
Version: ${KERNELVERSION}
Priority: optional
Architecture: all
Maintainer: leiwan <leiwan@autobuild-arm-sh01-lnx.qualcomm.com>
Homepage: https://www.kernel.org/
Description: Linux source code package deployed without compilation.
EOF
    cd ${WORKSPACE}/kernel/kernel_platform
    fakeroot dpkg-deb --build source
    mv source.deb linux-qcom-source.deb

    cd ${srctree}
    ./scripts/package/mkdebian --need-source
    debuild --no-lintian --no-tgz-check -us -uc
}

create_kernel_dlkm_package() {
    MAKEFILE=${KERNEL_PLATFORM_DIR}/kernel/Makefile
    export KERNELVERSION=$(awk '/^VERSION =|^PATCHLEVEL =|^SUBLEVEL =/ {print $3}' "$MAKEFILE" | paste -sd '.' -)
    rm -rf ${WORKSPACE}/kernel/kernel_platform/kernel-dlkm
    MODPATH=${WORKSPACE}/kernel/kernel_platform/kernel-dlkm/lib/modules/${KERNELVERSION}/updates/
    mkdir -p ${MODPATH}
    mkdir -p ${WORKSPACE}/kernel/kernel_platform/kernel-dlkm/DEBIAN
    touch ${WORKSPACE}/kernel/kernel_platform/kernel-dlkm/DEBIAN/control
    chmod 0755 ${WORKSPACE}/kernel/kernel_platform/kernel-dlkm/DEBIAN
    chmod 0755 ${WORKSPACE}/kernel/kernel_platform/kernel-dlkm/DEBIAN/control
    cat <<EOF > ${WORKSPACE}/kernel/kernel_platform/kernel-dlkm/DEBIAN/control
Package: kernel-dlkm
Section: base
Version: ${KERNELVERSION}
Priority: optional
Architecture: all
Maintainer: leiwan <leiwan@autobuild-arm-sh01-lnx.qualcomm.com>
Homepage: https://www.kernel.org/
Description: Linux source code package deployed without compilation.
EOF
    find ${WORKSPACE}/kernel/kernel_platform/kernel/ -type f -name "*.ko" -exec cp -t  ${MODPATH} {} +
    mkdir -p ${WORKSPACE}/kernel/kernel_platform/kernel-dlkm/etc/modules-load.d/
    cat <<EOF > ${WORKSPACE}/kernel/kernel_platform/kernel-dlkm/etc/modules-load.d/auto-dlkm.conf
drm
drm_kms_helper
phy-qcom-qmp-combo
phy-qcom-snps-eusb2
typec
EOF
    cd ${WORKSPACE}/kernel/kernel_platform
    fakeroot dpkg-deb --build kernel-dlkm
}

# reoragnize kernel packages
reorganize_kernel_deb() {
    rm -rf ${WORKSPACE}/debian_packages/oss/linux-qcom/
    mkdir -p ${WORKSPACE}/debian_packages/oss/linux-qcom/
    cp ${WORKSPACE}/kernel/kernel_platform/linux-qcom-source.deb ${WORKSPACE}/debian_packages/oss/linux-qcom/
    cp ${WORKSPACE}/kernel/kernel_platform/linux-libc-dev*deb ${WORKSPACE}/debian_packages/oss/linux-qcom/
    cp ${WORKSPACE}/kernel/kernel_platform/linux-headers*deb ${WORKSPACE}/debian_packages/oss/linux-qcom/
    cp ${WORKSPACE}/kernel/kernel_platform/kernel-dlkm*deb ${WORKSPACE}/debian_packages/oss/linux-qcom/
}

mkdir -p "${OUTPUT_DIR}"
if [ -z "${BUILD_VARIANT}" ]; then
    echo "Error: -v <variant> is required (debug or perf)"
    exit 1
fi
if [[ $PACKAGE_ONLY = false ]];then
build_kernel
build_oot_dtbo
build_bootimg
fi
create_kernel_package
create_kernel_dlkm_package
reorganize_kernel_deb
