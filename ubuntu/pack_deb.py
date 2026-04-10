"""
pack_deb.py

This script automates the process of creating a system image for a Debian-based operating system.
It sets up a chroot environment, parses package manifests, builds the image with specified packages,
and configures the bootloader. The script requires root privileges to execute.
"""

import os
import shutil
import subprocess
import threading
import argparse
import importlib.util
import re
from pathlib import Path
from queue import Queue
from collections import defaultdict, deque
from constants import *
from helpers import *
from deb_organize import search_manifest_map_for_path
from color_logger import logger

class PackagePacker:
    def __init__(self, MOUNT_DIR, IMAGE_TYPE, VARIANT, OUT_DIR, OUT_SYSTEM_IMG, APT_SERVER_CONFIG, TEMP_DIR, DEB_OUT_DIR, DEBIAN_INSTALL_DIR, IS_CLEANUP_ENABLED,PACKAGES_MANIFEST_PATH=None,QC_FOLDER=None,IF_RELEASE_ENABLED=False,TECH_VARIANT=None,BASE_MANIFEST_PATH=None):
        """
        Initializes the PackagePacker instance.

        Args:
        -----
        - MOUNT_DIR (str): The directory where the image will be mounted.
        - IMAGE_TYPE (str): The type of image to create.
        - VARIANT (str): The variant of the image (e.g., 'qcom').
        - OUT_DIR (str): The output directory for the image files.
        - OUT_SYSTEM_IMG (str): The path to the output system image file.
        - APT_SERVER_CONFIG (list): Configuration for the APT server.
        - TEMP_DIR (str): Temporary directory for building the image.
        - DEB_OUT_DIR (str): Output directory for Debian packages.
        - DEBIAN_INSTALL_DIR (str): Directory for Debian installation files.
        - IS_CLEANUP_ENABLED (bool): Flag to enable cleanup of temporary files.
        """

        if not check_if_root():
            logger.error('Please run this script as root user.')
            exit(1)
        self.cur_file = os.path.dirname(os.path.realpath(__file__))

        if not len(os.listdir(MOUNT_DIR)) == 0:
            raise Exception(f"Folder {MOUNT_DIR} should be empty.")

        self.MOUNT_DIR = Path(MOUNT_DIR)
        self.IMAGE_TYPE = IMAGE_TYPE
        self.DEBIAN_INSTALL_DIR = DEBIAN_INSTALL_DIR
        self.VARIANT = VARIANT
        self.OUT_DIR = OUT_DIR
        self.TEMP_DIR = TEMP_DIR
        self.OUT_SYSTEM_IMG = OUT_SYSTEM_IMG
        self.PACKAGES_MANIFEST_PATH = PACKAGES_MANIFEST_PATH
        self.qc_folder = QC_FOLDER
        self.IS_RELEASE_ENABLED = IF_RELEASE_ENABLED
        self.TECH_VARIANT = TECH_VARIANT
        if self.TECH_VARIANT in SNAP_SHOT_TABLE.keys():
            self.TECH_DEBIAN_MIRROR = f"{SNAP_SHOT_TABLE.get(TECH_VARIANT).get("mirror")}/{SNAP_SHOT_TABLE.get(TECH_VARIANT).get("date")}"
        else:
            self.TECH_DEBIAN_MIRROR = None

        self.BASE_MANIFEST_PATH = None
        if BASE_MANIFEST_PATH:
            try:
                self.BASE_MANIFEST_PATH = resolve_manifest_path(BASE_MANIFEST_PATH, self.TEMP_DIR, self.IMAGE_TYPE)
            except Exception as e:
                logger.critical(f"Manifest resolution failed: {e}")
                exit(1)

        self.EFI_BIN_PATH = os.path.join(self.OUT_DIR, "efi.bin")
        self.EFI_MOUNT_PATH = os.path.join(self.MOUNT_DIR, "boot", "efi")

        self.DEBS = []
        self.QCOM_PINNED_PACKAGES = {}  # package -> version, from packages/<flavor>.manifest
        self.APT_SERVER_CONFIG = APT_SERVER_CONFIG

        self.IS_CLEANUP_ENABLED = IS_CLEANUP_ENABLED

        self.DEB_OUT_DIR = DEB_OUT_DIR
        self.DEBIAN_INSTALL_DIR = DEBIAN_INSTALL_DIR

        self.parse_manifests()
        self.set_system_image()

    def set_system_image(self):
        """
        Creates and mounts the system image file.

        Raises:
        -------
        - Exception: If there is an error creating or mounting the system image.
        """
        run_command(f"truncate -s {IMAGE_SIZE_IN_G}G {self.OUT_SYSTEM_IMG}")
        run_command(f"mkfs.ext4 -F -U $(uuidgen) {self.OUT_SYSTEM_IMG}")
        run_command(f"mount -o loop {self.OUT_SYSTEM_IMG} {self.MOUNT_DIR}")

    def set_efi_bin(self):
        """
        Creates and mounts the EFI binary for the bootloader.

        Raises:
        -------
        - Exception: If there is an error creating or mounting the EFI binary.
        """
        cleanup_file(self.EFI_BIN_PATH)
        run_command(f"dd if=/dev/zero of={self.EFI_BIN_PATH} bs=512 count=32768")
        run_command(f"mkfs.fat -F16 -s 8 -h 2048 -n EFI {self.EFI_BIN_PATH}")

        create_new_directory(self.EFI_MOUNT_PATH)
        run_command(f"mount -o loop {self.EFI_BIN_PATH} {self.EFI_MOUNT_PATH}")
        grub_update_cmd = f"""echo 'GRUB_CMDLINE_LINUX="ro console=ttyMSM0,115200n8 pcie_pme=nomsi earlycon qcom_scm.download_mode=1 reboot=panic_warm"
GRUB_DEVICE="/dev/disk/by-partlabel/system"
GRUB_TERMINAL="console"
GRUB_DISABLE_LINUX_UUID="true"
GRUB_DISABLE_RECOVERY="true"' >> {os.path.join(self.MOUNT_DIR, 'etc', 'default', 'grub')}"""
        run_command(grub_update_cmd)

    def merge_manifests_from_folder(self, folder_path, image_type, subdir_filter=None):
        """
        Merges all non-empty manifest files matching image_type in the given folder and subfolders.
        If subdir_filter is provided, only includes manifests from subdirectories matching it.
        Returns the path to the merged manifest file.
        """
        if not os.path.isdir(folder_path):
            return None

        merged_manifest_path = os.path.join(self.TEMP_DIR, f"{image_type}.manifest")
        try:
            with open(merged_manifest_path, 'w') as merged_file:
                for root, _, files in os.walk(folder_path):
                    if subdir_filter and subdir_filter not in os.path.relpath(root, folder_path):
                        continue
                    for file in files:
                        if file == f"{image_type}.manifest":
                            file_path = os.path.join(root, file)
                            try:
                                if os.path.getsize(file_path) > 0:  # Check if file is not empty
                                    logger.info(f"Including manifest from: {file_path}")
                                    with open(file_path, 'r') as f:
                                        merged_file.write(f.read())
                            except (IOError, OSError) as e:
                                logger.warning(f"Failed to read manifest file {file_path}: {e}")

                return merged_manifest_path
        except (IOError, OSError) as e:
            logger.error(f"Failed to create or write to merged manifest file: {e}")
            return None

    def parse_manifests(self):
        """
        Parses the base and QCOM manifests to gather the list of packages to include in the image.
        """
        self.QCOM_MANIFEST = None

        # 1. If user provided a manifest path, use it
        if self.PACKAGES_MANIFEST_PATH:
            logger.info(f"Packages manifest path: {self.PACKAGES_MANIFEST_PATH}")
            self.DEBS = parse_debs_manifest(self.PACKAGES_MANIFEST_PATH)
            return

        # 2. If base manifest path is provided
        if self.BASE_MANIFEST_PATH:
            logger.info(f"Base manifest argument provided: {self.BASE_MANIFEST_PATH}")

            # Parse base manifest (local or downloaded)
            self.DEBS = parse_debs_manifest(self.BASE_MANIFEST_PATH)

        # 3. Default fallback logic
        if not self.BASE_MANIFEST_PATH :
            base_folder = os.path.join(self.cur_file, "packages", "base", f"{self.IMAGE_TYPE}.manifest")
            if base_folder:
                self.BASE_MANIFEST = base_folder
                if os.path.exists(base_folder):
                    self.DEBS = parse_debs_manifest(self.BASE_MANIFEST)
                    logger.info(f"Using base manifests from: {self.BASE_MANIFEST}")
            else:
                logger.error("No base manifests found.")

            # 3. Merge qcom manifests if variant is qcom
            if self.VARIANT == "qcom":
                qcom_path = os.path.join(self.cur_file, "packages", "qcom", f"{self.IMAGE_TYPE}.manifest")
                self.QCOM_MANIFEST = qcom_path
                if os.path.exists(qcom_path):
                    logger.info(f"Using QCOM manifest: {self.QCOM_MANIFEST}")
                    self.DEBS.extend(parse_debs_manifest(self.QCOM_MANIFEST))

        # 4. Load custom packages from packages/<flavor>.manifest if it exists
        # Qualcomm-specific packages are listed here with version pinning.
        custom_manifest_path = os.path.join(self.cur_file, "packages", f"{self.IMAGE_TYPE}.manifest")
        if os.path.exists(custom_manifest_path):
            logger.info(f"Loading custom packages from: {custom_manifest_path}")
            custom_debs = parse_debs_manifest(custom_manifest_path)
            if custom_debs:
                self.DEBS = self.extend_debs_list(self.DEBS, custom_debs)
                # Record Qualcomm-specific packages for version pinning in get_deb_list()
                self.QCOM_PINNED_PACKAGES = {
                    deb['package']: deb['version']
                    for deb in custom_debs
                    if deb.get('version')
                }
                logger.info(f"Added {len(custom_debs)} custom package(s) from {custom_manifest_path}, "
                            f"{len(self.QCOM_PINNED_PACKAGES)} with version pinning")
        else:
            logger.debug(f"No custom manifest found at: {custom_manifest_path}")

        # 5. Merge from qc_folder if provided
        if self.qc_folder:
            # Base manifests from qc_folder
            qc_base_merged = self.merge_manifests_from_folder(self.qc_folder, self.IMAGE_TYPE,"base")
            logger.info(f"Using base manifests from: {qc_base_merged}")

            # Todo: Not ready, skip for the moment
            logger.info(f"Skip merge base and qcom manifests from qc_folder")
            return

            if qc_base_merged:
                qc_base_debs_list = parse_debs_manifest(qc_base_merged)
                self.DEBS = self.extend_debs_list(self.DEBS, qc_base_debs_list)

            # QCOM manifests from qc_folder
            if self.VARIANT == "qcom":
                qc_qcom_merged = self.merge_manifests_from_folder(self.qc_folder, self.IMAGE_TYPE, "qcom")
                if qc_qcom_merged:
                    logger.info(f"Using qcom manifests from: {qc_qcom_merged}")
                    manifest_debs = parse_debs_manifest(qc_qcom_merged)
                    if self.IS_RELEASE_ENABLED:
                        # Append +rel to everyone (no filtering)
                        manifest_debs[:] = [{**d, "version": (d["version"] if d["version"].endswith("+rel") else d["version"] + "+rel")}
                        for d in manifest_debs]
                        logger.info("Assuming a release build, appending +rel to all packages.")
                        logger.info(manifest_debs)
                    self.DEBS = self.extend_debs_list(self.DEBS, manifest_debs)

            return

        # 3. No manifest found: print message and exit
        logger.error("No manifest found. Please provide a valid .manifest file via PACKAGES_MANIFEST_PATH or ensure default manifests exist.")
        exit(1)

    def get_deb_list(self) -> None:
        """
        Constructs a list of Debian packages to be included in the image.
        - Qualcomm-specific packages (from packages/<flavor>.manifest) use version pinning
          to ensure the exact local version is installed.
        - Ubuntu official packages ignore version, installing the latest available.

        Returns:
        --------
        - str: A comma-separated string of package specs (name or name=version).
        """
        result = []
        for deb in self.DEBS:
            pkg = str(deb['package']).strip()
            pinned_version = self.QCOM_PINNED_PACKAGES.get(pkg)
            if pinned_version:
                result.append(f"{pkg}={str(pinned_version).strip()}")
            else:
                result.append(pkg)
        result = ['ca-certificates'] + result
        result = list(set(result))
        debs = ",".join(result)

        return debs

    def build_image(self):
        """
        Builds the system image using mmdebstrap with the specified packages.

        Raises:
        -------
        - Exception: If there is an error during the image building process.
        """
        log_file = os.path.join(self.TEMP_DIR, f"mmdebstrap_{self.IMAGE_TYPE}_{self.VARIANT}.mmdebstrap.build")

        bash_command = f"""
sudo mmdebstrap --verbose --variant=apt --logfile={log_file} \
--customize-hook='echo root:password | chroot "$1" chpasswd' \
--customize-hook='echo qc-ubuntu > "$1/etc/hostname"' \
--customize-hook='echo "127.0.0.1 localhost qc-ubuntu" > "$1/etc/hosts"' \
--customize-hook='chroot "$1" useradd -m -s /bin/bash -p $(openssl passwd -6 "qc-ubuntu") qc-ubuntu' \
--customize-hook='chroot "$1" usermod -aG sudo qc-ubuntu' \
--customize-hook='cp {self.cur_file}/01-end0.yaml "$1/etc/netplan/01-end0.yaml"' \
--customize-hook='echo "PermitRootLogin yes" >> "$1/etc/ssh/sshd_config"' \
--customize-hook='chroot "$1" depmod -a 6.6.110' \
--setup-hook='echo /dev/disk/by-partlabel/system / ext4 defaults 0 1 > "$1/etc/fstab"' \
--arch=arm64 \
--aptopt='APT::Get::Allow-Downgrades "true";' \
--include={self.get_deb_list()} \
noble \
{self.MOUNT_DIR}"""

        if self.DEB_OUT_DIR:
            apt_command = build_deb_package_gz(self.DEB_OUT_DIR)
            bash_command += f" \"{apt_command}\""

        if self.DEBIAN_INSTALL_DIR:
            apt_command = build_deb_package_gz(self.DEBIAN_INSTALL_DIR)
            bash_command += f" \"{apt_command}\""

        if self.APT_SERVER_CONFIG:
            for config in self.APT_SERVER_CONFIG:
                if config.strip():
                    bash_command += f" \"{config.strip()}\""

        bash_command += f" \"deb [arch=arm64 trusted=yes] http://ports.ubuntu.com/ubuntu-ports noble main universe multiverse restricted\""
        bash_command += f" \"deb [arch=arm64 trusted=yes] http://ports.ubuntu.com/ubuntu-ports noble-updates main universe multiverse restricted\""
        if self.TECH_DEBIAN_MIRROR:
            bash_command += f" \"deb [arch=arm64 trusted=yes] {self.TECH_DEBIAN_MIRROR} noble main\""

        out = run_command_for_result(bash_command)
        if out['returncode'] != 0:
            raise Exception(f"Error building image: {out['output']}")
        else:
            logger.info("Image built successfully.")

        # Set efi.bin
        try:
            self.set_efi_bin()
        except Exception as e:
            logger.error(f"Error setting EFI binary: {e}")
            if self.IS_CLEANUP_ENABLED:
                umount_dir(self.EFI_MOUNT_PATH)
            raise Exception(e)

        mount_img(self.OUT_SYSTEM_IMG, self.MOUNT_DIR, MOUNT_HOST_FS=True, MOUNT_IMG=False)

        out = run_command_for_result(f"chroot {self.MOUNT_DIR} {TERMINAL} -c 'grub-install --target=arm64-efi --efi-directory=/boot/efi --bootloader-id=ubuntu'")
        if out['returncode'] != 0:
            if self.IS_CLEANUP_ENABLED:
                umount_dir(self.EFI_MOUNT_PATH)
            raise Exception(f"Error installing grub: {out['output']}")
        else:
            logger.info("Grub installed successfully.")
            out = run_command_for_result(f"chroot {self.MOUNT_DIR} {TERMINAL} -c 'update-grub'")
            if out['returncode'] != 0:
                if self.IS_CLEANUP_ENABLED:
                    umount_dir(self.EFI_MOUNT_PATH)
                raise Exception(f"Error updating grub: {out['output']}")
            else:
                logger.info("Grub updated successfully.")

        self.extract_manifest(self.IMAGE_TYPE)

        if self.IS_CLEANUP_ENABLED:
            umount_dir(self.EFI_MOUNT_PATH)
            umount_dir(self.MOUNT_DIR, UMOUNT_HOST_FS=True)

    def extract_manifest(self, flavor):
        """
        Extracts the list of installed packages and their versions from the mounted system image
        and saves it as a <flavor>.manifest file in the OUT_DIR.
        """
        manifest_path = os.path.join(self.OUT_DIR, f"{flavor}.manifest")
        command = f"chroot {self.MOUNT_DIR} dpkg-query -W -f='${{Package}}\\t${{Version}}\\n' > {manifest_path}"
        result = run_command_for_result(command)

        if result['returncode'] != 0:
            logger.error(f"Failed to extract manifest for {flavor}: {result['output']}")
        else:
            logger.info(f"Manifest for {flavor} saved to {manifest_path}")


    def get_merged_manifest(self):
        if self.PACKAGES_MANIFEST_PATH:
            logger.info(f"User provided manifest path: {self.PACKAGES_MANIFEST_PATH}")
            return self.PACKAGES_MANIFEST_PATH

        manifest_paths = []
        if self.BASE_MANIFEST_PATH :
            manifest_paths.append(self.BASE_MANIFEST_PATH)

        # Always merge from qc_folder and packages
        search_dirs = [
            (self.qc_folder, "base"),
            (os.path.join(self.cur_file, "packages"), "base")
        ]

        if self.VARIANT == "qcom":
            search_dirs += [
                (self.qc_folder, "qcom"),
                (os.path.join(self.cur_file, "packages"), "qcom")
            ]

        for folder, subdir in search_dirs:
            if folder and os.path.isdir(folder):
                for root, _, files in os.walk(folder):
                    # Only include manifests from subdirectories matching subdir
                    if subdir in os.path.relpath(root, folder).split(os.sep):
                        for file in files:
                            if file == f"{self.IMAGE_TYPE}.manifest":
                                manifest_paths.append(os.path.join(root, file))

        # Merge all found manifest files into one
        merged_manifest_path = os.path.join(self.TEMP_DIR, f"{self.IMAGE_TYPE}_merged.manifest")
        with open(merged_manifest_path, 'w') as merged_file:
            for manifest in manifest_paths:
                with open(manifest, 'r') as f:
                    merged_file.write(f.read())
        logger.info(f"Final merged manifest saved to: {merged_manifest_path}")
        return merged_manifest_path


    def cleanup_downloaded_manifest(self):
        """
        Cleans up the downloaded manifest file.
        """
        if self.BASE_MANIFEST_PATH:
            try:
                if os.path.exists(self.BASE_MANIFEST_PATH):
                    logger.info(f"Cleaning up downloaded manifest: {self.BASE_MANIFEST_PATH}")
                    os.remove(self.BASE_MANIFEST_PATH)
                    logger.debug(f"Successfully removed downloaded manifest")
            except Exception as e:
                logger.warning(f"Failed to cleanup downloaded manifest: {e}")

    def extend_debs_list(self, debs_list, curr_debs):

        debs_list = debs_list or []
        curr_debs = curr_debs or []

        # Dictionary to store index of a dict in debs list
        package_idx_map = {}

        for idx, deb in enumerate(debs_list):

            package_idx_map[deb['package']] = idx

        # remove duplicate/add latest version to existing package and append new DEBS to the list
        for curr_deb in curr_debs:
            if curr_deb['package'] in package_idx_map:
                target_idx = package_idx_map[curr_deb['package']]
                debs_list[target_idx].update(curr_deb)
            else:
                debs_list.append(curr_deb)

        return debs_list
