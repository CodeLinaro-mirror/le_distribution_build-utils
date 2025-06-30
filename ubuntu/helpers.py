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
from git import Repo
from apt_server import AptServer
from constants import TERMINAL, HOST_FS_MOUNT

class ColorFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[94m', # Blue
        'INFO': '\033[92m', # Green
        'WARNING': '\033[93m', # Yellow
        'ERROR': '\033[91m', # Red
        'CRITICAL': '\033[95m', # Magenta
    }
    RESET = '\033[0m'

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        message = super().format(record)
        return f"{log_color}{message}{self.RESET}"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s || %(levelname)s || %(message)s",
    datefmt="%H:%M:%S"
)

handler = logging.StreamHandler()
formatter = ColorFormatter('%(levelname)s: %(message)s')
handler.setFormatter(formatter)

logger = logging.getLogger("DEB-BUILD")
logger.addHandler(handler)

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
    
    lines = []
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


def run_command(command, check=True, get_object=False, cwd=None):
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
    logger.info(f'Running: {command}')
    try:
        if not cwd:
            result = subprocess.run(command, shell=True, check=check, capture_output=True, text=True)
        else:
            result = subprocess.run(command, shell=True, check=check, capture_output=True, text=True, cwd=cwd)
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {e.stderr.strip() if e.stderr else str(e)}")
        raise Exception(e)

    if result.stderr:
        logger.error(f"Error: {result.stderr.strip()}")
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
    logger.info(f'Running for result: {command}')
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
    try:
        if os.path.exists(dirname):
            shutil.rmtree(dirname)
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
        # Create the destination directory
        os.makedirs(dirname, exist_ok=not delete_if_exists)
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

def mount_img(IMG_PATH, MOUNT_DIR, MOUNT_HOST_FS=False, MOUNT_IMG=True):
    """
    Mounts an image file to a specified directory, with optional host filesystem mounts.

    Args:
    -----
    - IMG_PATH (str): The path to the image file to mount.
    - MOUNT_DIR (str): The directory to mount the image to.
    - MOUNT_HOST_FS (bool): If True, mounts the host filesystem directories.
    - MOUNT_IMG (bool): If True, mounts the image file.
    """
    if MOUNT_IMG:
        create_new_directory(MOUNT_DIR)
        run_command(f"mount {IMG_PATH} {MOUNT_DIR}")
    if MOUNT_HOST_FS:
        for direc in HOST_FS_MOUNT:
            run_command(f"mount --bind /{direc} {MOUNT_DIR}/{direc}")

def umount_dir(MOUNT_DIR, UMOUNT_HOST_FS=False):
    """
    Unmounts a specified directory and optionally unmounts host filesystem mounts.

    Args:
    -----
    - MOUNT_DIR (str): The directory to unmount.
    - UMOUNT_HOST_FS (bool): If True, unmounts the host filesystem directories.
    """
    if UMOUNT_HOST_FS:
        for direc in HOST_FS_MOUNT:
            try:
                run_command(f"umount -l {MOUNT_DIR}/{direc}")
            except:
                logger.warning(f"Failed to unmount {MOUNT_DIR}/{direc}. Not mounted or busy. Ignoring.")
    try:
        run_command(f"umount -l {MOUNT_DIR}")
    except:
        logger.warning(f"Failed to unmount {MOUNT_DIR}. Not mounted or busy. Ignoring.")

def change_folder_perm_read_write(DIR):
    """
    Changes permissions of a directory and its contents to allow read and write access.

    Args:
    -----
    - DIR (str): The path to the directory whose permissions are to be changed.

    Raises:
    -------
    - Exception: If an error occurs while changing permissions.
    """
    try:
        # Change permissions for the root folder itself
        current_permissions = os.stat(DIR).st_mode
        new_permissions = current_permissions

        if current_permissions & stat.S_IWUSR:
            new_permissions |= stat.S_IWOTH

        if current_permissions & stat.S_IXUSR:
            new_permissions |= stat.S_IXOTH

        os.chmod(DIR, new_permissions)

        for root, dirs, files in os.walk(DIR):
            for dir_ in dirs:
                dir_path = os.path.join(root, dir_)
                current_permissions = os.stat(dir_path).st_mode
                new_permissions = current_permissions

                if current_permissions & stat.S_IWUSR:
                    new_permissions |= stat.S_IWOTH
                if current_permissions & stat.S_IXUSR:
                    new_permissions |= stat.S_IXOTH

                os.chmod(dir_path, new_permissions)

            for file in files:
                file_path = os.path.join(root, file)
                current_permissions = os.stat(file_path).st_mode
                new_permissions = current_permissions

                if current_permissions & stat.S_IWUSR:
                    new_permissions |= stat.S_IWOTH
                if current_permissions & stat.S_IXUSR:
                    new_permissions |= stat.S_IXOTH

                os.chmod(file_path, new_permissions)

        logger.info(f"Permissions updated conditionally for all folders and files in {DIR}.")
    except Exception as e:
        logger.error(f"Error while changing permissions: {e}")

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

def start_local_apt_server(direc):
    """
    Starts a local APT server in the specified directory and returns the APT repository line.

    Args:
    -----
    - direc (str): The directory to serve as the APT repository.

    Returns:
    --------
    - str: The APT repository line to add to sources.list.
    """
    server = AptServer(directory=direc, port=random.randint(7500, 8500))
    server.start()
    return f"deb [trusted=yes arch=arm64] http://localhost:{server.port} stable main"

def build_deb_package_gz(direc, start_server=True) -> str:
    """
    Builds a Debian package and creates a compressed Packages file, optionally starting a local APT server.

    Args:
    -----
    - direc (str): The directory where the package is built.
    - start_server (bool): If True, starts a local APT server after building the package.

    Returns:
    --------
    - str: The APT repository line if a server is started, None otherwise.

    Raises:
    -------
    - Exception: If an error occurs while creating the Packages file.
    """
    global servers
    try:
        packages_dir = os.path.join(direc, 'dists', 'stable', 'main', 'binary-arm64')
        os.makedirs(packages_dir, exist_ok=True)

        cmd = f'dpkg-scanpackages -m . /dev/null > {os.path.join(packages_dir, "Packages")}'
        run_command(cmd, cwd=direc)

        packages_path = os.path.join(packages_dir, "Packages")
        run_command(f"gzip -k -f {packages_path}")

        logger.info(f"Packages file created in {direc}")
    except Exception as e:
        logger.error(f"Error creating Packages file in {direc}, Ignoring.")

    if start_server:
        return start_local_apt_server(direc)
    return None
