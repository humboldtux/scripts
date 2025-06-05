#!/usr/bin/env python3
"""
Backup script to create a pre-upgrade backup of important files:
- .bash_history for current user and root
- .ssh directory for current user and root
- ~/.bashrc.d directory for current user and root (if exists)
- /etc/restic directory
- /etc/network/interfaces and /etc/network/interfaces.d directory
- /etc/fstab

The backup is saved as ~/Documents/backup-pre_upgrade-HOSTNAME-XXXX.tgz where HOSTNAME is the machine hostname and XXXX is a timestamp.
After backup, executes and displays output of:
- yadm status
- gita ll
- docker ps -a
- ip a
- df -h
- fdisk -l
"""

import os
import sys
import tarfile
import tempfile
import shutil
import datetime
import subprocess
import glob
import tomli
import io
import builtins
import socket
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path


def run_command(command, capture_output=False):
    """Run a shell command and display its output.
    If capture_output is True, returns the command output as a string."""
    separator = "\n" + "="*80 + "\n"
    cmd_header = f"{separator}COMMAND: {command}{separator}"
    print(cmd_header)
    try:
        result = subprocess.run(command, shell=True, check=False, text=True, capture_output=True)
        output = result.stdout
        print(output)
        return None
    except Exception as e:
        error_msg = f"ERROR: {e}"
        print(error_msg)
        return None


# Global variable to store the temp directory path
temp_dir_path = None

