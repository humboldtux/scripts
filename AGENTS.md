# Agent Guidance: scripts

This repository contains standalone shell and Python scripts for Debian system provisioning and maintenance.

## Execution & Workflow
- **Installation Sequence**: Installation scripts are sequentially numbered (e.g., `postinstall-10_base`, `postinstall-30_desktop`). Follow this numeric order for system setup.
- **Environment**: Scripts are designed for Debian-based systems. Most assume `sudo` availability and use `DEBIAN_FRONTEND=noninteractive` for automated package management.
- **Preseeding**: Automated OS installation configs are located in `preseed/`.

## Conventions
- **Idempotency**: Scripts should check for existing configurations or installed packages before applying changes to prevent duplication.
- **Privileges**: Scripts typically handle their own privilege escalation via `sudo`.

## Verification
- **No Automated Suite**: There is no centralized test framework. 
- **Verification Method**: Verify changes by checking the existence of target files, package status via `dpkg -l`, or running scripts twice to ensure idempotency.
