import os

LINUX_IMAGE_DBGSYM_DEB = "linux-qcom/linux-qcom-tools*_arm64.deb"
LINUX_MODULES_DEB = "linux-qcom/linux-modules-*_arm64.deb"
SNAP_SHOT_DATE = "2025-12-22"  #upgrade to x07 snapshot from https://ports-ubuntu.qualcomm.com/ports.ubuntu.com/

SNAP_SHOT_TABLE = {
    "ros":{"mirror":"http://ports-ubuntu.qualcomm.com/ros2/packages.ros.org","date":"24-09-2025"}
}
# ROS_SNAP_SHOT_DATE = "24-09-2025"update date for snapshot date from https://ports-ubuntu.qualcomm.com/ros2/packages.ros.org/

KERNEL_DEBS = [
    "linux-modules",
    "linux-tools",
    "linux-buildinfo",
    "linux-qcom-tools",
    "linux-headers",
    "linux-image-unsigned",
    "linux-libc-dev-qcom",
    "linux-source",
    "linux-qcom-headers"
]

COMBINED_DTB_FILE  = "combined-dtb.dtb"
VMLINUX_QCOM_FILE  = "vmlinux"
IMAGE_NAME         = "system.img"

IMAGE_SIZE_IN_G     = 8

TERMINAL = "/bin/bash"

HOST_FS_MOUNT = ["dev", "proc"]