def create_backup():
    # Determine if script is running with sudo
    is_sudo = os.geteuid() == 0
    
    # Get the actual user who invoked sudo (if applicable)
    if is_sudo:
        sudo_user = os.environ.get("SUDO_USER")
        if sudo_user:
            current_user = sudo_user
            home_dir = f"/home/{sudo_user}"
        else:
            # Fallback if SUDO_USER is not available
            current_user = os.getenv("USER")
            home_dir = str(Path.home())
        print(f"Running with sudo as {current_user}")
    else:
        current_user = os.getenv("USER")
        home_dir = str(Path.home())

    # Get hostname for the backup filename
    hostname = socket.gethostname()
    
    # Create timestamp for the backup filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_filename = f"{home_dir}/Documents/backup-pre_upgrade-{hostname}-{timestamp}.tgz"

    # Create a temporary directory for collecting files to backup
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create directories structure in the temp directory
        os.makedirs(f"{temp_dir}/user/{current_user}", exist_ok=True)
        os.makedirs(f"{temp_dir}/root", exist_ok=True)
        os.makedirs(f"{temp_dir}/etc", exist_ok=True)

        # Backup .bash_history for current user
        bash_history_path = f"{home_dir}/.bash_history"
        if os.path.exists(bash_history_path):
            try:
                shutil.copy2(
                    bash_history_path, f"{temp_dir}/user/{current_user}/.bash_history"
                )
                print(f"✅ Backed up {bash_history_path}")
            except PermissionError:
                # Try with sudo if we don't have permission
                try:
                    subprocess.run(
                        ["sudo", "cp", bash_history_path, f"{temp_dir}/user/{current_user}/.bash_history"],
                        check=True
                    )
                    print(f"✅ Backed up {bash_history_path} (with sudo)")
                except subprocess.CalledProcessError as e:
                    print(f"❌ Failed to backup {bash_history_path}: {e}")
        else:
            print(f"⚠️ {bash_history_path} does not exist, skipping")
            
        # Backup .bashrc.d directory for current user if it exists
        bashrc_d_path = f"{home_dir}/.bashrc.d"
        if os.path.exists(bashrc_d_path) and os.path.isdir(bashrc_d_path):
            try:
                # Create target directory
                os.makedirs(f"{temp_dir}/user/{current_user}/.bashrc.d", exist_ok=True)
                
                # Copy all files from .bashrc.d
                files_backed_up = 0
                for item in os.listdir(bashrc_d_path):
                    item_path = os.path.join(bashrc_d_path, item)
                    if os.path.isfile(item_path):
                        try:
                            shutil.copy2(item_path, f"{temp_dir}/user/{current_user}/.bashrc.d/{item}")
                            files_backed_up += 1
                            print(f"  ✅ Backed up .bashrc.d file: {item}")
                        except PermissionError:
                            # Try with sudo if we don't have permission
                            try:
                                subprocess.run(
                                    ["sudo", "cp", item_path, f"{temp_dir}/user/{current_user}/.bashrc.d/{item}"],
                                    check=True
                                )
                                files_backed_up += 1
                                print(f"  ✅ Backed up .bashrc.d file: {item} (with sudo)")
                            except subprocess.CalledProcessError as e:
                                print(f"  ❌ Failed to backup .bashrc.d file {item}: {e}")
                
                if files_backed_up > 0:
                    print(f"✅ Backed up {files_backed_up} files from {bashrc_d_path}")
                else:
                    print(f"⚠️ No files found in {bashrc_d_path}, directory is empty")
            except (PermissionError, OSError) as e:
                print(f"❌ Failed to backup {bashrc_d_path}: {e}")
        else:
            print(f"⚠️ {bashrc_d_path} does not exist or is not a directory, skipping")

        # Backup entire .ssh directory for current user (except control sockets)
        ssh_dir_path = f"{home_dir}/.ssh"
        if os.path.exists(ssh_dir_path):
            try:
                # Ignore control sockets and other special files
                def ignore_special(src, names):
                    return [name for name in names if 'control-' in name or not os.path.isfile(os.path.join(src, name))]
                
                # Copy entire .ssh directory with permissions, ignoring special files
                shutil.copytree(ssh_dir_path, f"{temp_dir}/user/{current_user}/.ssh", 
                               symlinks=True, 
                               ignore=ignore_special)
                print(f"✅ Backed up .ssh directory from {ssh_dir_path} (ignoring control sockets)")
            except PermissionError:
                # Try with sudo if we don't have permission
                try:
                    # Create target directory
                    os.makedirs(f"{temp_dir}/user/{current_user}/.ssh", exist_ok=True)
                    # Copy all regular files and symlinks, excluding control sockets
                    subprocess.run([
                        "sudo", "find", ssh_dir_path,
                        "(", "-type", "f", "-o", "-type", "l", ")",
                        "!", "-name", "control-*",
                        "-exec", "cp", "-a", "--parents", "{}", f"{temp_dir}/user/{current_user}/" ";"                        
                    ], check=True)
                    print(f"✅ Backed up .ssh directory from {ssh_dir_path} (with sudo, ignoring control sockets)")
                except subprocess.CalledProcessError as e:
                    print(f"❌ Failed to backup {ssh_dir_path}: {e}")
        else:
            print(f"⚠️ {ssh_dir_path} does not exist, skipping")

        # Backup .bash_history for root
        try:
            if os.path.exists("/root/.bash_history"):
                # If running as root, we can copy directly
                if os.geteuid() == 0:
                    shutil.copy2("/root/.bash_history", f"{temp_dir}/root/.bash_history")
                    print("✅ Backed up /root/.bash_history")
                else:
                    # Otherwise use sudo
                    subprocess.run(
                        [
                            "sudo",
                            "cp",
                            "/root/.bash_history",
                            f"{temp_dir}/root/.bash_history",
                        ],
                        check=True,
                    )
                    print("✅ Backed up /root/.bash_history (with sudo)")
            else:
                print("⚠️ /root/.bash_history does not exist, skipping")
        except (subprocess.CalledProcessError, PermissionError) as e:
            print(f"❌ Failed to backup /root/.bash_history: {e}")
            
        # Backup .bashrc.d directory for root if it exists
        try:
            root_bashrc_d_path = "/root/.bashrc.d"
            if os.path.exists(root_bashrc_d_path) and os.path.isdir(root_bashrc_d_path):
                # Create target directory
                os.makedirs(f"{temp_dir}/root/.bashrc.d", exist_ok=True)
                
                # If running as root, we can access files directly
                if os.geteuid() == 0:
                    # Copy all files from root's .bashrc.d
                    files_backed_up = 0
                    for item in os.listdir(root_bashrc_d_path):
                        item_path = os.path.join(root_bashrc_d_path, item)
                        if os.path.isfile(item_path):
                            shutil.copy2(item_path, f"{temp_dir}/root/.bashrc.d/{item}")
                            files_backed_up += 1
                            print(f"  ✅ Backed up root .bashrc.d file: {item}")
                    
                    if files_backed_up > 0:
                        print(f"✅ Backed up {files_backed_up} files from {root_bashrc_d_path}")
                    else:
                        print(f"⚠️ No files found in {root_bashrc_d_path}, directory is empty")
                else:
                    # Otherwise use sudo
                    # Get a list of files in root's .bashrc.d
                    file_list = subprocess.run(
                        ["sudo", "find", root_bashrc_d_path, "-type", "f"],
                        check=True,
                        text=True,
                        capture_output=True
                    ).stdout.strip().split('\n')
                    
                    # Copy each file
                    files_backed_up = 0
                    for file_path in file_list:
                        if file_path:  # Skip empty lines
                            file_name = os.path.basename(file_path)
                            subprocess.run(
                                ["sudo", "cp", file_path, f"{temp_dir}/root/.bashrc.d/{file_name}"],
                                check=True
                            )
                            files_backed_up += 1
                            print(f"  ✅ Backed up root .bashrc.d file: {file_name}")
                    
                    if files_backed_up > 0:
                        print(f"✅ Backed up {files_backed_up} files from {root_bashrc_d_path}")
                    else:
                        print(f"⚠️ No files found in {root_bashrc_d_path}, directory is empty")
            else:
                print(f"⚠️ {root_bashrc_d_path} does not exist or is not a directory, skipping")
        except (subprocess.CalledProcessError, PermissionError) as e:
            print(f"❌ Failed to backup {root_bashrc_d_path}: {e}")

        # Backup entire .ssh directory for root (except control sockets)
        try:
            if os.path.exists("/root/.ssh"):
                if os.geteuid() == 0:
                    # If running as root, we can copy directly
                    def ignore_special(src, names):
                        return [name for name in names if 'control-' in name or not os.path.isfile(os.path.join(src, name))]
                    
                    shutil.copytree("/root/.ssh", f"{temp_dir}/root/.ssh", 
                                   symlinks=True, 
                                   ignore=ignore_special)
                    print("✅ Backed up .ssh directory from /root/.ssh (ignoring control sockets)")
                else:
                    # Otherwise use sudo
                    # Create target directory
                    os.makedirs(f"{temp_dir}/root/.ssh", exist_ok=True)
                    # Copy all regular files and symlinks, excluding control sockets
                    subprocess.run([
                        "sudo", "find", "/root/.ssh",
                        "(", "-type", "f", "-o", "-type", "l", ")",
                        "!", "-name", "control-*",
                        "-exec", "cp", "-a", "--parents", "{}", f"{temp_dir}/root/" ";"
                    ], check=True)
                    print("✅ Backed up .ssh directory from /root/.ssh (with sudo, ignoring control sockets)")
            else:
                print("⚠️ /root/.ssh does not exist, skipping")
        except (subprocess.CalledProcessError, PermissionError) as e:
            print(f"❌ Failed to backup /root/.ssh: {e}")

        # Backup /etc/restic
        try:
            if os.path.exists("/etc/restic"):
                # If running as root, we can copy directly
                if os.geteuid() == 0:
                    shutil.copytree("/etc/restic", f"{temp_dir}/etc/restic", symlinks=True)
                    print("✅ Backed up /etc/restic")
                else:
                    # Otherwise use sudo
                    subprocess.run(
                        ["sudo", "cp", "-r", "/etc/restic", f"{temp_dir}/etc/restic"],
                        check=True,
                    )
                    print("✅ Backed up /etc/restic (with sudo)")
                
                # Check for profiles.toml and backup sources from [local.backup] section
                profiles_path = "/etc/restic/profiles.toml"
                if os.path.exists(profiles_path):
                    try:
                        # Create a directory for additional sources
                        os.makedirs(f"{temp_dir}/additional_sources", exist_ok=True)
                        
                        # Read and parse the TOML file
                        toml_content = ""
                        if os.geteuid() == 0:
                            with open(profiles_path, "rb") as f:
                                toml_content = f.read()
                        else:
                            # Use sudo cat to read the file
                            toml_content = subprocess.run(
                                ["sudo", "cat", profiles_path],
                                check=True,
                                capture_output=True
                            ).stdout
                        
                        # Parse TOML content
                        try:
                            config = tomli.loads(toml_content.decode('utf-8') if isinstance(toml_content, bytes) else toml_content)
                            
                            # Check if local.backup section exists
                            if "local" in config and "backup" in config["local"]:
                                backup_config = config["local"]["backup"]
                                
                                # Check if source array exists
                                if "source" in backup_config and isinstance(backup_config["source"], list):
                                    sources = backup_config["source"]
                                    print(f"\n✅ Found {len(sources)} sources in [local.backup] section")
                                    
                                    # Backup each source
                                    for i, source in enumerate(sources):
                                        source_path = str(source)
                                        if os.path.exists(source_path):
                                            target_name = os.path.basename(source_path)
                                            target_path = f"{temp_dir}/additional_sources/{target_name}"
                                            
                                            try:
                                                # Backup as root
                                                if os.path.isdir(source_path):
                                                    if os.geteuid() == 0:
                                                        shutil.copytree(source_path, target_path, symlinks=True)
                                                    else:
                                                        subprocess.run(
                                                            ["sudo", "cp", "-r", source_path, target_path],
                                                            check=True
                                                        )
                                                else:  # It's a file
                                                    if os.geteuid() == 0:
                                                        shutil.copy2(source_path, target_path)
                                                    else:
                                                        subprocess.run(
                                                            ["sudo", "cp", source_path, target_path],
                                                            check=True
                                                        )
                                                print(f"  ✅ Backed up additional source: {source_path}")
                                            except (subprocess.CalledProcessError, PermissionError, shutil.Error) as e:
                                                print(f"  ❌ Failed to backup {source_path}: {e}")
                                        else:
                                            print(f"  ⚠️ Source {source_path} does not exist, skipping")
                                else:
                                    print("⚠️ No 'source' array found in [local.backup] section")
                            else:
                                print("⚠️ No [local.backup] section found in profiles.toml")
                        except Exception as e:
                            print(f"❌ Failed to parse profiles.toml: {e}")
                    except (subprocess.CalledProcessError, PermissionError) as e:
                        print(f"❌ Failed to read profiles.toml: {e}")
                else:
                    print("⚠️ /etc/restic/profiles.toml does not exist, skipping additional sources")
            else:
                print("⚠️ /etc/restic does not exist, skipping")
        except (subprocess.CalledProcessError, PermissionError) as e:
            print(f"❌ Failed to backup /etc/restic: {e}")

        # Backup /etc/network/interfaces file if it exists
        try:
            if os.path.exists("/etc/network/interfaces") and os.path.isfile("/etc/network/interfaces"):
                # Create target directory
                os.makedirs(f"{temp_dir}/etc/network", exist_ok=True)
                
                # If running as root, we can copy directly
                if os.geteuid() == 0:
                    shutil.copy2("/etc/network/interfaces", f"{temp_dir}/etc/network/interfaces")
                    print("✅ Backed up /etc/network/interfaces")
                else:
                    # Otherwise use sudo
                    subprocess.run(
                        ["sudo", "cp", "/etc/network/interfaces", f"{temp_dir}/etc/network/interfaces"],
                        check=True
                    )
                    print("✅ Backed up /etc/network/interfaces (with sudo)")
            else:
                print("⚠️ /etc/network/interfaces does not exist, skipping")
        except (subprocess.CalledProcessError, PermissionError) as e:
            print(f"❌ Failed to backup /etc/network/interfaces: {e}")
            
        # Backup /etc/network/interfaces.d directory if it exists
        try:
            interfaces_d_path = "/etc/network/interfaces.d"
            if os.path.exists(interfaces_d_path) and os.path.isdir(interfaces_d_path):
                # Create target directory
                os.makedirs(f"{temp_dir}/etc/network/interfaces.d", exist_ok=True)
                
                # If running as root, we can access files directly
                if os.geteuid() == 0:
                    # Copy all files from interfaces.d
                    files_backed_up = 0
                    for item in os.listdir(interfaces_d_path):
                        item_path = os.path.join(interfaces_d_path, item)
                        if os.path.isfile(item_path):
                            shutil.copy2(item_path, f"{temp_dir}/etc/network/interfaces.d/{item}")
                            files_backed_up += 1
                            print(f"  ✅ Backed up interfaces.d file: {item}")
                    
                    if files_backed_up > 0:
                        print(f"✅ Backed up {files_backed_up} files from {interfaces_d_path}")
                    else:
                        print(f"⚠️ No files found in {interfaces_d_path}, directory is empty")
                else:
                    # Otherwise use sudo
                    # Get a list of files in interfaces.d
                    file_list = subprocess.run(
                        ["sudo", "find", interfaces_d_path, "-type", "f"],
                        check=True,
                        text=True,
                        capture_output=True
                    ).stdout.strip().split('\n')
                    
                    # Copy each file
                    files_backed_up = 0
                    for file_path in file_list:
                        if file_path:  # Skip empty lines
                            file_name = os.path.basename(file_path)
                            subprocess.run(
                                ["sudo", "cp", file_path, f"{temp_dir}/etc/network/interfaces.d/{file_name}"],
                                check=True
                            )
                            files_backed_up += 1
                            print(f"  ✅ Backed up interfaces.d file: {file_name}")
                    
                    if files_backed_up > 0:
                        print(f"✅ Backed up {files_backed_up} files from {interfaces_d_path}")
                    else:
                        print(f"⚠️ No files found in {interfaces_d_path}, directory is empty")
            else:
                print(f"⚠️ {interfaces_d_path} does not exist or is not a directory, skipping")
        except (subprocess.CalledProcessError, PermissionError) as e:
            print(f"❌ Failed to backup {interfaces_d_path}: {e}")
            
        # Backup /etc/fstab file if it exists
        try:
            if os.path.exists("/etc/fstab") and os.path.isfile("/etc/fstab"):
                # Create target directory if it doesn't exist
                os.makedirs(f"{temp_dir}/etc", exist_ok=True)
                
                # If running as root, we can copy directly
                if os.geteuid() == 0:
                    shutil.copy2("/etc/fstab", f"{temp_dir}/etc/fstab")
                    print("✅ Backed up /etc/fstab")
                else:
                    # Otherwise use sudo
                    subprocess.run(
                        ["sudo", "cp", "/etc/fstab", f"{temp_dir}/etc/fstab"],
                        check=True
                    )
                    print("✅ Backed up /etc/fstab (with sudo)")
            else:
                print("⚠️ /etc/fstab does not exist, skipping")
        except (subprocess.CalledProcessError, PermissionError) as e:
            print(f"❌ Failed to backup /etc/fstab: {e}")

        # Create a file for script output at the root of the archive
        output_file_path = f"{temp_dir}/script.output"
        # Write an initial message - we'll update this file later with complete output
        with open(output_file_path, "w") as f:
            f.write(f"Backup script started at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("This file will contain the complete output of the backup-pre_upgrade.py script\n")
            f.write("including all command outputs.\n")
        
        # Create the backup archive
        try:
            os.makedirs(os.path.dirname(backup_filename), exist_ok=True)
            with tarfile.open(backup_filename, "w:gz") as tar:
                tar.add(temp_dir, arcname=".")
            print(f"\n✅ Backup successfully created at: {backup_filename}")
        except Exception as e:
            print(f"❌ Failed to create backup archive: {e}")
            return False, None, None

    # Store the temp directory path in the global variable
    global temp_dir_path
    temp_dir_path = temp_dir
    
    # Return success, backup filename, and the temp directory path
    return True, backup_filename, temp_dir


def run_as_user(command, user=None, capture_output=False):
    """Run a command as the specified user or as the current user if None."""
    # If we're running as root and have a sudo_user, use su to run as that user
    if os.geteuid() == 0 and user:
        cmd = ["su", "-", user, "-c", command]
        separator = "\n" + "="*80 + "\n"
        cmd_header = f"{separator}COMMAND AS USER {user}: {command}{separator}"
        print(cmd_header)
        try:
            result = subprocess.run(cmd, check=False, text=True, capture_output=True)
            output = result.stdout
            print(output)
            return None
        except Exception as e:
            error_msg = f"ERROR: {e}"
            print(error_msg)
            return None
    else:
        # Run normally
        return run_command(command, capture_output)


def run_as_root(command, capture_output=False):
    """Run a command as root."""
    separator = "\n" + "="*80 + "\n"
    cmd_header = f"{separator}COMMAND AS ROOT: {command}{separator}"
    print(cmd_header)
    try:
        if os.geteuid() == 0:  # Already running as root
            result = subprocess.run(command, shell=True, check=False, text=True, capture_output=True)
            output = result.stdout
            print(output)
            return None
        else:  # Need to use sudo
            cmd = f"sudo {command}"
            result = subprocess.run(cmd, shell=True, check=False, text=True, capture_output=True)
            output = result.stdout
            print(output)
            return None
    except Exception as e:
        error_msg = f"ERROR: {e}"
        print(error_msg)
        return None


# Capture all output to this global variable
all_output = []

# Store the original print function
original_print = builtins.print

# Custom print function to capture output while still printing to console
def capture_print(*args, **kwargs):
    # Get the original print output as a string
    output_buffer = io.StringIO()
    
    # Make a copy of kwargs without 'file' if it exists
    kwargs_for_buffer = kwargs.copy()
    if 'file' in kwargs_for_buffer:
        del kwargs_for_buffer['file']
    
    # Print to the buffer
    original_print(*args, file=output_buffer, **kwargs_for_buffer)
    output_str = output_buffer.getvalue()
    
    # Print to console using original print
    original_print(*args, **kwargs)
    
    # Add to our captured output
    global all_output
    all_output.append(output_str)


def main():
    """Main function to run the backup process and capture output."""
    global all_output
    all_output = []
    
    # Replace the standard print with our capture_print during backup
    saved_print = builtins.print
    builtins.print = capture_print
    
    try:
        # Start the backup process
        capture_print(f"Starting pre-upgrade backup at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Determine the actual user (not root) for running commands later
        actual_user = None
        if os.geteuid() == 0:  # If running as root
            actual_user = os.environ.get("SUDO_USER")
            capture_print(f"Running with sudo as user: {actual_user}")
        
        # Store the temp_dir outside the function to access it later
        global temp_dir_path
        success, backup_file, temp_dir_path = create_backup()
        
        if success:
            capture_print("Backup process completed successfully.")

            # Execute the requested commands after backup is complete
            capture_print("\nExecuting requested commands:")
            
            # Run user commands as the actual user with output capture
            run_as_user("yadm status", actual_user)
            run_as_user("gita ll", actual_user)
            run_as_user("docker ps -a", actual_user)
            
            # Run root commands with output capture
            run_as_root("df -h")
            run_as_root("fdisk -l")
            run_as_root("ip a")
            
            # Add completion timestamp
            capture_print(f"\nBackup completed at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Create the output file in /tmp
            script_output_file = os.path.join("/tmp", f"script.output-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}")
            
            try:
                # Write all output to the script.output file
                with open(script_output_file, "w") as f:
                    f.write("".join(all_output))
                capture_print(f"\n✅ Temporary script output saved to: {script_output_file}")
                
                # Create a new archive that includes the original files plus the script.output
                # First, create a temporary directory for the new archive
                with tempfile.TemporaryDirectory() as new_temp_dir:
                    # Extract the original archive to the new temp directory
                    with tarfile.open(backup_file, "r:gz") as tar:
                        tar.extractall(path=new_temp_dir)
                    
                    # Copy the script.output file to the root of the extracted archive
                    shutil.copy2(script_output_file, os.path.join(new_temp_dir, "script.output"))
                    
                    # Create a new archive with the updated contents
                    with tarfile.open(backup_file, "w:gz") as tar:
                        # Add all files from the new temp directory
                        for item in os.listdir(new_temp_dir):
                            tar.add(os.path.join(new_temp_dir, item), arcname=item)
                    
                    capture_print(f"\n✅ Archive updated with script.output at: {backup_file}")
                    
                # Delete the temporary script.output file
                os.remove(script_output_file)
                capture_print(f"\n✅ Temporary script output file removed: {script_output_file}")
            except Exception as e:
                capture_print(f"\n❌ Failed to update archive with script output: {e}")
                # Try to clean up the temporary file even if there was an error
                try:
                    if os.path.exists(script_output_file):
                        os.remove(script_output_file)
                        capture_print(f"\n✅ Temporary script output file removed: {script_output_file}")
                except Exception as cleanup_error:
                    capture_print(f"\n❌ Failed to remove temporary file: {cleanup_error}")
            
            return 0
        else:
            capture_print("Backup process failed.")
            return 1
    finally:
        # Restore the original print function
        builtins.print = saved_print


if __name__ == "__main__":
    # Run the main function but don't capture output at the top level
    # so it still displays to the console
    sys.exit(main())
