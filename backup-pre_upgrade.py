#!/usr/bin/env python3
"""
Backup script to create a pre-upgrade backup of important files:
- .bash_history for current user and root
- .ssh directory for current user and root
- /etc/restic directory

The backup is saved as ~/Documents/backup-pre_upgrade-XXXX.tgz where XXXX is a timestamp.
After backup, executes and displays output of:
- yadm status
- gita ll
- docker ps -a
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

        # Backup selected .ssh files for current user (id*, *local, *.local, local)
        ssh_dir_path = f"{home_dir}/.ssh"
        if os.path.exists(ssh_dir_path):
            # Create the target directory
            os.makedirs(f"{temp_dir}/user/{current_user}/.ssh", exist_ok=True)
            
            try:
                # Get list of files in the .ssh directory
                ssh_files = os.listdir(ssh_dir_path)
                
                # Copy files matching the patterns
                backed_up_files = 0
                for file in ssh_files:
                    file_path = os.path.join(ssh_dir_path, file)
                    # Check if file matches any of the patterns
                    if os.path.isfile(file_path) and (
                        file.startswith('id') or 
                        'local' in file or 
                        file.endswith('.local') or 
                        file == 'local'
                    ):
                        try:
                            shutil.copy2(file_path, f"{temp_dir}/user/{current_user}/.ssh/{file}")
                            backed_up_files += 1
                            print(f"  ✅ Backed up SSH file: {file}")
                        except PermissionError:
                            # Try with sudo if we don't have permission
                            try:
                                subprocess.run(
                                    ["sudo", "cp", file_path, f"{temp_dir}/user/{current_user}/.ssh/{file}"],
                                    check=True
                                )
                                backed_up_files += 1
                                print(f"  ✅ Backed up SSH file: {file} (with sudo)")
                            except subprocess.CalledProcessError as e:
                                print(f"  ❌ Failed to backup SSH file {file}: {e}")
                
                if backed_up_files > 0:
                    print(f"✅ Backed up {backed_up_files} files from {ssh_dir_path}")
                else:
                    print(f"⚠️ No matching SSH files found in {ssh_dir_path}")
            except PermissionError:
                # If we can't list the directory, try using sudo find
                try:
                    # Create the target directory
                    os.makedirs(f"{temp_dir}/user/{current_user}/.ssh", exist_ok=True)
                    
                    # Get a list of files in the user's .ssh directory using sudo that match our patterns
                    # We need to run multiple find commands and combine the results
                    find_commands = [
                        ["sudo", "find", ssh_dir_path, "-type", "f", "-name", "id*"],
                        ["sudo", "find", ssh_dir_path, "-type", "f", "-name", "*local*"],
                        ["sudo", "find", ssh_dir_path, "-type", "f", "-name", "local"]
                    ]
                    
                    ssh_files = []
                    for cmd in find_commands:
                        result = subprocess.run(
                            cmd,
                            check=True,
                            text=True,
                            capture_output=True
                        ).stdout.strip()
                        if result:
                            ssh_files.extend(result.split('\n'))
                    
                    # Remove duplicates
                    ssh_files = list(set(ssh_files))
                    
                    # Copy each matching file
                    backed_up_files = 0
                    for file_path in ssh_files:
                        if file_path:  # Skip empty lines
                            file_name = os.path.basename(file_path)
                            subprocess.run(
                                ["sudo", "cp", file_path, f"{temp_dir}/user/{current_user}/.ssh/{file_name}"],
                                check=True
                            )
                            backed_up_files += 1
                            print(f"  ✅ Backed up SSH file: {file_name} (with sudo)")
                    
                    if backed_up_files > 0:
                        print(f"✅ Backed up {backed_up_files} files from {ssh_dir_path} (with sudo)")
                    else:
                        print(f"⚠️ No matching SSH files found in {ssh_dir_path}")
                except subprocess.CalledProcessError as e:
                    print(f"❌ Failed to backup files from {ssh_dir_path}: {e}")
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

        # Backup selected .ssh files for root (id*, *local, *.local, local)
        try:
            if os.path.exists("/root/.ssh"):
                # Create the target directory
                os.makedirs(f"{temp_dir}/root/.ssh", exist_ok=True)
                
                # If running as root, we can access files directly
                if os.geteuid() == 0:
                    # Get list of files in the root .ssh directory matching our patterns
                    ssh_files = []
                    # Files starting with 'id'
                    ssh_files.extend(glob.glob("/root/.ssh/id*"))
                    # Files containing 'local'
                    ssh_files.extend(glob.glob("/root/.ssh/*local*"))
                    # The specific file named 'local'
                    if os.path.exists("/root/.ssh/local"):
                        ssh_files.append("/root/.ssh/local")
                    
                    # Remove duplicates
                    ssh_files = list(set(ssh_files))
                    
                    # Copy each matching file
                    backed_up_files = 0
                    for file_path in ssh_files:
                        if os.path.isfile(file_path):
                            file_name = os.path.basename(file_path)
                            shutil.copy2(file_path, f"{temp_dir}/root/.ssh/{file_name}")
                            backed_up_files += 1
                            print(f"  ✅ Backed up root SSH file: {file_name}")
                    
                    if backed_up_files > 0:
                        print(f"✅ Backed up {backed_up_files} files from /root/.ssh")
                    else:
                        print("⚠️ No matching SSH files found in /root/.ssh")
                else:
                    # Otherwise use sudo
                    # We need to run multiple find commands and combine the results
                    find_commands = [
                        ["sudo", "find", "/root/.ssh", "-type", "f", "-name", "id*"],
                        ["sudo", "find", "/root/.ssh", "-type", "f", "-name", "*local*"],
                        ["sudo", "find", "/root/.ssh", "-type", "f", "-name", "local"]
                    ]
                    
                    ssh_files = []
                    for cmd in find_commands:
                        result = subprocess.run(
                            cmd,
                            check=True,
                            text=True,
                            capture_output=True
                        ).stdout.strip()
                        if result:
                            ssh_files.extend(result.split('\n'))
                    
                    # Remove duplicates
                    ssh_files = list(set([f for f in ssh_files if f]))
                    
                    # Copy each matching file
                    backed_up_files = 0
                    for file_path in ssh_files:
                        if file_path:  # Skip empty lines
                            file_name = os.path.basename(file_path)
                            subprocess.run(
                                ["sudo", "cp", file_path, f"{temp_dir}/root/.ssh/{file_name}"],
                                check=True
                            )
                            backed_up_files += 1
                            print(f"  ✅ Backed up root SSH file: {file_name}")
                    
                    if backed_up_files > 0:
                        print(f"✅ Backed up {backed_up_files} files from /root/.ssh")
                    else:
                        print("⚠️ No matching SSH files found in /root/.ssh")
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
