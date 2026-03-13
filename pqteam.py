

# !/usr/bin/python3
# ------------------------------------------------------------------------------
# Copyright (c) 2021, HCL Technologies Ltd. All rights reserved.
# ------------------------------------------------------------------------------
"""
This module contains Rubrik Platform Qualification code
"""
import logging
import pandas as pd
import pytest
import time
import subprocess
# Import the PQE class from pq1.py
from pq1 import PQE
# Paths and configurations
file_path = "/home/ubuntu/platform-qual-main/automation_excel_file.xlsx"
output_file = 'rkcl_output.txt'
# Setup Logging
logging.basicConfig(filename='test_results.log', level=logging.DEBUG, format='%(asctime)s %(message)s')
logger = logging.getLogger()
# Read the Excel File
print("Reading Excel file...")
try:
    df = pd.read_excel(file_path, sheet_name='Sheet1')
    print("Excel file read successfully.")
except Exception as e:
    print(f"Failed to read Excel file: {e}")
    logger.error(f"Failed to read Excel file: {e}")
print(f"Excel content:\n{df}")
# Ensure OUTPUT and Status columns are string type
df['Actual result'] = df['Actual result'].astype(str)
df['Test status'] = df['Test status'].astype(str)
# Mapping of Test Scenario
script_mapping = {
    'Perform PXE manufacturing by booting to USB boot with bios changes': 'pxe'
}
@pytest.mark.parametrize("test_scenario, command_option", [
    (row['Test Scenario'], 'pxe')  # Mapping Test Scenario to 'pxe' command option
    for _, row in df.iterrows()
    if row['Test Scenario'] == 'Perform PXE manufacturing by booting to USB boot with bios changes'
])
def test_pxe_manufacturing(test_scenario, command_option):
    print(f"Running test for Test Scenario: {test_scenario} with command option: {command_option}")
    try:
        # Run the pq1.py script with the specified option
        subprocess.run(['python3', 'pq1.py', '-o', command_option], check=True)
    except subprocess.CalledProcessError as e:
        pytest.fail(f"Error running pq1.py with option {command_option}: {e}")
    # Sleep for 35-45 minutes (using a midpoint of 40 minutes = 2400 seconds)
    sleep_time_seconds = 2400
    print(f"Sleeping for {sleep_time_seconds} seconds...")
    time.sleep(sleep_time_seconds)
    print("Sleeping done.")
    print("Sleeping completed.")
    # Execute the pq1.py script with the second command option (testpxe)
    try:
        subprocess.run(['python3', 'pq1.py', '-o', 'testpxe'], check=True)
    except subprocess.CalledProcessError as e:
        pytest.fail(f"Error running pq1.py with option 'testpxe': {e}")
    # Update the Excel file with placeholder results for demonstration
    try:
        result_status = "PASS"  # Placeholder status, replace with genuine result capture logic
        output_message = "Test successfully completed."  # Placeholder message, replace with genuine output
        row_index = df.loc[df['Test Scenario'] == test_scenario].index[0]
        df.at[row_index, 'Actual result'] = output_message
        df.at[row_index, 'Test status'] = result_status
        df.to_excel(file_path, sheet_name='Sheet1', index=False)
        print(f"Results saved to {file_path}")
    except Exception as e:
        pytest.fail(f"Error processing results for Test Scenario {test_scenario}: {e}")
if __name__ == "__main__":
    pytest.main()