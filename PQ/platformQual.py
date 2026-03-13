#!/usr/bin/python3
#------------------------------------------------------------------------------
# Copyright (c) 2021, HCL Technologies Ltd. All rights reserved.
#------------------------------------------------------------------------------

"""
This module contains Rubrik Platform Qualification code
"""

import sys
import yaml
import urllib3
import logging
import requests
import subprocess
import json
import time



from rubrik_cdm.exceptions import InvalidParameterException, RubrikException
from pathlib import Path

from .pxeMfg import PxeMfg
from .genericCli import GenericCLI
from .usbPrecheck import UsbPrecheck
from .upgradeCluster import UpgradeCluster
from .forgeClusterOps import ForgeClusterOps
from .bootstrapCluster import BootstrapCluster
from .setupNetwork import SetUpNetwork
from .preservehd import PreserveHdd
from .nodeEntitlement import entitlement
from .securityTest import SecurityTest

class Connect(PxeMfg, BootstrapCluster, GenericCLI, UsbPrecheck, UpgradeCluster, ForgeClusterOps, SetUpNetwork, PreserveHdd, entitlement, SecurityTest):
    """This class acts as the base class for the Rubrik Platform Qual Automation and serves as the main interaction point
    for its end users. It also contains various helper functions used throughout the SDK.

    Arguments:
        PxeMfg {class} -- This class contains methods related to PXE manufacturing and testing.
        BootstrapCluster {class} -- This class contains methods related to cluster bootstrapping and testing.
        GenericCLI {class} -- This class contains methods related to testing the build with some generic CLI and hardware health commands.
        UsbPrecheck {class} -- This class contains methods related to USB manufacturing pre-checks.
    """

    def __init__(self, enable_logging=False, logging_level="debug"):
        """Constructor for the PlatformQual class which is used to initialize the class variables.

        Keyword Arguments:
            enable_logging {bool} -- Flag to determine if logging will be enabled for the SDK. (default: {False}) 
            logging_level {str} -- Sets the threshold for logging to the provided to level. Logging messages which are less severe than level will be ignored. (default: {debug}) (choices: {debug, critical, error, warning, info})
        """

        set_logging = {
            "debug": logging.DEBUG,
            "critical": logging.CRITICAL,
            "error": logging.ERROR,
            "warning": logging.WARNING,
            "info": logging.INFO,
        }

        if logging_level not in set_logging:
            raise InvalidParameterException(
                "'{}' is not a valid logging_level. Valid choices are 'debug', 'critical', 'error', 'warning', or 'info'.".format(logging_level))
        
        # Disable urrlib3 warnings and set logging level to ERROR
        urllib3.disable_warnings()
        logging.getLogger("urllib3").setLevel(logging.ERROR)

        # Paramiko - Set logging level to ERROR
        logging.getLogger("paramiko").setLevel(logging.ERROR)

        # IdracRedfishSupport - Set logging level to ERROR
        # logging.getLogger("IdracRedfishSupport").setLevel(logging.ERROR)

        # rubrik_cdm - Set logging level to ERROR
        # logging.getLogger("rubrik_cdm").setLevel(logging.ERROR)

        # Enable logging for the SDK
        self.logging_level = logging_level
        if enable_logging:
            logging.getLogger().setLevel(set_logging[self.logging_level])
            console_output_handler = logging.StreamHandler()
            formatter = logging.Formatter("[%(asctime)s] [%(name)s] [%(levelname)s] -- %(message)s")
            console_output_handler.setFormatter(formatter)
            logging.getLogger().addHandler(console_output_handler)

        self.logger = logging.getLogger(__name__)
        # log.addHandler(console_output_handler)

        self.sdk_version = "1.0.0"
        self.python_version = sys.version.split("(")[0].strip()
        # function_name will be populated in each function
        self.function_name = ""
        # Optional value to define the Platform using the SDK (Ex. Ansible)
        self.platform = ""
        
        print("")
        
        # Load data from cluster YAML
        try:
            with open("cluster.yml") as file:
                self.cluster = yaml.load(file, Loader=yaml.FullLoader)
        except FileNotFoundError as ferr:
            sys.exit("Error: {}\nExiting...".format(ferr))
        except IOError as ioerr:
            sys.exit("Error: {}\nExiting...".format(ioerr))
        else:
            self.log("Cluster YAML file 'cluster.yml' exists and read successfully.")
        finally:
            file.close()
        
        # Load data from input YAML
        try:
            with open("input.yml") as file:
                self.input = yaml.load(file, Loader=yaml.FullLoader)
        except FileNotFoundError as ferr:
            sys.exit("Error: {}\nExiting...".format(ferr))
        except IOError as ioerr:
            sys.exit("Error: {}\nExiting...".format(ioerr))
        else:
            self.log("Input YAML file 'input.yml' exists and read successfully.")
        finally:
            file.close()
        
        # Check if the private key file is present or not
        pk_file = Path("pkey.pem")
        if pk_file.is_file():
            self.log("Private key file 'pkey.pem' exists and read successfully.\n")
        else:
            sys.exit("The private key file 'pkey.pem' doesn't exist or is a broken symlink.\n")
    
    def log(self, log_message):
        """Create properly formatted debug log messages.
        
        Arguments:
            log_message {str} -- The message to pass to the debug log.
        """

        log = logging.getLogger(__name__)

        set_logging = {
            "debug": log.debug,
            "critical": log.critical,
            "error": log.error,
            "warning": log.warning,
            "info": log.info
        }
        
        set_logging[self.logging_level](log_message)

    def check_bootstrap(self):
        """This method checks whether this machine has been bootstrapped.

        Parametes:
            None
        """

        # Initialization
        cluster = self.cluster
        self.log("upgrade_cluster: Started the upgrade task")
        
        username = cluster['bootstrap_credentials']['username']
        password = cluster['bootstrap_credentials']['password']

        # Check whether the cluster is accessible
        self.log("Checking whether the cluster is reachable.")
        reachable = False
        reachable_node_ip = ''
        for node in cluster['nodes']:

            ip = node['ipv4']['address']
            not_pinging = subprocess.call("ping -c 1 {}".format(ip),
                        shell=True,
                        stdout=open('/dev/null', 'w'),
                        stderr=subprocess.STDOUT)
            
            if not_pinging:
                continue
            else:
                reachable = True
                reachable_node_ip = ip
                break
        
        if reachable:
            self.log("upgrade_cluster: The cluster is reachable.")
            print("")
        else:
            raise RubrikException("upgrade_cluster: The cluster IPs are unreachable. Can't check whether the cluster is bootstrapped.")
            # return None, None, 'unr'

        # Check whether cluster is bootstrapped
        self.log("Checking whether cluster is bootstrapped.")
        url = 'https://' + reachable_node_ip + '/api/internal/node_management/is_bootstrapped'
        header = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        try:
            response = requests.get(url, headers=header, verify=False, auth=(username, password), timeout=30)
        except requests.exceptions.ConnectionError as err:
            self.log("upgrade_cluster: Connection refused")
            self.log("[!] Error: {}".format(err))
            raise RubrikException()
        
        if response.status_code == 200:
            if response.json()['value']:
                self.log("The cluster is bootstrapped.")
                print("")
                return reachable_node_ip, node
            else:
                self.log("The cluster is not bootstrapped.")
                print("")
        return '', {}

    def job_status(self, url, auth_tuple, wait_for_completion=True, timeout=15):
        """This method gets details about a ongoing async request.

        Parametes:
            ...
        """

        if wait_for_completion:
            self.log("platform-qual: Waiting for the job to complete.")
            try:
                response = requests.get(url, verify=False, auth=auth_tuple)
            except requests.exceptions.ConnectionError as err:
                self.log("platform-qual: Connection refused.")
                # raise Exception(err)
                self.log("[!] Error: {}".format(err))
                return {}
            
            data = response.json()

            if response.status_code != 200:
                self.log("[!] Failed with status code {}.".format(response.status_code))
                self.log("[!] FAILURE: {}".format(data['message']))
                return {}

            while True:

                try:
                    response = requests.get(url, verify=False, auth=auth_tuple)
                except requests.exceptions.ConnectionError as err:
                    self.log("platform-qual: Connection refused.")
                    # raise Exception(err)
                    self.log("[!] Error: {}".format(err))
                    return {}
                
                data = response.json()

                if response.status_code != 200:
                    self.log("[!] Failed with status code {}.".format(response.status_code))
                    self.log("[!] FAILURE: {}".format(data['message']))
                    return {}

                
                job_status = data['status']

                in_progress_status = ["QUEUED", "RUNNING", "FINISHING", "TO_FINISH", "TO_RETRY", "ACQUIRING", "TO_YIELDING", "YIELDING", "TO_YIELDED", "YIELDED"]

                canceling_status = ["CANCELING", "TO_CANCEL"]

                failing_status = ["TO_UNDO", "UNDOING"]

                if job_status == "SUCCEEDED":
                    self.log("platform-qual: Job complete\n")
                    job_status = data['status']
                    break
                elif job_status == "CANCELED":
                    self.log("platform-qual: Job Cancelled\n")
                    job_status = data['status']
                    break
                elif job_status in in_progress_status:
                    self.log("platform-qual: Job Progress {}%\n".format(data['progress']))
                    job_status = data['status']
                    time.sleep(10)
                    continue
                elif job_status in canceling_status:
                    self.log("platform-qual: Job is being Cancelled {}%\n".format(data['progress']))
                    job_status = data['status']
                    time.sleep(10)
                    continue
                elif job_status in failing_status:
                    self.log("platform-qual: Job Failing {}%\n".format(data['progress']))
                    job_status = data['status']
                    time.sleep(10)
                    continue
                else:
                    # Job FAILED
                    self.log("platform-qual: Job Failed\n")
                    job_status = data['status']
                    raise Exception('{}'.format(str(data)))

        else:
            try:
                response = requests.get(url, verify=False, auth=auth_tuple)
            except requests.exceptions.ConnectionError as err:
                self.log("platform-qual: Connection refused.")
                # raise Exception(err)
                self.log("[!] Error: {}".format(err))
                return {}
            
            data = response.json()

            if response.status_code != 200:
                self.log("[!] Failed with status code {}.".format(response.status_code))
                self.log("[!] FAILURE: {}".format(data['message']))
                return {}
        
        return data

    def api_call(self, method, url, success_code, auth_tuple, payload=None, headers=None):
        """This method is created for making API calls.

        Arguments:
            ...
        """

        self.log("platform-qual: Attempting an API call.")
        self.log("platform-qual: {} - {}".format(method, url))
        try:
            if method == 'GET':
                response = requests.get(url, verify=False, auth=auth_tuple)
            elif method == 'POST':
                response = requests.post(url, verify=False, data=json.dumps(payload), auth=auth_tuple)
            elif method == 'PATCH':
                response = requests.patch(url, verify=False, data=json.dumps(payload), auth=auth_tuple)
            elif method == 'PUT':
                response = requests.put(url, verify=False, data=json.dumps(payload), auth=auth_tuple)
            elif method == 'DELETE':
                response = requests.delete(url, verify=False, data=json.dumps(payload), auth=auth_tuple)
            else:
                self.log("[!] Error: Invalid method. Must be one of ['GET', 'PUT', 'POST', 'PATCH', 'DELETE'].")
                return False, {}
        except requests.exceptions.ConnectionError as err:
            self.log("platform-qual: Connection refused.")
            self.log("[!] Error: {}".format(err))
        
        if response.status_code != success_code:
            self.log("[!] Failed with status code {}.".format(response.status_code))
            self.log("[!] FAILURE: {}".format(response.text))
            return False, {}
        
        if response.json():
            return True, response.json()
        else:
            return True, {}




