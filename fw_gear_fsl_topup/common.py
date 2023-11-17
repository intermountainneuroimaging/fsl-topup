"""
This module, utils.args.common, hosts the functionality used by all modules in
utils.args. They streamline the 'execute' functionality of the build/validate/execute
paradigm followed in each of the other module-scripts in args.
"""

import os
import subprocess as sp
import re
import logging
from typing import List
import shutil
import tempfile

log = logging.getLogger(__name__)

# -----------------------------------------------
# Support functions
# -----------------------------------------------


def build_command_list(command, ParamList, include_keys=True):
    """
    command is a list of prepared commands
    ParamList is a dictionary of key:value pairs to be put into the command
     list as such ("-k value" or "--key=value")
    include_keys indicates whether to include the key-names with the command (True)
    """
    for key in ParamList.keys():
        # Single character command-line parameters are preceded by a single '-'
        if len(key) == 1:
            if include_keys:
                # If Param is boolean and true include, else exclude
                if type(ParamList[key]) == bool or len(str(ParamList[key])) == 0:
                    if ParamList[key] and include_keys:
                        command.append('-' + key)
                else:
                    command.append('-' + key)
                    command.append(str(ParamList[key]))
        # Multi-Character command-line parameters are preceded by a double '--'
        else:
            # If Param is boolean and true include, else exclude
            if type(ParamList[key]) == bool:
                if ParamList[key] and include_keys:
                    command.append('--' + key)
            else:
                # If Param not boolean, but without value include without value
                # (e.g. '--key'), else include value (e.g. '--key=value')
                item = ""
                if include_keys:
                    item = '--' + key
                if len(str(ParamList[key])) > 0:
                    if include_keys:
                        item = item + "="
                    item = item + str(ParamList[key])
                command.append(item)
    return command


def generate_command(
        gear_options: dict,
        app_options: dict,
) -> List[str]:
    """Build the main command line command to run.

    This method should be the same for FW and XNAT instances. It is also BIDS-App
    generic.

    Args:
        gear_options (dict): options for the gear, from config.json
        app_options (dict): options for the app, from config.json
    Returns:
        cmd (list of str): command to execute
    """

    cmd = []
    cmd.append(gear_options["feat"]["common_command"])
    cmd.append(app_options["design_file"])

    return cmd


def execute_shell(cmd, dryrun=False, cwd=os.getcwd()):
    log.info("\n %s", cmd)
    if not dryrun:
        terminal = sp.Popen(
            cmd,
            shell=True,
            stdout=sp.PIPE,
            stderr=sp.PIPE,
            universal_newlines=True,
            cwd=cwd
        )
        stdout, stderr = terminal.communicate()
        returnCode = terminal.poll()
        log.debug("\n %s", stdout)
        log.debug("\n %s", stderr)

        if returnCode > 0:
            log.error("Error. \n%s\n%s", stdout, stderr)
        return returnCode


def searchfiles(path, dryrun=False, exit_on_errors=True, find_first=False) -> list[str]:
    cmd = "ls -d " + path

    log.debug("\n %s", cmd)

    if not dryrun:
        terminal = sp.Popen(
            cmd, shell=True, stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True
        )
        stdout, stderr = terminal.communicate()
        returnCode = terminal.poll()
        log.debug("\n %s", stdout)
        log.debug("\n %s", stderr)

        files = stdout.strip("\n").split("\n")

        if returnCode > 0 and exit_on_errors:
            log.error("Error. \n%s\n%s", stdout, stderr)

        if returnCode > 0 and not exit_on_errors:
            log.warning("Warning. \n%s\n%s", stdout, stderr)

        if find_first:
            files = files[0]

        return files


def apply_lookup(text, lookup_table):
    if '{' in text and '}' in text:
        for lookup in lookup_table:
            text = text.replace('{' + lookup + '}', lookup_table[lookup])
    return text
