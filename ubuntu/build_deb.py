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
from pathlib import Path
from queue import Queue
from collections import defaultdict, deque
from constants import *
from helpers import check_if_root, logger, run_command, check_and_append_line_in_file, create_new_directory, build_deb_package_gz, run_command_for_result
from deb_organize import search_manifest_map_for_path

class PackageBuilder:
    def __init__(self, MOUNT_DIR, SOURCE_DIR, APT_SERVER_CONFIG, CHROOT_NAME, \
    MANIFEST_MAP=None, TEMP_DIR=None, DEB_OUT_DIR=None, DEB_OUT_DIR_APT=None, DEBIAN_INSTALL_DIR=None, \
    DEBIAN_INSTALL_DIR_APT=None, IS_CLEANUP_ENABLED=True, IS_PREPARE_SOURCE=False):
        """
        Initializes the PackageBuilder instance.

        Args:
        -----
        - MOUNT_DIR (str): The directory where the chroot environment will be mounted.
        - SOURCE_DIR (str): The source directory containing the packages to build.
        - APT_SERVER_CONFIG (list): Configuration for the APT server.
        - CHROOT_NAME (str): The name of the chroot environment.
        - MANIFEST_MAP (dict, optional): A mapping of package paths to their properties.
        - TEMP_DIR (str, optional): Temporary directory for building packages.
        - DEB_OUT_DIR (str, optional): Output directory for built Debian packages.
        - DEB_OUT_DIR_APT (str, optional): Output directory for APT repository.
        - DEBIAN_INSTALL_DIR (str, optional): Directory for Debian installation files.
        - DEBIAN_INSTALL_DIR_APT (str, optional): Directory for APT installation files.
        - IS_CLEANUP_ENABLED (bool, optional): Flag to enable cleanup of the mount directory.
        - IS_PREPARE_SOURCE (bool, optional): If True, prepares the source directory before building. Defaults to False.
        """
        if not check_if_root():
            logger.error('Please run this script as root user.')
            exit(1)
        self.SOURCE_DIR = SOURCE_DIR
        self.DEB_OUT_DIR = DEB_OUT_DIR
        self.MOUNT_DIR = Path(MOUNT_DIR)
        self.APT_SERVER_CONFIG = APT_SERVER_CONFIG
        self.CHROOT_NAME = CHROOT_NAME

        self.DIST = "noble"

        self.packages = {}

        self.MANIFEST_MAP = MANIFEST_MAP

        self.TEMP_DIR = TEMP_DIR

        self.IS_CLEANUP_ENABLED = IS_CLEANUP_ENABLED

        self.DEB_OUT_DIR = DEB_OUT_DIR
        self.DEBIAN_INSTALL_DIR = DEBIAN_INSTALL_DIR
        self.DEB_OUT_DIR_APT = DEB_OUT_DIR_APT
        self.DEBIAN_INSTALL_DIR_APT = DEBIAN_INSTALL_DIR_APT
        self.IS_PREPARE_SOURCE = IS_PREPARE_SOURCE

        self.generate_schroot_config()

    def generate_schroot_config(self):
        """
        Generates the schroot configuration for the specified chroot environment.

        Raises:
        -------
        - Exception: If there is an error creating the schroot environment.
        """
        logger.info(f"Generating schroot configuration for {self.CHROOT_NAME} at {self.MOUNT_DIR}")
        if not os.path.exists(os.path.join(self.MOUNT_DIR, "root")):
            out = run_command_for_result(f"sbuild-createchroot --arch=arm64 --chroot-suffix={self.CHROOT_NAME} --components=main,universe {self.DIST} {self.MOUNT_DIR} http://ports.ubuntu.com")
            if out['returncode'] != 0:
                if self.IS_CLEANUP_ENABLED:
                    cleanup_directory(self.MOUNT_DIR)
                raise Exception(f"Error creating schroot environment: {out['output']}")
            else:
                logger.info(f"Schroot environment {self.CHROOT_NAME} created successfully.")
        else:
            logger.warning(f"Schroot environment {self.CHROOT_NAME} already exists at {self.MOUNT_DIR}. Skipping creation.")

    def load_packages(self):
        """Load package metadata from build_config.py and fetch dependencies from control files."""
        for root, dirs, files in os.walk(self.SOURCE_DIR):
            dirs[:] = [d for d in dirs if d != '.git']
            if 'debian' in dirs:
                debian_dir = Path(os.path.join(root, 'debian'))
                pkg_names, dependencies = self.get_packages_from_control(debian_dir / "control")

                self.packages[str(debian_dir)] = {
                    "debian_dir": debian_dir,
                    "repo_path": Path(root),
                    "dependencies": dependencies,
                    "packages": pkg_names,
                    "visited": False
                }

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

    def reorganize_deb_in_oss_prop(self, repo_path):
        """
        Reorganizes built .deb files into the appropriate output directory based on the manifest map.

        Args:
        -----
        - repo_path (Path): The path to the repository containing the built packages.
        """
        oss_or_prop = search_manifest_map_for_path(self.MANIFEST_MAP, self.SOURCE_DIR, repo_path)
        for root, dirs, files in os.walk(self.TEMP_DIR):
            for file in files:
                if file.endswith('.deb'):
                    pkg_name = file.split('_')[0]
                    pkg_dir = os.path.join(self.DEB_OUT_DIR, oss_or_prop, pkg_name)
                    create_new_directory(pkg_dir, delete_if_exists=False)
                    shutil.move(os.path.join(root, file), os.path.join(pkg_dir, file))

    def reorganize_dsc_in_oss_prop(self, repo_path):
        """
        Reorganizes .dsc files into the appropriate output directory based on the manifest map.

        Args:
        -----
        - repo_path (Path): The path to the repository containing the .dsc files.
        """
        oss_or_prop = search_manifest_map_for_path(self.MANIFEST_MAP, self.SOURCE_DIR, repo_path)
        parent_dir = repo_path.parent

        for file in os.listdir(parent_dir):
            file_path = parent_dir / file
            if file_path.is_file() and file.endswith('.dsc'):
                pkg_name = file.split('_')[0]
                pkg_dir = os.path.join(self.DEB_OUT_DIR, oss_or_prop, pkg_name)
                create_new_directory(pkg_dir, delete_if_exists=False)
                shutil.move(str(file_path), os.path.join(pkg_dir, file))

    def build_package(self, package):
        """
        Builds a package inside the chroot environment.

        Args:
        -----
        - package (str): The name of the package to build.

        Raises:
        -------
        - Exception: If there is an error during the build process.
        """
        package_info = self.packages[package]

        repo_path = package_info["repo_path"]
        debian_dir = package_info["debian_dir"]
        packages = package_info['packages']

        logger.info(f"Building {packages}...")

        os.chdir(repo_path)
        create_new_directory(self.TEMP_DIR)
        if self.IS_PREPARE_SOURCE:
            logger.info(f"generating dsc for {packages}...")
            cmd = f"sbuild --source --no-arch-all --no-arch-any  -d {self.DIST}-arm64{self.CHROOT_NAME} --build-dir {self.TEMP_DIR} "

        else:
            cmd = f"sbuild -A --arch=arm64 -d {self.DIST}-arm64{self.CHROOT_NAME} --no-run-lintian \
            --build-dir {self.TEMP_DIR} --build-dep-resolver=apt"

        if self.DEB_OUT_DIR_APT:
            build_deb_package_gz(self.DEB_OUT_DIR, start_server=False) # Rebuild Packages file
            cmd += f" --extra-repository=\"{self.DEB_OUT_DIR_APT}\""

        if self.DEBIAN_INSTALL_DIR_APT:
            cmd += f" --extra-repository=\"{self.DEBIAN_INSTALL_DIR_APT}\""

        if self.APT_SERVER_CONFIG:
            for config in self.APT_SERVER_CONFIG:
                if config.strip():
                    cmd += f" --extra-repository=\"{config.strip()}\""

        run_command(cmd, cwd=repo_path)

        self.reorganize_dsc_in_oss_prop(repo_path)
        self.reorganize_deb_in_oss_prop(repo_path)

        logger.info(f"{packages} built successfully!")

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
        - bool: True if the package was found and built, False otherwise.
        """
        found = False
        for package in self.packages:
            if not self.packages[package]['visited']:
                if package_name in self.packages[package]['packages']:
                    for dep in self.packages[package]['dependencies']:
                        self.build_specific_package(dep)
                        self.packages[package]['visited'] = True
                    self.build_package(package)
                    found = True

        if not found:
            logger.error(f"Package '{package_name}' not found.")
            return False
