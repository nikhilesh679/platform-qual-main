#!/usr/bin/python3
#------------------------------------------------------------------------------
# Copyright (c) 2021, HCL Technologies Ltd. All rights reserved.
#------------------------------------------------------------------------------

"""
This module contains Rubrik Platform Qualification code
"""

import os
import time
import json
import paramiko
import requests
import subprocess
import sys

# from platformQual import PlatformQual

class PxeMfg():
    """This class contains methods related to PXE manufacturing and testing."""

    def log(self, message):
        # Assuming there's a log method in the parent or class
        print(message)

    def pxe_mfg(self, param=0):
        """Starts the PXE manufacturing steps."""
        os.environ['ANSIBLE_HOST_KEY_CHECKING'] = "False"

        for index, node in enumerate(self.cluster['nodes'], start=1):
            if param != index and param != 0:
                continue
            
            self.log("Starting to attempt PXE manufacturing for the node [{}] - {}".format(index, node['hostname']))
            patched = []

            pxe_srvr_ip = node['pxeserverip']
            mac_ids = node['mac_addresses'] if 'mac_addresses' in node.keys() else [node[k] for k in node.keys() if 'mac_address' in k]
            build_url = self.input['pxe_mfg_build']
            
            for mac in mac_ids:
                url = 'https://' + pxe_srvr_ip + '/manufacturing/?mac_address=' + mac + '&build_url=' + build_url + '&boot_option=manufacturing-ubuntu-18.04'
                response = requests.patch(url, verify=False)
                
                if response.status_code == 201:
                    patched.append(mac)

            if not patched:
                self.log("[!] FAILED - Patch was unsuccessful on node [{}] - {}. Ignoring node {}.\n".format(index, node['hostname'], index))
                continue
            
            self.log("MAC IDs {} of node [{}] - {} have been patched successfully.".format(patched, index, node['hostname']))

            vendor = ''
            hn = node['hostname']
            if hn.startswith(("RDL740", "RDL6420", "RDL750", "RDL660", "RDL76", "RDL6")):
                vendor = 'dell'
            elif hn.startswith(("RHPDL360", "RHPDL380")):
                vendor = 'hp'
            elif hn.startswith(("RC240", "RC220", "RC225")):
                vendor = 'cisco'
            
            self._trigger_pxe_mfg(node, index, vendor)

    def _trigger_pxe_mfg(self, node, index, vendor):
        ipmi_username = node['ipmi']['default_admin_user']
        ipmi_password = 'RubrikAdminPassw'
        ipmi_ips = [node['ipmi']['address'], node['ipmi']['reserved_dhcp_address']]

        self.log("Checking whether the node is reachable via IPMI.")
        reachable = False
        reachable_ip = ''
        for ip in ipmi_ips:
            not_pinging = subprocess.call("ping -c 1 {}".format(ip),
                                       shell=True,
                                       stdout=open('/dev/null', 'w'),
                                       stderr=subprocess.STDOUT)
            if not not_pinging:
                reachable = True
                reachable_ip = ip
                break

        if not reachable:
            self.log(f"manufacture: Node [{index}] unreachable via IPMI. Ignoring.")
            return

        self.log("manufacture: Waiting for the manufacturing process to start.")

        # Determine System URL
        if vendor == 'dell':
            url = f'https://{reachable_ip}/redfish/v1/Systems/System.Embedded.1'
        elif vendor == 'hp':
            url = f'https://{reachable_ip}/redfish/v1/Systems/1'
        elif vendor == 'cisco':
            url = f'https://{reachable_ip}/redfish/v1/Systems'
            response = requests.get(url, verify=False, auth=(ipmi_username, ipmi_password), timeout=10)
            
            if 400 <= response.status_code <= 403:
                ipmi_password = 'ADMIN' if ipmi_password == 'RubrikAdminPassw' else 'RubrikAdminPassw'
                response = requests.get(url, verify=False, auth=(ipmi_username, ipmi_password), timeout=10)
            
            # SAFE PARSING for Cisco Systems list
            try:
                data = response.json()
                url = 'https://' + reachable_ip + data['Members'][0]['@odata.id']
            except (json.JSONDecodeError, KeyError, IndexError):
                self.log(f"[!] FAILED - Could not parse System URL for Node {index}. Status: {response.status_code}")
                return

        # Get Boot Options
        response = requests.get(url, verify=False, auth=(ipmi_username, ipmi_password), timeout=10)
        if 400 <= response.status_code <= 403:
            ipmi_password = 'ADMIN' if ipmi_password == 'RubrikAdminPassw' else 'RubrikAdminPassw'
            response = requests.get(url, verify=False, auth=(ipmi_username, ipmi_password), timeout=10)

        try:
            data = response.json()
        except json.JSONDecodeError:
            self.log(f"[!] FAILED - Node {index} returned non-JSON data at {url}")
            return

        if response.status_code >= 400:
            self.log(f"[!] FAILED with status code: {response.status_code}")
            return

        # Identify PXE value
        allowable = data.get('Boot', {}).get('BootSourceOverrideTarget@Redfish.AllowableValues', [])
        self.log(f"Supported one-time-boot options: {allowable}")
        pxe_val = next((v for v in allowable if v.lower() == 'pxe'), None)

        if not pxe_val:
            self.log(f"[!] Node [{index}] doesn't support PXE boot. Ignoring.")
            return
        
        # Patch Boot Device
        payload = {"Boot": {"BootSourceOverrideEnabled": "Once", "BootSourceOverrideTarget": pxe_val}}
        headers = {'content-type': 'application/json'}
        response = requests.patch(url, data=json.dumps(payload), headers=headers, verify=False, auth=(ipmi_username, ipmi_password), timeout=10)
        
        # Cisco often returns 204 (No Content) which causes .json() to crash
        if response.status_code not in [200, 204]:
            self.log(f"[!] FAILED to set PXE boot. Status: {response.status_code}")
            return
        
        self.log(f"manufacture: PATCH command passed to set next boot to '{pxe_val}' successfully.")
        time.sleep(3)
        
        # Warm Reset the node
        reset_url = url + '/Actions/ComputerSystem.Reset'
        reset_payload = {"ResetType": "ForceRestart"}
        if vendor == 'hp':
            reset_payload['Action'] = 'ComputerSystem.Reset'

        response = requests.post(reset_url, data=json.dumps(reset_payload), headers=headers, verify=False, auth=(ipmi_username, ipmi_password), timeout=10)
        
        if response.status_code in [200, 204]:
            self.log("[!] WARNING - Node will now reset and be back online shortly.")
        else:
            self.log(f"[!] FAILED Reset with Status code: {response.status_code}")
            return
        
        time.sleep(5)
        self.log(f"manufacture: Successfully triggered manufacturing for node [{index}] - {node['hostname']}\n")

    def test_pxe_mfg(self, param=0):
        """This is the method that tests the PXE manufacturing with running the given commands.
        
        Keyword Arguments:
            param {int} -- The node ID in the nodes list (1, 2, 3, ...), 0 denotes all nodes.
        """
        print(sys.executable)
        print(sys.version)
        for index, node in enumerate(self.cluster['nodes'], start=1):
            if param != index and param != 0:
                continue

            host = node['ipv6']['address']
            interface = 'ens192' if 'bond0' in node['ipv6']['interface'] else '0'
            
            # Connect to the node via link local address and remove hosts to IPv6 mapping
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            try:
                ssh.connect(host + '%' + interface, username = "ubuntu", key_filename = "pkey.pem")
            except paramiko.SSHException as e:
                self.log("[i] Error: {}".format(e))
                continue
            else:
                self.log("Successfully connected to node [{}] - {}.".format(index, node['hostname']))
            
            command = 'sudo rm /var/lib/rubrik/hosts_to_ipv6_mapping'
            self.log("Trying '{}'".format(command))
            
            try:
                _, stdout, stderr = ssh.exec_command(command)
            except paramiko.SSHException as e:
                self.log("[i] Error: {}", e)
            
            if not stdout.read().decode():
                self.log("Success!\n")
            
            err = stderr.read().decode()
            if err and 'No such file or directory' not in err:
                self.log(err)
           
            ssh.close()

            # Connect to the node via link local address and run PXE mfg tests
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                ssh.connect(host + "%" + interface, username = "admin", password = "rubrik")
                # print("pass = rubik")
            except:
                # pass
                try:
                    ssh.connect(host + "%" + interface, username = "admin", password = "RubrikAdminPassword")
                except:
                    self.log("[!] Cannot connect to the node [{}] - {} via link local address for testing the manufacturing. Ignoring node {}.\n".format(index, node['hostname'], index))
            # print("pass = rubik")
            commands = [
                        'cluster mfg_status\n',
                        'cluster version\n',
                        'cluster reset_node_status\n',
                        'network ifconfig\n',
                        'cluster hw_health\n',
                       # 'cluster discover',
                      #  'cluster install status'
                        ]
            
            for command in commands:
                self.log("Trying '{}'".format(command))
                try:
                    stdin, stdout, stderr = ssh.exec_command(command)
                    if 'reset_node force' in command:
                        stdin.write('yes\n')
                        time.sleep(30)
                        stdin.write('yes')
                        stdin.write('\n')
                        self.log("reset node force started successfully")
                        time.sleep(1100)
                        break
                except paramiko.SSHException as e:
                    self.log("[i] Error: {}".format(e))
                self.log("\n\n" + node['hostname'] + " >> " + command + "\n" + stdout.read().decode())
                err = stderr.read().decode()
                if err:
                    self.log(err)


                
                      #  print("Successfully connected to node [{}] - {}.".format(index, node['hostname']))

            ssh.close()
            time.sleep(10)
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            try:
                ssh.connect(host + '%' + interface, username="ubuntu", key_filename="pkey.pem")
            except paramiko.SSHException as e:
                self.log("[i] Error: {}".format(e))
                continue
            else:
                self.log("Successfully connected to node after reset [{}] - {}.".format(index, node['hostname']))
            command='cat /tmp/sdtests/reset_node.out.txt'
            try:
                stdin, stdout, stderr = ssh.exec_command(command)
                reset_node_check=stdout.read()
                            # print(reset_node_check)
                check = "Ran sdreset successfully on node {}".format(node['hostname'])
                if check.encode().strip() in reset_node_check:
                    print("reset_node successfully completed")
                else:
                    print("unable to complete the reset_node")
                    

            except paramiko.SSHException as e:
                self.log("[i] Error: {}",e)
            ssh.close()
            self.log("Successfully tested PXE manufacturing process for the node [{}] - {}.\n\n".format(index, node['hostname']))

    def test_iso_mfg(self, param=0):
        """This is the method that tests the ISO manufacturing with running the given commands.
        
        Keyword Arguments:
            param {int} -- The node ID in the nodes list (1, 2, 3, ...), 0 denotes all nodes.
        """
        print(sys.executable)
        print(sys.version)
        for index, node in enumerate(self.cluster['nodes'], start=1):
            if param != index and param != 0:
                continue

            host = node['ipv6']['address']
            interface = 'ens192' if 'bond0' in node['ipv6']['interface'] else '0'
           

            # Connect to the node via link local address and run PXE mfg tests
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                ssh.connect(host + "%" + interface, username = "admin", password = "rubrik")
                # print("pass = rubik")
            except:
                # pass
                try:
                    ssh.connect(host + "%" + interface, username = "admin", password = "RubrikAdminPassword")
                except:
                    self.log("[!] Cannot connect to the node [{}] - {} via link local address for testing the manufacturing. Ignoring node {}.\n".format(index, node['hostname'], index))
            # print("pass = rubik")
            commands = [
                        'cluster mfg_status\n',
                        'cluster version\n',
                        'cluster reset_node_status\n',
                        'network ifconfig\n',
                        'cluster hw_health\n',
                        #'cluster discover',
                       
                        ]
            
            for command in commands:
                self.log("Trying '{}'".format(command))
                try:
                    stdin, stdout, stderr = ssh.exec_command(command)
        
                except paramiko.SSHException as e:
                    self.log("[i] Error: {}".format(e))
                self.log("\n\n" + node['hostname'] + " >> " + command + "\n" + stdout.read().decode())
                err = stderr.read().decode()
                if err:
                    self.log(err)

            ssh.close()
            self.log("Successfully tested ISO  manufacturing process for the node [{}] - {}.\n\n".format(index, node['hostname']))

            
   
   
