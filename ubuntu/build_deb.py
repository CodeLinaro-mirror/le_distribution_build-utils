# Copyright (c) Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause-Clear
"""
build_deb.py

This script is designed to automate the process of building Debian packages within a chroot environment.
"""

import os
import shutil
import subprocess
import threading
import argparse
import importlib.util
import re
import tempfile
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from collections import defaultdict, deque
from constants import *
from helpers import run_command, check_and_append_line_in_file, create_new_directory, build_deb_package_gz, run_command_for_result, print_build_logs, download_ros2_apt_source_deb, fix_debian_permissions
from deb_organize import search_manifest_map_for_path
from color_logger import logger

class PackageNotFoundError(Exception):
    """
    Exception raised when a package is not found.
    """
    pass

class PackageBuildError(Exception):
    """
    Exception raised when there is an error during package building.
    """
    pass

class PackageBuilder:
    def __init__(self, CHROOT_NAME, CHROOT_DIR, SOURCE_DIR, APT_SERVER_CONFIG, \
    MANIFEST_MAP=None, DEB_OUT_TEMP_DIR=None, DEB_OUT_DIR=None, DEB_OUT_DIR_APT=None, \
    DEBIAN_INSTALL_DIR_APT=None, IS_CLEANUP_ENABLED=True, IS_PREPARE_SOURCE=False, \
    DIST= "noble", ARCH="arm64", CHROOT_SUFFIX="ubuntu", TECH_VARIANT=None, incremental=False):
        """
        Initializes the PackageBuilder instance.

        Args:
        -----
        - CHROOT_NAME (str): The name of the chroot environment.
        - CHROOT_DIR (str): The directory where the chroot environment is found, or created if it doesnt already exist.
        - SOURCE_DIR (str): The source directory containing the packages to build.
        - APT_SERVER_CONFIG (list): Configuration for the APT server.
        - MANIFEST_MAP (dict, optional): A mapping of package paths to their properties.
        - DEB_OUT_TEMP_DIR (str, optional): Temporary directory for building packages.
        - DEB_OUT_DIR (str, optional): Output directory for built Debian packages.
        - DEB_OUT_DIR_APT (str, optional): Output directory for APT repository.
        - DEBIAN_INSTALL_DIR_APT (str, optional): Directory for APT installation files.
        - IS_CLEANUP_ENABLED (bool, optional): Flag to enable cleanup of the mount directory.
        - IS_PREPARE_SOURCE (bool, optional): If True, prepares the source directory before building. Defaults to False.
        """
        self.CHROOT_NAME = CHROOT_NAME
        self.CHROOT_DIR  = CHROOT_DIR
        self.DIST = DIST
        self.ARCH = ARCH
        self.CHROOT_SUFFIX = CHROOT_SUFFIX
        self.SOURCE_DIR = SOURCE_DIR
        self.APT_SERVER_CONFIG = APT_SERVER_CONFIG
        self.MANIFEST_MAP = MANIFEST_MAP
        self.DEB_OUT_TEMP_DIR = DEB_OUT_TEMP_DIR
        self.IS_CLEANUP_ENABLED = IS_CLEANUP_ENABLED
        self.DEB_OUT_DIR = DEB_OUT_DIR
        self.DEB_OUT_DIR_APT = DEB_OUT_DIR_APT
        self.DEBIAN_INSTALL_DIR_APT = DEBIAN_INSTALL_DIR_APT
        self.IS_PREPARE_SOURCE = IS_PREPARE_SOURCE
        self.TECH_VARIANT = TECH_VARIANT
        self.incremental = incremental
        self.build_state = {}
        self.rebuilt_packages = set()
        self.source_changed_packages = set()
        self._stats_built = []
        self._stats_skipped = 0
        self._start_time = None
        if self.incremental and self.DEB_OUT_DIR:
            self._load_build_state()
        if self.TECH_VARIANT in SNAP_SHOT_TABLE.keys():
            self.TECH_DEBIAN_MIRROR = SNAP_SHOT_TABLE.get(TECH_VARIANT).get("mirror")
        else:
            self.TECH_DEBIAN_MIRROR = None
        self.DEBIAN_MIRROR = "http://ports.ubuntu.com/ubuntu-ports"
        self.packages = {}
        self.generate_schroot_config()

    def _install_ros2_apt_source_in_chroot(self):
        """
        Installs ros2-apt-source in the chroot using the official .deb package.

        Downloads the latest ros2-apt-source release from GitHub and installs it
        with dpkg inside the chroot. This sets up the ROS apt source and GPG key
        in one step, replacing the old manual ros.key approach.

        Skips silently if already installed. On any failure logs a warning and
        returns; build_package() will fall back to --extra-repository trusted=yes.
        """
        chroot_path = f"{self.CHROOT_DIR}/{self.CHROOT_NAME}"
        ros_apt_source_file = os.path.join(
            chroot_path, "usr", "share", "ros-apt-source", "ros2.sources"
        )

        if os.path.exists(ros_apt_source_file):
            logger.info("ros2-apt-source already installed in chroot, skipping.")
            return

        logger.info("Installing ros2-apt-source in chroot environment...")
        try:
            tmp_deb_path = download_ros2_apt_source_deb(tempfile.gettempdir(), self.DIST)
            deb_name = os.path.basename(tmp_deb_path)
            chroot_deb = os.path.join(chroot_path, "tmp", deb_name)
            try:
                subprocess.run(["cp", tmp_deb_path, chroot_deb], check=True)
                subprocess.run(["chmod", "644", chroot_deb], check=True)

                install_result = subprocess.run(
                    ["chroot", chroot_path, "dpkg", "-i", f"/tmp/{deb_name}"],
                    capture_output=True, text=True,
                )

                if install_result.returncode != 0:
                    raise RuntimeError(f"dpkg -i failed: {install_result.stderr}")

                update_result = subprocess.run(
                    ["chroot", chroot_path, "apt-get", "update", "-qq"],
                    capture_output=True, text=True,
                )
                if update_result.returncode != 0:
                    logger.warning(f"apt-get update after ros2-apt-source install failed: {update_result.stderr}")

                logger.info(f"ros2-apt-source installed successfully in chroot")
            finally:
                if os.path.exists(tmp_deb_path):
                    os.unlink(tmp_deb_path)
                if os.path.exists(chroot_deb):
                    os.unlink(chroot_deb)
        except Exception as e:
            logger.warning(f"Failed to install ros2-apt-source in chroot: {e}")
            logger.warning("Will use trusted=yes for ROS repository instead")

    def _get_build_state_path(self):
        return os.path.join(self.DEB_OUT_DIR, ".build-state.json")

    def _load_build_state(self):
        path = self._get_build_state_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            if data.get('schema_version') == 1:
                self.build_state = data.get('packages', {})
                logger.info(f"[incremental] Loaded build state for {len(self.build_state)} packages")
        except (json.JSONDecodeError, IOError, KeyError) as e:
            logger.warning(f"[incremental] Could not load build state, will do full rebuild: {e}")
            self.build_state = {}

    def _save_build_state(self):
        path = self._get_build_state_path()
        try:
            with open(path, 'w') as f:
                json.dump({'schema_version': 1, 'packages': self.build_state}, f, indent=2)
        except IOError as e:
            logger.warning(f"[incremental] Failed to save build state: {e}")

    def _compute_source_hash(self, repo_path):
        SKIP_DIRS = {'.git', '__pycache__', '.pc'}
        SKIP_EXTS = {'.pyc', '.deb', '.ddeb', '.dsc', '.gz', '.xz', '.o', '.ko'}
        hasher = hashlib.sha256()
        for root, dirs, files in os.walk(str(repo_path)):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for fname in sorted(files):
                if os.path.splitext(fname)[1] in SKIP_EXTS:
                    continue
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, str(repo_path))
                hasher.update(rel.encode())
                try:
                    with open(fpath, 'rb') as f:
                        while chunk := f.read(65536):
                            hasher.update(chunk)
                except (IOError, OSError):
                    pass
        return 'sha256:' + hasher.hexdigest()

    def _can_skip_build(self, repo_path, dependencies):
        state = self.build_state.get(str(repo_path))
        if not state:
            return False
        if any(dep in self.source_changed_packages for dep in dependencies):
            logger.debug(f"[incremental] Dependency source-changed, forcing rebuild of {repo_path.name}")
            return False
        current_hash = self._compute_source_hash(repo_path)
        if state.get('source_hash') != current_hash:
            logger.debug(f"[incremental] Source changed for {repo_path.name}")
            return False
        for fpath in state.get('output_debs', []):
            if not os.path.exists(fpath):
                logger.debug(f"[incremental] Output missing for {repo_path.name}: {fpath}")
                return False
        return True

    def generate_schroot_config(self):
        """
        Generates the schroot configuration for the specified chroot environment.

        Raises:
        -------
        - Exception: If there is an error creating the schroot environment.
        """

        logger.debug(f"Checking if chroot container '{self.CHROOT_NAME}' is already registered")

        cmd = f"schroot -l | grep chroot:{self.CHROOT_NAME}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if result.returncode == 0:
            logger.info(f"Schroot container {self.CHROOT_NAME} already exists. Skipping creation.")
            # Even for an existing schroot, ensure ros2-apt-source is installed when needed.
            # This handles schroots created before this code was introduced.
            if self.TECH_VARIANT == "ros" and self.TECH_DEBIAN_MIRROR:
                self._install_ros2_apt_source_in_chroot()
            return

        logger.warning(f"Schroot container '{self.CHROOT_NAME}' does not exist, creating it for the first time.")
        logger.warning(f"The chroot will be created in {self.CHROOT_DIR}/{self.CHROOT_NAME}")
        logger.warning(f"Its config will be stored as /etc/schroot/chroot.d/{self.CHROOT_NAME}.conf")

        # this command creates a chroot environment that will be named "{DIST}-{ARCH}-{SUFFIX}"
        # We supply our own suffix, otherwise sbuild will use 'sbuild'
        cmd = f"sbuild-createchroot --arch={self.ARCH}" \
                                 f" --keyring="" " \
                                 f" --chroot-suffix=-{self.CHROOT_SUFFIX}" \
                                 f" --components=main,universe" \
                                 f" {self.DIST}" \
                                 f" {self.CHROOT_DIR}/{self.CHROOT_NAME}" \
                                 f" {self.DEBIAN_MIRROR}"
        
        logger.debug(f"Creating schroot environment with command: {cmd}")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if result.returncode != 0:
            raise Exception(f"Error creating schroot environment: {result.stderr}")

        # Install ros2-apt-source in chroot if using ROS (official method).
        if self.TECH_VARIANT == "ros" and self.TECH_DEBIAN_MIRROR:
            self._install_ros2_apt_source_in_chroot()

        subprocess.run(["chroot", f"{self.CHROOT_DIR}/{self.CHROOT_NAME}", "bash", "-c", f"sed -i 's|{self.DEBIAN_MIRROR}|[trusted=yes] {self.DEBIAN_MIRROR}|' /etc/apt/sources.list"])

        logger.info(f"Schroot environment {self.CHROOT_NAME} created successfully.")

    @staticmethod
    def _canonical_pkg_name(pkg_name: str) -> str:
        name = pkg_name.removesuffix('-dev').removesuffix('-dbgsym')
        if name and name[-1].isdigit():
            name = name[:-1]
        return name

    def _find_output_debs(self, pkg_names: set) -> list:
        found = []
        for pkg in pkg_names:
            cname = self._canonical_pkg_name(pkg)
            for subdir in ('oss', 'prop'):
                d = Path(self.DEB_OUT_DIR) / subdir / cname
                if d.is_dir():
                    for f in d.iterdir():
                        if f.suffix in ('.deb', '.ddeb') and f.is_file():
                            found.append(str(f))
        return sorted(found)

    def _auto_bootstrap(self):
        """Bootstrap build state from existing .deb output when no state file exists."""
        logger.info("[incremental] No build state found — bootstrapping from existing output...")
        recorded = 0
        for pkg_key, pkg_info in self.packages.items():
            repo_path = pkg_info['repo_path']
            repo_name = pkg_info['repo_name']
            pkg_names = pkg_info['packages']
            output_debs = self._find_output_debs(pkg_names)
            if not output_debs:
                continue
            source_hash = self._compute_source_hash(repo_path)
            self.build_state[str(repo_path)] = {
                'repo_name': repo_name,
                'source_hash': source_hash,
                'last_built': datetime.now(timezone.utc).isoformat(),
                'output_debs': output_debs,
            }
            recorded += 1
        self._save_build_state()
        logger.info(f"[incremental] Bootstrap complete: {recorded}/{len(self.packages)} packages recorded")

    def load_packages(self):
        """Load package metadata from build_config.py and fetch dependencies from control files."""
        source_dirs = self.SOURCE_DIR if isinstance(self.SOURCE_DIR, list) else [self.SOURCE_DIR]
        for source_dir in source_dirs:
            for root, dirs, files in os.walk(source_dir, followlinks=True):
                dirs[:] = [d for d in dirs if d != '.git']
                if 'debian' in dirs:
                    if os.path.exists(os.path.join(root, '.disable_package')) or os.path.exists(os.path.join(root, '.build-disable')):
                        logger.debug(f"Skipping disabled package: {root}")
                        continue
                    root_name = Path(root).name
                    debian_dir = Path(os.path.join(root, 'debian'))
                    pkg_names, dependencies = self.get_packages_from_control(debian_dir / "control")

                    self.packages[str(debian_dir)] = {
                        "debian_dir": debian_dir,
                        "repo_path": Path(root),
                        "repo_name": root_name,
                        "dependencies": dependencies,
                        "packages": pkg_names,
                        "visited": False
                    }

        if self.incremental and self.DEB_OUT_DIR and not self.build_state:
            self._auto_bootstrap()

    def get_packages_from_control(self, control_file):
        """
        Extracts package names and build dependencies from the control file.

        Args:
        -----
        - control_file (Path): The path to the control file.

        Returns:
        --------
        - tuple: A tuple containing a set of package names and a set of dependencies.

        Raises:
        -------
        - SystemExit: If the control file is invalid or does not exist.
        """
        if not control_file.exists():
            return []

        packages = set()
        dependencies = set()
        found_build_depends = False
        build_depends_lines = []

        with open(control_file, "r") as f:
            for line in f:
                line_strip = line.strip()
                if line.startswith('Package:'):
                    packages.add(line_strip.split(':', 1)[1].strip())

                elif line.startswith('Build-Depends:') and not found_build_depends:
                    found_build_depends = True
                    if line_strip.split(':', 1)[1].strip():
                        build_depends_lines.append(line_strip.split(':', 1)[1].strip())

                elif found_build_depends and line.startswith((" ", "\t")):
                    if line_strip:
                        build_depends_lines.append(line_strip)

                elif found_build_depends and not line.startswith((" ", "\t")):
                    found_build_depends = False

        if build_depends_lines:
            full_deps = " ".join(build_depends_lines)
            dependencies.update(dep.split()[0] for dep in full_deps.split(", "))

        if len(packages) == 0:
            logger.error(f"Invalid control file at {control_file}")
            exit(1)

        return packages, dependencies

    def detect_cycle(self):
        """
        Detects cycles in the dependency graph using Kahn's Algorithm.

        Returns:
        --------
        - list: A sorted order of packages if no cycles are detected, otherwise logs an error.
        """
        graph = {}
        in_degree = {}

        sorted_order = []

        if self.packages:
            for repo in self.packages:
                for binary in self.packages[repo]['packages']:
                    in_degree[binary] = 0
                    graph[binary] = []

            for repo in self.packages:
                for binary in self.packages[repo]['packages']:
                    for dependency in self.packages[repo]['dependencies']:
                        if dependency not in in_degree:
                            in_degree[dependency] = 0
                            graph[dependency] = []
                        graph[dependency].append(binary)
                        in_degree[binary] += 1

            queue = deque([pkg for pkg in in_degree if in_degree[pkg] == 0])
            if not queue:
                logger.warning('No Package with in_degree 0, Possible cycle detected.')
                min_pkg = min(in_degree, key=in_degree.get)
                logger.warning(f'Forcing {min_pkg} into the queue.')
                queue.append(min_pkg)

            while queue:
                pkg = queue.popleft()
                sorted_order.append(pkg)
                for dependent in graph[pkg]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

            cycle_nodes = [pkg for pkg in in_degree if in_degree[pkg] > 0]

            # cycle_edges = []
            # if cycle_nodes:
            #     for node in cycle_nodes:
            #         for dep in self.dependencies.get(node, []):
            #             if dep in cycle_nodes:
            #                 cycle_edges.append((node, dep))

            if len(cycle_nodes) > 0:
                # TODO: Fetch the nodes causing a cyclic dependency
                # logger.error('Cycle detected in dependencies for the following pairs:')
                # for edge in cycle_edges:
                #     logger.error(str(edge))
                logger.error("Cycle detected in dependencies! Halting build.")
                return
            else:
                logger.info('No cycle detected in dependencies.')

        return sorted_order

    def reorganize_outputs_in_oss_prop(self, repo_source_path, repo_build_tmp_dir):
        """
        Reorganizes built packages files into the appropriate output directory based on the manifest map.
        Also reorganizes the 'dsc' file form the repo source path.

        A given 'repo_build_tmp_dir' is a folder containing all the built packages for a given repository.
        In most cases it contains one .deb package, but it is possible that building one repo yields more than one package
        For any .deb package, there is also almost always an associated -dev.deb and -dbgsym.ddeb package.
        In some cases, it is possible that for a given package, only a -dev.deb file exists, no .deb.

        Args:
        -----
        - repo_source_path (Path): The path to the repository containing the sources of the built packages.
        - repo_build_tmp_dir (Path): The path to the temporary directory where the built packages are stored.
        """

        # Look back into the source directory manifest to determine if the package is OSS (open source) or PROP (proprietary).
        source_dirs = self.SOURCE_DIR if isinstance(self.SOURCE_DIR, list) else [self.SOURCE_DIR]
        matching_source_dir = next(
            (sd for sd in source_dirs if str(repo_source_path).startswith(sd)),
            source_dirs[0]
        )
        oss_or_prop = search_manifest_map_for_path(self.MANIFEST_MAP, matching_source_dir, repo_source_path)

        repo_parent_path = repo_source_path.parent

        # Create a list of all the packages (.deb, -dev.deb, -dbgsym.ddeb)
        files = os.listdir(repo_build_tmp_dir)
        deb_files = [f for f in files if f.endswith('.deb')  and "-dev" not in f]
        dev_files = [f for f in files if f.endswith('.deb')  and "-dev"     in f]
        dbg_files = [f for f in files if f.endswith('.ddeb') and "-dbgsym"  in f]

        # Isolate all the canonical package names (i.e. remove the version and architecture from the filenames)
        deb_pkg_names = [f.split('_')[0]                         for f in deb_files]
        dev_pkg_names = [f.split('_')[0].removesuffix("-dev")    for f in dev_files]
        dbg_pkg_names = [f.split('_')[0].removesuffix("-dbgsym") for f in dbg_files]

        # Second pass to remove all the major version that often suffix the package names
        # The norm is that packages that include the major in the deb name DO NOT include it in the dev
        # this ensures we deal with root package name and not doubles when we combine the lists below
        deb_pkg_names = [(f[:-1] if f[-1].isdigit() else f) for f in deb_pkg_names]
        dev_pkg_names = [(f[:-1] if f[-1].isdigit() else f) for f in dev_pkg_names]
        dbg_pkg_names = [(f[:-1] if f[-1].isdigit() else f) for f in dbg_pkg_names]

        package_names = list(set(deb_pkg_names) | set(dev_pkg_names) | set(dbg_pkg_names))

        # Important that the list be sorted from the longest package name to the shortest
        # Starting with the longest and removing it from the _files lists ensures we deal
        # properly specificaly with the edge case or qcom-adreno/qcom-adreno-cl
        package_names.sort(reverse=True, key=lambda x: len(x))

        copied_files = []
        for package_name in package_names:
            output_dir = os.path.join(self.DEB_OUT_DIR, oss_or_prop, package_name)
            create_new_directory(output_dir, delete_if_exists=False)

            logger.debug(f"Re-organizing outputs of package: {package_name} (oss/prop: {oss_or_prop})")

            deb_package = next((file for file in deb_files if package_name in file), None)
            dev_package = next((file for file in dev_files if package_name in file), None)
            dbg_package = next((file for file in dbg_files if package_name in file), None)

            if deb_package is not None:
                dst = os.path.join(output_dir, deb_package)
                shutil.copy(os.path.join(repo_build_tmp_dir, deb_package), dst)
                copied_files.append(dst)
                logger.info(f'Copied {deb_package} to {output_dir}')
                deb_files.remove(deb_package)
            else:
                logger.debug(f"No .deb package found for {package_name}")

            if dev_package is not None:
                dst = os.path.join(output_dir, dev_package)
                shutil.copy(os.path.join(repo_build_tmp_dir, dev_package), dst)
                copied_files.append(dst)
                logger.info(f'Copied {dev_package} to {output_dir}')
                dev_files.remove(dev_package)
            else:
                logger.debug(f"No -dev.deb package found for {package_name}")

            if dbg_package is not None:
                dst = os.path.join(output_dir, dbg_package)
                shutil.copy(os.path.join(repo_build_tmp_dir, dbg_package), dst)
                copied_files.append(dst)
                logger.info(f'Copied {dbg_package} to {output_dir}')
                dbg_files.remove(dbg_package)
            else:
                logger.debug(f"No -dbgsym.ddeb package found for {package_name}")

            # Deal with the .dsc file
            dsc_package = next((f for f in os.listdir(repo_parent_path) if f.endswith('.dsc') and package_name in f), None)

            if dsc_package is not None:
                shutil.move(os.path.join(repo_parent_path, dsc_package), os.path.join(output_dir, dsc_package))
                logger.info(f'Moved {dsc_package} to {output_dir}')
            else:
                logger.debug(f"No .dsc file found for {package_name}")

        return copied_files

    def build_package(self, package):
        """
        Builds a package inside the chroot environment.

        Args:
        -----
        - package (str): The name of the package to build, this is a 'debian' folder

        Raises:
        -------
        - Exception: If there is an error during the build process.
        """

        logger.debug(f"Building debian folder: {package}")

        if not Path(package).is_dir() or Path(package).name != "debian":
            raise ValueError ("'package' argument must be a debian folder: {package}")

        package_info = self.packages[package]
        repo_path = package_info["repo_path"]
        repo_name = package_info["repo_name"]
        debian_dir = package_info["debian_dir"]
        packages = package_info['packages']

        if self.incremental and self._can_skip_build(repo_path, package_info['dependencies']):
            logger.info(f"[incremental] Skipping {packages}: source unchanged")
            self._stats_skipped += 1
            return

        package_temp_dir = os.path.join(self.DEB_OUT_TEMP_DIR, repo_name)

        create_new_directory(package_temp_dir, delete_if_exists=True)

        logger.debug(f"Building deb packages : {packages} listed in the Control file")

        os.chdir(repo_path)

        if self.IS_PREPARE_SOURCE:
            logger.debug(f"generating dsc for {packages}...")
            cmd = f"sbuild --source --no-arch-all --no-arch-any  -d {self.CHROOT_NAME} --build-dir {package_temp_dir}"
        else:
            cmd = f"sbuild -A --arch=arm64 -d {self.CHROOT_NAME} --no-run-lintian --build-dir {package_temp_dir} --build-dep-resolver=apt"

        if self.DEB_OUT_DIR_APT:
            build_deb_package_gz(self.DEB_OUT_DIR, start_server=False) # Rebuild Packages file
            cmd += f" --extra-repository=\"{self.DEB_OUT_DIR_APT}\""

        if self.DEBIAN_INSTALL_DIR_APT:
            cmd += f" --extra-repository=\"{self.DEBIAN_INSTALL_DIR_APT}\""

        if self.APT_SERVER_CONFIG:
            for config in self.APT_SERVER_CONFIG:
                if config.strip():
                    cmd += f" --extra-repository=\"{config.strip()}\""

        # Add ROS repository only if the chroot does not already have ros2-apt-source installed.
        # ros2-apt-source installs /usr/share/ros-apt-source/ros2.sources (and symlinks it into
        # sources.list.d). Adding the same URL again via --extra-repository causes APT to error
        # with "Conflicting values set for option Trusted".
        if self.TECH_DEBIAN_MIRROR:
            chroot_path = f"{self.CHROOT_DIR}/{self.CHROOT_NAME}"
            ros_apt_source_file = os.path.join(chroot_path, "usr", "share", "ros-apt-source", "ros2.sources")
            if os.path.exists(ros_apt_source_file):
                logger.debug("ros2-apt-source already installed in chroot, skipping --extra-repository")
            else:
                cmd += f" --extra-repository=\"deb [arch=arm64 trusted=yes] {self.TECH_DEBIAN_MIRROR} noble main\""
                logger.debug("Using trusted=yes for ROS repository (ros2-apt-source not installed in chroot)")

        # Resolve directory symlinks in repo_path so that dpkg-source includes
        # the actual content in the source tarball (symlink targets would be
        # broken inside the sbuild chroot).
        resolved_symlinks = []
        for entry in os.scandir(repo_path):
            if entry.is_symlink():
                try:
                    original_target = os.readlink(entry.path)   # preserve original (possibly relative) target
                    real_target = os.path.realpath(entry.path)  # absolute resolved path
                    if os.path.isdir(real_target) and os.access(real_target, os.R_OK):
                        logger.debug(f"Resolving symlink for sbuild: {entry.path} -> {real_target}")
                        os.remove(entry.path)
                        shutil.copytree(real_target, entry.path, symlinks=True)
                        resolved_symlinks.append((entry.path, original_target))
                    else:
                        logger.warning(f"Skipping symlink {entry.path}: target not accessible or not a directory")
                except (OSError, IOError) as e:
                    logger.warning(f"Failed to resolve symlink {entry.path}: {e}")

        fix_debian_permissions(repo_path)

        try:
            run_command(cmd, cwd=repo_path)
        except Exception as e:
            logger.error(f"Failed to build {packages}: {e}")
            print_build_logs(package_temp_dir)
            raise PackageBuildError(f"Failed to build {packages}: {e}")
        finally:
            # Restore symlinks after build
            for (link_path, original_target) in resolved_symlinks:
                try:
                    if os.path.exists(link_path) and not os.path.islink(link_path):
                        shutil.rmtree(link_path)
                        os.symlink(original_target, link_path)
                        logger.debug(f"Restored symlink: {link_path} -> {original_target}")
                except Exception as restore_error:
                    logger.error(f"Failed to restore symlink {link_path}: {restore_error}")
                    # Continue with other symlinks even if one fails

        copied_files = self.reorganize_outputs_in_oss_prop(repo_path, package_temp_dir)

        if self.incremental:
            source_hash = self._compute_source_hash(repo_path)
            old_hash = (self.build_state.get(str(repo_path)) or {}).get('source_hash')
            self.build_state[str(repo_path)] = {
                'repo_name': repo_name,
                'source_hash': source_hash,
                'last_built': datetime.now(timezone.utc).isoformat(),
                'output_debs': copied_files,
            }
            self._save_build_state()
            self.rebuilt_packages.update(packages)
            if old_hash != source_hash:
                self.source_changed_packages.update(packages)

        self._stats_built.append(repo_name)

        # Clean up dpkg-source artifacts (*.tar.gz, *.tar.xz, *.dsc) left in the
        # parent directory of the source tree by dpkg-buildpackage / sbuild.
        source_pkg_name = repo_name
        control_file = debian_dir / "control"
        if control_file.exists():
            with open(control_file) as _cf:
                for _line in _cf:
                    if _line.startswith("Source:"):
                        source_pkg_name = _line.split(":", 1)[1].strip()
                        break
        parent_dir = repo_path.parent
        for artifact in parent_dir.glob(f"{source_pkg_name}_*"):
            if artifact.suffix in ('.gz', '.xz', '.dsc') and artifact.is_file():
                artifact.unlink()
                logger.debug(f"Removed dpkg-source artifact: {artifact}")

        logger.info(f"{packages} built successfully!")

    def log_build_summary(self):
        total = len(self.packages)
        built = len(self._stats_built)
        skipped = self._stats_skipped
        if self._start_time:
            elapsed = (datetime.now(timezone.utc) - self._start_time).total_seconds()
            mins, secs = divmod(elapsed, 60)
            elapsed_str = f"{int(mins)}m {secs:.1f}s" if mins >= 1 else f"{secs:.1f}s"
        else:
            elapsed_str = "N/A"
        logger.info("=" * 60)
        logger.info(f"Build summary: {total} packages total | {built} built | {skipped} skipped | elapsed {elapsed_str}")
        if self._stats_built:
            logger.info(f"Built packages ({built}):")
            for name in self._stats_built:
                logger.info(f"  - {name}")
        else:
            logger.info("No packages were built (all up to date)")
        logger.info("=" * 60)

    def build_all_packages(self):
        """Builds all packages in dependency order."""
        sorted_order = self.detect_cycle()  # Ensures dependencies are resolved before building
        for pkg in sorted_order:
            for package in self.packages:
                if not self.packages[package]['visited']:
                    if pkg in self.packages[package]['packages']:
                        self.build_package(package)
                        self.packages[package]['visited'] = True
                        break

    def build_specific_package(self, package_name):
        """
        Builds a specific package along with its dependencies first.

        Args:
        -----
        - package_name (str): The name of the package to build.

        Returns:
        --------

        Raises:
        -------
        - PackageNotFoundError: If the package is not found in the packages list.
        - PackageBuildError: If the package fails to build (raising up from the build_package function).
        """

        for package in self.packages:
            if not self.packages[package]['visited']:
                if package_name in self.packages[package]['packages']:
                    for dep in self.packages[package]['dependencies']:
                        self.packages[package]['visited'] = True
                        logger.debug(f"Building dependency: {dep}")

                        try:
                            self.build_specific_package(dep)
                        except PackageNotFoundError as e:
                            # Its possible that a dependency is not found in the packages list,
                            # yet the build is successful. Catch the exception, and continue.
                            logger.error(f"Failed to find dependency: {e}")
                        except PackageBuildError as e:
                            # If the dependency build fails, raise the exception up.
                            logger.error(f"Failed to build dependency: {e}")
                            raise e

                    # let any potential exception from build_package raise up to the caller
                    self.build_package(package)
                    return

        # If we reach here, the package was not found in the packages list.
        raise PackageNotFoundError(f"Package '{package_name}' not found.")
