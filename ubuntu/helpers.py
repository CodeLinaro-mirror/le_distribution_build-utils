# Copyright (c) Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause-Clear
"""
helper.py

This module provides utilities for managing Debian package builds and related operations.
It includes functions for executing shell commands, managing files and directories,
logging, and setting up a local APT server.
"""

import os
import stat
import shlex
import random
import shutil
import logging
import subprocess
import glob
import json
import re
import requests
from pathlib import Path
from git import Repo
from apt_server import AptServer
from constants import TERMINAL, HOST_FS_MOUNT, LINUX_MODULES_DEB
from color_logger import logger
import tempfile

def check_if_root() -> bool:
    """
    Checks if the script is being run with root privileges.

    Returns:
    --------
    - bool: True if the script is run as root, False otherwise.
    """
    return os.geteuid() == 0

def check_and_append_line_in_file(file_path, line_to_check, append_if_missing=False):
    """
    Checks if a specific line exists in a file and appends it if it is missing.

    Args:
    -----
    - file_path (str): The path to the file to check.
    - line_to_check (str): The line to check for in the file.
    - append_if_missing (bool): If True, appends the line to the file if it is missing.

    Returns:
    --------
    - bool: True if the line exists or was appended, False if the line does not exist and append_if_missing is False.
    """
    if not os.path.exists(file_path):
        logger.error(f"{file_path} does not exist.")
        exit(1)

    with open(file_path, "r") as file:
        lines = file.readlines()

    for line in lines:
        if line.strip() == line_to_check.strip():
            return True

    if append_if_missing:
        with open(file_path, "a") as file:
            file.write(f"\n{line_to_check}\n")
        return True

    return False


def extract_vmlinux(deb_dir, deb_file_regex, vmlinux_filename, out_dir):
    """
    Extracts the vmlinux file from a Debian package and places it in the output directory.

    Args:
    -----
    - deb_dir (str): Directory containing the .deb files.
    - deb_file_regex (str): Regex pattern to match the .deb file.
    - vmlinux_filename (str): Name of the vmlinux file to extract.
    - out_dir (str): Directory to copy the extracted vmlinux file to.

    Raises:
    -------
    - Exception: If no matching .deb files found, or if errors occur during extraction.
    """
    vmlinux_path = os.path.join(out_dir, vmlinux_filename)
    if os.path.exists(vmlinux_path):
        logger.info(f"Removing existing vmlinux at {vmlinux_path}")
        os.remove(vmlinux_path)

    # Step 0: Check if the .deb file exists
    files = glob.glob(os.path.join(deb_dir, deb_file_regex))
    if len(files) == 0:
        logger.error(f"Error: No files matching {deb_file_regex} exist in {deb_dir}")
        raise Exception(f"No files matching {deb_file_regex} found")

    # Step 1: Extract the .deb package to a temporary directory
    deb_file = files[0]  # Assuming only one file matches the regex
    try:
        temp_dir = tempfile.mkdtemp()
        logger.debug(f'Temp path for vmlinux extraction: {temp_dir}')
        subprocess.run(["dpkg-deb", '-x', deb_file, temp_dir], check=True)

        # Step 2: Find the vmlinux file within the temporary directory
        file_path = None
        for root, _, files in os.walk(temp_dir):
            if vmlinux_filename in files:
                file_path = os.path.join(root, vmlinux_filename)
                break

        # Step 3: Copy the vmlinux file to the output directory
        if file_path:
            try:
                shutil.copy(file_path, vmlinux_path)
                os.chmod(vmlinux_path, 0o644)
                logger.info(f"{vmlinux_filename} has been copied to {vmlinux_path}")
            except Exception as e:
                logger.error(f"Error copying file {file_path}")
                logger.error(f"Resulted in error: {e}")
        else:
            logger.error(f"{vmlinux_filename} not found in {deb_file}")

    except Exception as e:
        logger.error(f"Error extracting vmlinux: {e}")
        raise
    finally:
        # Step 4: Clean up the temporary directory
        if temp_dir:
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temporary directory {temp_dir}")

