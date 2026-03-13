#!/usr/bin/python3
#------------------------------------------------------------------------------
# Copyright (c) 2021, HCL Technologies Ltd. All rights reserved.
#------------------------------------------------------------------------------

"""
This module contains Rubrik Platform Qualification code
"""

import time
import json
import paramiko
import requests
import rubrik_cdm

from rubrik_cdm.exceptions import InvalidParameterException, RubrikException, APICallException

class BootstrapCluster():
    """This class contains functions related to the Bootstrapping of a Rubrik Cluster.

    Arguments:
        None
    """

    def __init__(self):
        """This is the init method for BootstrapCluster class.

        Arguments:
            None
        """

        self.mfa_done = False

    def _gather_data(self):
        """This methods gathers all cluster data from cluster.yml file and prepares payload for bootstrap API call

        Arguments:
            None
        """

        cluster = self.cluster
        cluster_name = cluster['cluster']['name']
        admin_email = cluster['bootstrap_credentials']['email']
        admin_password = cluster['bootstrap_credentials']['password']
        bootstrap_ip = cluster['nodes'][0]['ipv6']['address']
        interface = cluster['nodes'][0]['ipv6']['interface']

        management_gateway = cluster['nodes'][0]['ipv4']['gateway']
        management_subnet_mask = cluster['nodes'][0]['ipv4']['netmask']
        node_config = {}
        for node in cluster['nodes']:
            node_config[node['hostname']] = node['ipv4']['address']
        
        management_vlan = None
        ipmi_gateway = cluster['nodes'][0]['ipmi']['gateway']
        ipmi_subnet_mask = cluster['nodes'][0]['ipmi']['netmask']
        ipmi_vlan = None
        node_ipmi_ips = {}
        for node in cluster['nodes']:
            node_ipmi_ips[node['hostname']] = node['ipmi']['address']
        
        data_gateway = None
        data_subnet_mask = None
        data_vlan = None
        node_data_ips = {}
        enable_encryption = True
        skip_ipmi_setup = True
        dns_search_domains = [ domain for domain in cluster['cluster']['dns_search_domains'] ]
        dns_nameservers = [ server for server in cluster['cluster']['dns_nameservers'] ]
        ntp_servers = [ server for server in cluster['cluster']['ntp_servers'] ]

        if node_config is None or isinstance(node_config, dict) is not True:
            raise InvalidParameterException(
                "You must provide a valid dictionary for 'node_config' holding node names and management IPs.")

        if dns_search_domains is None:
            dns_search_domains = []
        elif isinstance(dns_search_domains, list) is not True:
            raise InvalidParameterException(
                "You must provide a valid list for 'dns_search_domains'.")

        if dns_nameservers is None:
            dns_nameservers = ['8.8.8.8']
        elif isinstance(dns_nameservers, list) is not True:
            raise InvalidParameterException(
                "You must provide a valid list for 'dns_nameservers'.")

        if ntp_servers is None:
            ntp_servers = ['pool.ntp.org']
        elif isinstance(ntp_servers, list) is not True:
            raise InvalidParameterException(
                "You must provide a valid list for 'ntp_servers'.")

        using_ipmi_config = False
        using_data_config = False

        if ipmi_gateway is not None and ipmi_subnet_mask is not None and isinstance(node_ipmi_ips, dict):
            using_ipmi_config = True
        if data_gateway is not None and data_subnet_mask is not None and isinstance(node_data_ips, dict):
            using_data_config = True
        
        bootstrap_config = {}
        bootstrap_config["shouldSkipIpmiSetup"] = skip_ipmi_setup
        bootstrap_config["enableSoftwareEncryptionAtRest"] = enable_encryption
        bootstrap_config["name"] = cluster_name
        bootstrap_config["dnsNameservers"] = dns_nameservers
        bootstrap_config["dnsSearchDomains"] = dns_search_domains

        bootstrap_config["ntpServerConfigs"] = []
        for server in ntp_servers:
            bootstrap_config["ntpServerConfigs"].append({"server": server})

        bootstrap_config["adminUserInfo"] = {}
        bootstrap_config["adminUserInfo"]['password'] = admin_password
        bootstrap_config["adminUserInfo"]['emailAddress'] = admin_email
        bootstrap_config["adminUserInfo"]['id'] = "admin"

        bootstrap_config["nodeConfigs"] = {}

        for node_name, node_ip in node_config.items():
            bootstrap_config["nodeConfigs"][node_name] = {}
            bootstrap_config["nodeConfigs"][node_name]['managementIpConfig'] = {}
            bootstrap_config["nodeConfigs"][node_name]['managementIpConfig']['netmask'] = management_subnet_mask
            bootstrap_config["nodeConfigs"][node_name]['managementIpConfig']['gateway'] = management_gateway
            bootstrap_config["nodeConfigs"][node_name]['managementIpConfig']['address'] = node_ip
            if management_vlan is not None:
                bootstrap_config["nodeConfigs"][node_name]['managementIpConfig']['vlan'] = management_vlan

        if (using_ipmi_config):
            for node_name, ipmi_ip in node_ipmi_ips.items():
                if node_name not in bootstrap_config["nodeConfigs"]:
                    raise InvalidParameterException(
                        "Non-existent node name specified in IPMI addresses.")
                bootstrap_config["nodeConfigs"][node_name]['ipmiIpConfig'] = {}
                bootstrap_config["nodeConfigs"][node_name]['ipmiIpConfig']['netmask'] = ipmi_subnet_mask
                bootstrap_config["nodeConfigs"][node_name]['ipmiIpConfig']['gateway'] = ipmi_gateway
                bootstrap_config["nodeConfigs"][node_name]['ipmiIpConfig']['address'] = ipmi_ip
                if ipmi_vlan is not None:
                    bootstrap_config["nodeConfigs"][node_name]['ipmiIpConfig']['vlan'] = ipmi_vlan

        if (using_data_config):
            for node_name, data_ip in node_data_ips.items():
                if node_name not in bootstrap_config["nodeConfigs"]:
                    raise InvalidParameterException(
                        "Non-existent node name specified in DATA addresses.")
                bootstrap_config["nodeConfigs"][node_name]['dataIpConfig'] = {}
                bootstrap_config["nodeConfigs"][node_name]['dataIpConfig']['netmask'] = data_subnet_mask
                bootstrap_config["nodeConfigs"][node_name]['dataIpConfig']['gateway'] = data_gateway
                bootstrap_config["nodeConfigs"][node_name]['dataIpConfig']['address'] = data_ip
                if data_vlan is not None:
                    bootstrap_config["nodeConfigs"][node_name]['dataIpConfig']['vlan'] = data_vlan
        self.log(bootstrap_config)
        # Get the first node IP address so we can use it to check bootstrap status if IPv6 is disabled.
        self.ipv4_addr = cluster['nodes'][0]['ipv4']['address']
        return bootstrap_config, bootstrap_ip, self.ipv4_addr
    
    def setup_cluster(self, wait_for_completion=True, mfa_done=False):
        """This is the method that actually triggers the upgrade job

        Keyword Arguments:
            wait_for_completion {bool} -- Flag to determine whether to wait for the bootstrap process to monitor and complete. (Default = True)
            mfa_done {bool} -- Flag to determine whether MFA is disabled for the testing purposes. (Default = False)
        """

        bootstrap_config, bootstrap_ip, ipv4_addr = self._gather_data()
        number_of_attempts = 1
        response = {}

        while number_of_attempts < 4:

            self.log("bootstrap: Starting the bootstrap process. Attempt No. {}".format(number_of_attempts))
            url = 'https://[' + bootstrap_ip + '%' + 'ens192]/api' + '/internal' + '/cluster/me/bootstrap'
            header = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Host': '[' + bootstrap_ip + ']'
            }
            try:
                response = requests.post(url, data=json.dumps(bootstrap_config), verify=False, headers=header, auth=None, timeout=30)
                # print(response.text)
            except BaseException as err:
                self.log("bootstrap: Connection refused.")
                # raise RubrikException(response.json())
                self.log("[!] FAILURE: {}".format(err))
                return
            
            if "Failed to establish a new connection: [Errno 111] Connection refused" in str(response.text):
                self.log("bootstrap: Connection refused. Waiting 30 seconds for the node to initialize before trying again.\n")
                number_of_attempts += 1
                time.sleep(30)
            elif "Cannot bootstrap from an already bootstrapped node" in str(response.text):
                self.log("No change required. The Rubrik cluster is already bootstrapped.\n")
                wait_for_completion = False
                break
            else:
                break

        if number_of_attempts == 4:
            # raise APICallException("Unable to establish a connection to the Rubrik cluster.")
            self.log("[!] FAILURE: Unable to establish a connection to the Rubrik cluster. Exiting...\n")
            return

        if wait_for_completion:
            request_id = response.json()['id']
            self.log("Information useful for tracking bootstrap:\n\n\tBootstrap IP: {}\n\tIPv4 Address: {}\n\tRequest ID: {}\n".format(bootstrap_ip, ipv4_addr, request_id))
            self.log("bootstrap: Successfully triggered the bootstrap process.")
            self._track_bootstrap_status(ipv4_addr, bootstrap_ip, request_id)
        
        bootstrap_result = self.status(bootstrap_ip)
        cluster_username = bootstrap_config['adminUserInfo']['id']
        cluster_password = bootstrap_config['adminUserInfo']['password']

        if bootstrap_result['status'] == 'SUCCESS' or wait_for_completion == False: # skip registration and disable MFA for qualification purpose
            
            # self.log("Trying to skip registration of the newly bootstrapped cluster.")
            # time.sleep(2)
            # url = 'https://' + ipv4_addr + '/api' + '/internal' + '/cluster/me' + '/skip_registration'
            # response = requests.post(url, verify=False, auth=(cluster_username, cluster_password))
            # if response.status_code > 199 and response.status_code < 210:
            #     self.log("bootatrap: Skipped cluster registration.\n")
            # elif 'already registered' in response.text:
            #     self.log("bootstrap: Cluster is already registered.\n")
            # else:
            #     self.log(response.text)
            #     print("\n")
            
            # Set MFA to disabled
            totp = False
            self.log("Trying to disable the global enforcement of mandatory MFA on the cluster.")
            time.sleep(5)
            url = 'https://' + ipv4_addr + '/api/v1/cluster/me/security/totp/setting'
            totp_config = {
                "isEnforced": False,
                "isReminderEnabled": False,
                "isTotpEnforceUndecided": False
            }
            response = requests.put(url, verify=False, data=json.dumps(totp_config), auth=(cluster_username, cluster_password), timeout=10)
            if response.status_code == 200:
                totp = True
                self.log("bootstrap: Cluster MFA is disabled.\n")
            else:
                self.log("[!] FAILURE: {}".format(response.json()['message']))
            
            # Keep MFA disabled for maximum duration allowed
            mfa = False
            self.log("Trying to remember the currently applied TOTP settings for maximum available time on the cluster. (i.e., 89 days)")
            time.sleep(5)
            url = 'https://' + ipv4_addr + '/api/v1/cluster/me/security/mfa/setting'
            mfa_config = {
                "rememberDeviceDays": 89
            }
            response = requests.put(url, verify=False, data=json.dumps(mfa_config), auth=(cluster_username, cluster_password), timeout=10)
            if response.status_code == 200:
                mfa = True
                self.log("bootstrap: Cluster MFA 'disabled' setting is going to be remembered for 89 days on the cluster.\n")
            else:
                self.log("[!] FAILURE: {}".format(response.json()['message']))
            
            # Set timezone to IST
            self.log("Trying to set timezone to Asia/Kolkata.")
            time.sleep(3)
            url = 'https://' + ipv4_addr + '/api/v1/cluster/me'
            timezone_config = {
                "name":bootstrap_config['name'],
                "timezone": {
                    "timezone": "Asia/Kolkata"
                }
            }
            response = requests.patch(url, verify=False, data=json.dumps(timezone_config), auth=(cluster_username, cluster_password), timeout=10)
            if response.status_code == 200:
                self.log("bootstrap: Timezone set to Asia/Kolkata for convenience.\n")
            else:
                self.log("[!] FAILURE: {}".format(response.json()['message']))
            
            self.mfa_done = mfa and totp
            
    
    def _track_bootstrap_status(self, ipv4_addr, ipv6_addr, request_id):
        """This method tracks the ongoing bootstrap progress.

        Arguments:
            ipv4_addr {str} -- String containing IPv4 address of one of the nodes from cluster.
            ipv6_addr {str} -- String containing IPv6 address of one of the node of cluster from where the bootstrap was initiated.
            request_id {int} -- ID of the bootstrap request.
        """
        
        self.log("bootstrap: Waiting for the bootstrap process to complete.")
        count = 0
        result = ''
        while True:
            status = self.status(ipv6_addr, request_id=request_id, ipv4_addr=ipv4_addr)
            time.sleep(15)
            result = ''
            
            if status['status'] == 'IN_PROGRESS' and count == 20:
                count = 0
                self.log("completed: {}".format([key for key, value in status.items() if value == 'SUCCESS']))
                self.log("not started: {}".format([key for key, value in status.items() if value == 'NOT_STARTED']))
                self.log("currently ongoing: {}".format(status['message']))
                self.log("bootstrap_status: {}\n".format(status['status']))
                # time.sleep(300)
                continue
            elif status['status'] == 'IN_PROGRESS':
                count += 1
                continue
            elif status['status'] == 'FAILURE' or status['status'] == "FAILED":
                result = 'FAIL'
                raise RubrikException("{}".format(status['message']))
            elif status['status'] == 'SUCCESS':
                result = 'SUCCESS'
                self.log("bootstrap_status: {}".format(status['status']))
                self.log("bootstrap: {}\n".format(status['message']))
                break
            else:
                self.log("{}".format(status))
                break
        self.log("bootstrap: Finished Bootstrap process.\n")
    
    def bootstrap(self):
        """This method starts and manages the bootstrap call.

        Arguments:
            None
        """
        self.setup_cluster()
        if not self.mfa_done:
            self.setup_cluster(wait_for_completion=False)

    def status(self, ipv6_addr, request_id=None, timeout=15, ipv4_addr=None):
        """Retrieves status of in progress bootstrap requests
        Keyword Arguments:
            request_id {str} -- ID of the bootstrap request(default: {"1"})
            timeout {int} -- The response timeout value, in seconds, of the API call. (default: {15})
        Returns:
            dict -- The response returned by `GET /internal/cluster/me/bootstrap?request_id={request_id}`.
        """

        # self.function_name = inspect.currentframe().f_code.co_name

        self.log("status: Getting the status of the Rubrik Cluster bootstrap.")
        if request_id:
            bootstrap_status_api_endpoint = '/cluster/me/bootstrap?request_id={}'.format(request_id)
        else:
            bootstrap_status_api_endpoint = '/cluster/me/bootstrap'
        self.log("backup IPv4 address for tracking: {}".format(ipv4_addr if ipv4_addr is not None else "Not provided"))
        try:
            # api_request = self.get('internal', bootstrap_status_api_endpoint, timeout=timeout, authentication=False)
            # url = 'https://' + ipv4_addr + '/api' + '/internal' + bootstrap_status_api_endpoint
            url = 'https://[' + ipv6_addr + '%' + 'ens192]' + '/api' + '/internal' + bootstrap_status_api_endpoint
            self.log(url+"\n")
            header = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Host': '[' + ipv6_addr + ']'
            }
            # response = requests.get(url, verify=False, auth=None, timeout=timeout)
            response = requests.get(url, verify=False, headers=header, auth=None, timeout=timeout)

        except APICallException:
            # if connection failed, then try to reconnect on the IPv4 address of one of the nodes
            ipv4_conn = rubrik_cdm.Connect(node_ip=ipv4_addr, api_token="abcd")
            self.log("status: trying the backup IPv4 addr to get status as the IPv6 address caused an exception.")
            api_request = ipv4_conn.get('internal', bootstrap_status_api_endpoint, timeout=timeout, authentication=False)
            return api_request

        return response.json()

    def test_cluster_bootstrap(self):
        """This methods tests the previous successful bootstrap.

        Arguments:
            None
        """

        cluster = self.cluster
        cluster_name = cluster['cluster']['name']
        username = cluster['bootstrap_credentials']['username']
        password = cluster['bootstrap_credentials']['password']

        self.log("Running the bootstrap tests on the given cluster - {}.".format(cluster_name))
        for index, node in enumerate(cluster['nodes'], start=1):

            host = node['ipv4']['address']
            interface = 'ens192' if 'bond0' in node['ipv6']['interface'] else '0'

            # Connect to the node via link local address and run PXE mfg tests
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                ssh.connect(host, username = username, password = password)
            except:
                self.log("[!] Cannot connect to the node [{}] - {} of cluster {} via link local address. Trying to connect via next available node.\n".format(index, node['hostname'], cluster_name))
                continue
            else:
                self.log("Sucessfully connected to node [{}] - {} of cluster {}.".format(index, node['hostname'], cluster_name))
            commands = [
                        'cluster get_node_statuses',
                        'cluster reset_node_status',
                        'cluster cluster_uuid',
                        'cluster cluster_name',
                        'cluster node_table',
                        'cluster discover',
                      #  'cluster reboot cluster'

                        ]
            for command in commands:
                self.log("Trying '{}'".format(command))
                try:
                    stdin, stdout, stderr = ssh.exec_command(command)
                    if 'cluster reboot cluster' in command:
                        stdin.write('yes')
                        stdin.write('\n')

                except paramiko.SSHException as e:
                    self.log("[i] Error: {}", e)
                self.log("\n" + node['hostname'] + " >> " + command + "\n" + stdout.read().decode())
                err = stderr.read().decode()
                if err:
                    self.log(err)
          #  ssh.close()
          #  self.log("Successfully tested bootstrap for the cluster - {}.\n\n".format(cluster_name))
         #   break
           # if ssh.get_transport().is_active():
           #     print("connection happening")
          #  else:
            #    print("connection not happening")
         #   for command in commands:
          #      self.log("Trying '{}'".format(command))
           #     try:
            #        _, stdout, stderr = ssh.exec_command(command)
             #       time.sleep(10)
                  #  stdout.close()
                   # print(stdout.readlines())
                   # print(stderr.read())
              #  except paramiko.SSHException as e:
              #      self.log("[i] Error: {}", e)
              #  self.log("\n\n" + node['hostname'] + cluster['bootstrap_credentials']['username'] + cluster['bootstrap_credentials']['password'] + " >> " + command + "\n" + stdout.read().decode())
              #  err = stderr.read().decode()
              #  if err:
              #      self.log(err)
               # time.sleep(10)
                # stdout=None
                
            ssh.close()
            self.log("Successfully tested bootstrap for the cluster - {}.\n\n".format(cluster_name))
            break

