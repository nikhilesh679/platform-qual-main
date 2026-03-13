import pandas as pd
import pytest
from connect import connecting_node
from openpyxl import load_workbook
import re
import time


@pytest.mark.platform_qual
def test_cluster_discover():
    """
    Test case to verify cluster discovery.
    """
    ssh = connecting_node()
    if ssh is None:
        pytest.fail("Failed to connect to the remote node.")
    else:
        print("Successfully connected to node")
 
    # Define command and expected output
    full_command = "/opt/rubrik/tools/rkcli_internal.sh cluster discover"
    # Execute command
    stdin, stdout, stderr = ssh.exec_command(full_command)
    command_input = f"{full_command}\n"
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    full_output = f"{command_input}{out}"
    print("Command Output:")
    print(out)
    print("Command Error:")
    print(err)
 
    # Clean the output
    cleaned_out = re.sub(r'=+', '', full_output).strip()