def parse_debs_manifest(manifest_path):
    """
    Parses a manifest file and returns a dictionary of module names and their corresponding versions.
    """
    DEBS = []
    user_manifest = Path(manifest_path)
    if not user_manifest.is_file() or not user_manifest.name.endswith('.manifest'):
        raise ValueError(f"Provided manifest path '{user_manifest}' is not a valid '.manifest' file.")
    if os.path.isfile(manifest_path):
        with open(manifest_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = list(line.split())
                    DEBS.append({
                        'package': parts[0],
                        'version': parts[1] if len(parts) > 1 else None,
                    })
            return DEBS
    else:
        print(f"Manifest file {manifest_path} not found.")
        return None

def run_command(command, check=True, get_object=False, cwd=None, env=None):
    """
    Executes a shell command and returns the output, logging any errors.

    Args:
    -----
    - command (str): The shell command to execute.
    - check (bool): If True, raises an exception on a non-zero exit code.
    - get_object (bool): If True, returns the result object instead of the output string.
    - cwd (str): The working directory to execute the command in.

    Returns:
    --------
    - str: The standard output of the command.

    Raises:
    -------
    - Exception: If the command fails and check is True.
    """

    logger.debug(f'Running command: {command}')

    try:
        result = subprocess.run(command, shell=True, check=check, capture_output=True, text=True, cwd=cwd, env=env)

    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed with return value: {e.returncode}")
        logger.error(f"stderr: {e.stderr.strip() if e.stderr else str(e)}")
        logger.error(f"stdout: {e.stdout.strip()}")
        raise Exception(e)

    stderr = result.stderr.strip()
    if stderr:
        if result.returncode == 0:
            logger.debug(f"Successful return value, yet there is content in stderr: {stderr}")
        else:
            logger.error(f"Error: {stderr}")

    return result.stdout.strip()

def run_command_for_result(command):
    """
    Executes a shell command and returns the output and return code in a dictionary.

    Args:
    -----
    - command (str): The shell command to execute.

    Returns:
    --------
    - dict: A dictionary containing:
        - "output" (str): The standard output of the command.
        - "returncode" (int): The return code of the command.
    """
    command = command.strip()
    logger.debug(f'Running for result: {command}')
    try:
        result = subprocess.check_output(command, shell=True, stderr=subprocess.sys.stdout)
        return {"output": result.decode("utf-8").strip(), "returncode": 0}
    except subprocess.CalledProcessError as e:
        return {"output": e.output.decode("utf-8", errors="ignore").strip(), "returncode": e.returncode}

def set_env(key, value):
    """
    Sets an environment variable.

    Args:
    -----
    - key (str): The name of the environment variable.
    - value (str): The value to set for the environment variable.
    """
    os.environ[str(key)] = str(value)

def cleanup_directory(dirname):
    """
    Removes a directory and its contents.

    Args:
    -----
    - dirname (str): The path to the directory to clean up.

    Raises:
    -------
    - Exception: If an error occurs while trying to remove the directory.
    """
    import subprocess as _sp
    try:
        if os.path.exists(dirname):
            try:
                shutil.rmtree(dirname)
            except PermissionError:
                logger.debug(
                    f"shutil.rmtree failed on {dirname} (mapped UIDs), "
                    "falling back to chmod+rm -rf"
                )
                _sp.run(
                    f"chmod -R a+rwX {dirname} 2>/dev/null; "
                    f"find {dirname} -type d -exec chmod a+rwx {{}} \\; 2>/dev/null; "
                    f"true",
                    shell=True
                )
                result = _sp.run(
                    ["rm", "-rf", dirname],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    logger.warning(
                        f"Could not fully remove {dirname} (some files owned by "
                        "subuid-mapped UIDs). Leftover files will be cleaned up "
                        "by the mmdebstrap customize-hook on the next run."
                    )
    except Exception as e:
        logger.error(f"Error cleaning directory {dirname}: {e}")
        raise Exception(e)

def cleanup_file(file_path):
    """
    Deletes a specified file.

    Args:
    -----
    - file_path (str): The path to the file to delete.

    Raises:
    -------
    - Exception: If an error occurs while trying to delete the file.
    """

    logger.debug(f"Cleaning file {file_path}")

    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logger.error(f"Error cleaning file {file_path}: {e}")
        raise Exception(e)

def create_new_directory(dirname, delete_if_exists=True):
    """
    Creates a new directory, optionally deleting it if it already exists.

    Args:
    -----
    - dirname (str): The path to the directory to create.
    - delete_if_exists (bool): If True, deletes the directory if it already exists.

    Raises:
    -------
    - SystemExit: If an error occurs while creating the directory.
    """
    try:
        if os.path.exists(dirname):
            # Check if the directory exists, if so delete it
            if delete_if_exists:
                cleanup_directory(dirname)
        os.makedirs(dirname, exist_ok=True)
    except Exception as e:
        logger.error(f"Error creating directory {dirname}: {e}")
        exit(1)

def create_new_file(filepath, delete_if_exists=True) -> str:
    """
    Creates a new file, optionally deleting it if it already exists.

    Args:
    -----
    - filepath (str): The path to the file to create.
    - delete_if_exists (bool): If True, deletes the file if it already exists.

    Returns:
    --------
    - str: The path to the created file.

    Raises:
    -------
    - SystemExit: If an error occurs while creating the file.
    """
    try:
        if os.path.exists(filepath):
            # Check if the file exists, if so don't do anything
            return filepath
        # Create the destination directory
        with open(filepath, 'w') as f: pass
        return filepath
    except Exception as e:
        logger.error(f"Error creating file {filepath}: {e}")
        exit(1)

def print_build_logs(directory):
    """
    Prints the contents of build log files in a specified directory.

    Args:
    -----
    - directory (str): The path to the directory containing build logs.
    """
    logger.info("===== Build Logs Start ======")
    build_logs = []
    for entry in os.listdir(directory):
        full_path = os.path.join(directory, entry)
        if (os.path.islink(full_path) and entry.endswith(".build")) or entry.endswith(".mmdebstrap.build"):
            build_logs.append(entry)
    for entry in build_logs:
        full_path = os.path.join(directory, entry)
        logger.info(f"===== {full_path} =====")
        content = None
        with open(full_path, 'r') as log_file:
            content = log_file.read()
        logger.error(content)
    logger.info("=====  Build Logs End  ======")

def start_local_apt_server(dir):
    """
    Starts a local APT server in the specified directory and returns the APT repository line.

    Args:
    -----
    - dir (str): The directory to serve as the APT repository.

    Returns:
    --------
    - str: The APT repository line to add to sources.list.
    """

    server = AptServer(directory=dir, port=random.randint(7500, 8500))
    server.start()

    return f"deb [trusted=yes arch=arm64] http://localhost:{server.port} stable main"

def build_deb_package_gz(dir, start_server=True) -> str:
    """
    Builds a Debian package and creates a compressed Packages file, optionally starting a local APT server.

    Args:
    -----
    - dir (str): The directory where the package is built.
    - start_server (bool): If True, starts a local APT server after building the package.

    Returns:
    --------
    - str: The APT repository line if a server is started, None otherwise.

    Raises:
    -------
    - Exception: If an error occurs while creating the Packages file.
    """

    packages_dir = os.path.join(dir, 'dists', 'stable', 'main', 'binary-arm64')
    packages_path = os.path.join(packages_dir, "Packages")

    try:
        os.makedirs(packages_dir, exist_ok=True)

        cmd = f'dpkg-scanpackages -m . > {packages_path}'

        result = subprocess.run(cmd, shell=True, cwd=dir, check=False, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Error running : {cmd}")
            logger.error(f"stdout : {result.stdout}")
            logger.error(f"stderr : {result.stderr}")

            raise Exception(result.stderr)

        # Even with a successful exit code, dpkg-scanpackages still outputs the number of entries written to stderr
        logger.debug(result.stderr.strip())


        cmd = f"gzip -k -f {packages_path}"
        result = subprocess.run(cmd, shell=True, cwd=dir, check=False, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Error running : {cmd}")
            logger.error(f"stdout : {result.stdout}")
            logger.error(f"stderr : {result.stderr}")

            raise Exception(result.stderr)

        logger.debug(f"Packages file created at {packages_path}.gz")

    except Exception as e:
        logger.error(f"Error creating Packages file in {dir} : {e}")
        raise Exception(e)

    if start_server:
        return start_local_apt_server(dir)
    return None

def pull_debs_wget(manifest_file_path, out_dir,DEBS_to_download_list,base_url):
    """
    Downloads Debian packages from a remote repository using wget.

    Args:
    -----
    - manifest_file_path (str): Path to the manifest file containing package versions.
    - out_dir (str): Directory where downloaded packages will be saved.
    - DEBS_to_download_list (list): List of package name prefixes to download.
    - base_url (str): Base URL of the repository to download packages from.

    Returns:
    --------
    - int: Number of packages successfully downloaded.

    Raises:
    -------
    - Exception: If an error occurs while downloading packages.
    """
    # Read manifest file
    # Parse manifest into a dictionary
    with open(manifest_file_path, 'r') as f:
        manifest_text = f.read()

    # Parse manifest into a dictionary
    version_map = {}
    for line in manifest_text.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 2:
            name, version = parts[0], parts[1]
            version_map[name] = version


    # Generate wget links and download
    os.makedirs(out_dir, exist_ok=True)
    #logger.info(f"version map {version_map}...")

    matches = {k: v for k, v in version_map.items() if 'linux-modules' in k}

    # Get the first match (you can change this logic if needed)
    first_match_value = next(iter(matches.values()))
    first_match_key = next(iter(matches))

    prefix = "linux-modules-"
    suffix = "-qcom"

    if first_match_key.startswith(prefix) and first_match_key.endswith(suffix):
        # extract version from package name
        name_suffix = first_match_key[len(prefix):-len(suffix)]
        # Construct new key and update version_map
        linux_qcom_tools_suffix = f"linux-qcom-tools-{name_suffix}"
        version_map[linux_qcom_tools_suffix] = first_match_value
    else:
        logger.warning(
            f"Can't find linux-modules key: {first_match_key}"
        )
    for module in DEBS_to_download_list:
        for name, version in version_map.items():
            if name.startswith(module):
                first_letter = name[0]
                deb_name = f"{name}_{version}_arm64.deb"
                #url = f"{base_url}/{first_letter}/{name}/{deb_name}"
                url = f"{base_url}/{first_letter}/{LINUX_MODULES_DEB.split('/')[0]}/{deb_name}"
                output_path = os.path.join(out_dir, LINUX_MODULES_DEB.split('/')[0],deb_name )
                create_new_directory(os.path.join(out_dir,LINUX_MODULES_DEB.split('/')[0]), delete_if_exists=False)
                # Construct wget command
                wget_cmd = ["wget", "--no-check-certificate", url, "-O", output_path]
                try:
                    logger.info(f"Downloading {url}...")
                    subprocess.run(wget_cmd, check=True)
                    logger.info(f"Saved to {output_path}")
                except subprocess.CalledProcessError as e:
                    logger.error(f"error: Failed to download {url}: {e}")
                # break # Stop after first match

def resolve_manifest_path(manifest_path, workspace, IMAGE_TYPE):
    if manifest_path is None:
        logger.warning("Manifest path is None. Skipping resolution.")
        return None

    if manifest_path.startswith(("http://", "https://")):
        logger.info(f"Downloading manifest from URL: {manifest_path}")
        local_manifest = os.path.join(workspace, f"base_{IMAGE_TYPE}.manifest")

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(f"{manifest_path}/{IMAGE_TYPE}.manifest", timeout=30,verify = False)
                response.raise_for_status()

                # Basic validation: check if content looks like a manifest
                content = response.content.decode('utf-8')
                if not content.strip():
                    raise ValueError("Downloaded manifest is empty")

                with open(local_manifest, "w") as f:
                    f.write(content)
                logger.info(f"Manifest downloaded to {local_manifest}")
                return local_manifest
            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Download attempt {attempt + 1} failed: {e}. Retrying...")
                    continue
                raise RuntimeError(f"Failed to download manifest after {max_retries} attempts: {e}")
    else:
        abs_manifest = os.path.abspath(manifest_path)
        if os.path.isfile(abs_manifest):
            return abs_manifest
        else:
            raise FileNotFoundError(f"Manifest file not found: {abs_manifest}")

def fix_debian_permissions(root: str = ".") -> None:
    """
    Normalizes permissions under every debian/ directory found beneath root.
    Removes the executable bit from all regular files (maxdepth 2 from the
    debian/ dir), then restores +x on debian/rules so dpkg-buildpackage can
    execute it.
    """
    root_path = Path(root)
    no_exec = ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    all_exec = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH

    for rules in root_path.rglob("debian/rules"):
        if not rules.is_file():
            continue
        debian_dir = rules.parent
        for file in debian_dir.rglob("*"):
            if not file.is_file():
                continue
            if len(file.relative_to(debian_dir).parts) > 2:
                continue
            if file == rules:
                continue
            file.chmod(file.stat().st_mode & no_exec)
        rules.chmod(rules.stat().st_mode | all_exec)
        logger.debug(f"Fixed debian permissions in {debian_dir}")

def download_ros2_apt_source_deb(dest_dir: str, distro: str) -> str:
    """
    Downloads the latest ros2-apt-source .deb from GitHub Releases.

    Args:
    -----
    - dest_dir (str): Directory to download the .deb file into.
    - distro (str): Ubuntu distro codename (e.g. "noble").

    Returns:
    --------
    - str: Full path to the downloaded .deb file.

    Raises:
    -------
    - RuntimeError: If the GitHub API request or download fails.
    - ValueError: If the version string returned by the API is unexpected.
    """
    _FALLBACK_ROS_APT_VERSION = "1.2.0"
    api_result = subprocess.run(
        ["curl", "-sL",
         "https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest"],
        capture_output=True, text=True, timeout=30,
    )
    ros_apt_version = _FALLBACK_ROS_APT_VERSION
    if api_result.returncode != 0:
        logger.warning(f"GitHub API request failed, using fallback version {_FALLBACK_ROS_APT_VERSION}: {api_result.stderr}")
    else:
        try:
            tag = json.loads(api_result.stdout).get("tag_name", "").strip()
        except json.JSONDecodeError:
            tag = ""
        if re.match(r'^[\w.\-]+$', tag):
            ros_apt_version = tag
        else:
            logger.warning(f"Unexpected version string from GitHub API: {tag!r}, using fallback version {_FALLBACK_ROS_APT_VERSION}")

    deb_name = f"ros2-apt-source_{ros_apt_version}.{distro}_all.deb"
    deb_url = (
        "https://github.com/ros-infrastructure/ros-apt-source/releases/download"
        f"/{ros_apt_version}/{deb_name}"
    )
    fd, deb_path = tempfile.mkstemp(suffix=f"_{deb_name}", dir=dest_dir)
    os.close(fd)
    dl_result = subprocess.run(
        ["curl", "-fLSs", "--retry", "3", "-o", deb_path, deb_url],
        capture_output=True, text=True, timeout=120,
    )
    if dl_result.returncode != 0:
        os.unlink(deb_path)
        raise RuntimeError(f"Failed to download {deb_url}: {dl_result.stderr}")

    return deb_path
