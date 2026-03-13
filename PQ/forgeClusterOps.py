#!/usr/bin/python3
#------------------------------------------------------------------------------
# Copyright (c) 2021, HCL Technologies Ltd. All rights reserved.
#------------------------------------------------------------------------------

"""
This module contains Rubrik Platform Qualification code
"""

import json
import time
import paramiko
import pprint
import requests

from rubrik_cdm.exceptions import RubrikException

pp = pprint.PrettyPrinter(indent=2)

class ForgeClusterOps():
    """This class contains functions related to the forge cluster operations like node addition and deletion.

    Arguments:
        none
    """

    def add_node(self,param=0):
        """This method contains the code for node addtion.

        Arguments:
            None
        """

        cluster = self.cluster
        input = self.input
        cluster_name = cluster['cluster']['name']
       # cluster_uuid = cluster['cluster']['uuid']
        cluster_username = cluster['bootstrap_credentials']['username']
        cluster_password = cluster['bootstrap_credentials']['password']
        
        cluster_ip, cluster_node = self.check_bootstrap()

        if not cluster_ip:
            self.log("[!] Error: Either the cluster is not bootstrapped, or there is some other error. Node addition can't continue. Exiting...")
            return

        

        for index, node in enumerate(self.cluster['nodes'], start=1):
            if param != index and param != 0:
                continue
            host = node['ipv6']['address']
            interface = 'ens192' if 'bond0' in node['ipv6']['interface'] else '0'

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())


            try:
                ssh.connect(host + '%' + interface, username="ubuntu", key_filename="pkey.pem")

            except paramiko.SSHException as e:
                self.log("[i] Error: {}".format(e))
                self.log("Ignoring node [{}] - {}.\n".format(index, node['hostname']))
                continue

            else:
                self.log("Successfully connected to node [{}] - {}.".format(index, node['hostname']))

            command = 'sudo /opt/rubrik/src/scripts/dev/get_local_spray_token.py --username support$'
            self.log("Trying '{}'".format(command))

            try:
                _, stdout, stderr = ssh.exec_command(command)
                rk_support = stdout.read().decode('utf-8')
               # break
            except paramiko.SSHException as e:
                self.log("[i] Error: {}", e)

            ssh.close()
       
        rk=rk_support.split("'")
        rk_support_authentication=rk[0].strip()

       # print(rk_support_authentication)
                
        


        nodes_to_add = input['add_node']

        add_node_config = {}
        add_node_config['ipmiPassword'] = input['ipmi_pass']['post_bootstrap']
        add_node_config['nodes'] = {}
        for node in nodes_to_add:
            add_node_config['nodes'][node['hostname']] = {}

            add_node_config['nodes'][node['hostname']]['ipmiIpConfig'] = {}
            add_node_config['nodes'][node['hostname']]['ipmiIpConfig']['address'] = node['ipmi']['address']
            add_node_config['nodes'][node['hostname']]['ipmiIpConfig']['netmask'] = cluster_node['ipmi']['netmask']
            add_node_config['nodes'][node['hostname']]['ipmiIpConfig']['gateway'] = cluster_node['ipmi']['gateway']

            add_node_config['nodes'][node['hostname']]['managementIpConfig'] = {}
            add_node_config['nodes'][node['hostname']]['managementIpConfig']['address'] = node['ipv4']['address']
            add_node_config['nodes'][node['hostname']]['managementIpConfig']['netmask'] = cluster_node['ipv4']['netmask']
            add_node_config['nodes'][node['hostname']]['managementIpConfig']['gateway'] = cluster_node['ipv4']['gateway']

        # pp.pprint(add_node_config)
        self.log("add_node: Attempting to trigger node addition with {} node(s) into the {} cluster".format([node['hostname'] for node in nodes_to_add], cluster_name))
        url = 'https://' + cluster_ip + '/api' + '/internal' + '/cluster/me/node'
        header = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        try:
            response = requests.post(url, data=json.dumps(add_node_config), headers=header, verify=False, auth=(cluster_username, cluster_password))
            status=response.json()
            print(status)
        except requests.exceptions.ConnectionError as err:
            self.log("add_node: Connection refused.")
            raise RubrikException(err)
        
        if response.status_code != 202:
            self.log("[!] Failed with status code {}.".format(response.status_code))
            self.log("[!] FAILURE: {}".format(response.json()['message']))
            return
            # raise RubrikException(response.json())
        
        self.log("add_node: Successfully triggered node addition of {} node(s) to the {} cluster.".format([node['hostname'] for node in nodes_to_add], cluster_name))
        self.log("add_node: Waiting for 30 sec to have the cluster ready with add_node job.")
        time.sleep(30)
        status = response.json()
       # data_dict = json.loads(status)
       # print(data_dict)
        jobId_to_track = status['jobId']
       # print(jobId_to_track)

        result = self.track_add_node_status(cluster_ip, jobId_to_track, rk_support_authentication, cluster_username, cluster_password)
        if result == 'SUCCESS':
            self.log("add_node: Successfully added {} node(s) to the {} cluster.".format([node['hostname'] for node in nodes_to_add], cluster_name))
        else:
            self.log("add_node: Node addition of {} node(s) to the {} cluster has failed\n".format([node['hostname'] for node in nodes_to_add], cluster_name))
    
    def track_add_node_status(self, ip, track, support, username='admin', password='RubrikAdminPassword'):
        """This method tracks the status of ongoing add node operation.

        Arguments:
            ip {str} -- IP address to reach the cluster
        
        Keyword Arguments:
            username {str} -- Username of the cluster. (Default = 'admin')
            password {str} -- Password of the cluster for the given username. (Default = 'RubrikAdminPassword')
        """

        self.log("add_node: Waiting for the node addition to complete.")
        
        url = 'https://' + ip + '/api' + '/internal' + '/job/' + track
    
        header = {
             "Content-Type": "application/json",
             "Authorization":f"Bearer {support}"
         }
       # print(header)
        result = ''
        while True:
            try:
                response = requests.get(url, headers=header, verify=False)
                self.log("GET " + url + "\n")
            except requests.exceptions.ConnectionError as err:
                self.log("add_node: Connection refused.")
                raise RubrikException(err)

            if response.status_code != 200:
                self.log("[!] Failed tracking operation with status code {}.".format(response.status_code))
                # raise RubrikException(response.json())
                self.log("[!] Failure: {}".format(response.json()['message']))
                return
            status = response.json()
            self.log(status)

            if status['status'] == 'RUNNING':
                self.log("Node addition is happening")
                time.sleep(180)
                continue
            elif status['status'] == 'FAILURE' or status['status'] == "FAILED":
                result = 'FAIL'
                self.log("Node addition is failed")
                # raise RubrikException("{}".format(status['message']))
                break
            elif status['status'] == 'SUCCEEDED':
                result = 'SUCCESS'
                self.log("add_node_status: {}".format(status['status']))
                break
            else:
                self.log("{}".format(status))
                break
        
        self.log("add_node: Finished node addition.\n")
        return result

    def decommission_node(self):


        cluster = self.cluster
        input = self.input
        cluster_name = cluster['cluster']['name']
        cluster_username = cluster['bootstrap_credentials']['username']
        cluster_password = cluster['bootstrap_credentials']['password']
        cluster_ip, cluster_node = self.check_bootstrap()

        if not cluster_ip:
            self.log("[!] Error: Either the cluster is not bootstrapped, or there is some other error. Node addition can't continue. Exiting...")
            return
        nodes_to_decommission_node=input['decommission_node']
        decommission_node_config={}
        for node in nodes_to_decommission_node:
            decommission_node_config['nodeIds']=[node['hostname']]

        decommission_node_config["minTolerableNodeFailures"]= 0
        decommission_node_config["shouldSkipPrechecks"]= True
        decommission_node_config["shouldBlockOnNegativeFailureTolerance"]= True
        decommission_node_config["isDecommissionOnly"]= False
        print(decommission_node_config)

        self.log("decommission_node: Attempting to trigger node decommission with {} node(s) from the {} cluster".format([node['hostname'] for node in nodes_to_decommission_node], cluster_name))

        url = 'https://' + cluster_ip + '/api' + '/internal' + '/cluster/me/decommission_nodes'
        header = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
        }
    

        try:
            response = requests.post(url, data=json.dumps(decommission_node_config), headers=header, verify=False, auth=(cluster_username, cluster_password))
            self.log(url)

        except requests.exceptions.ConnectionError as err:
            self.log("decommission node: Connection refused.")

            raise Exception(err)

        if response.status_code != 202:
            self.log("[!] Failed with status code {}.".format(response.status_code))
            self.log("[!] FAILURE: {}".format(response.json()['message']))
            return

        status=response.json()
        self.log(status)
        if status!='':
            self.log("decommission_node: successfully triggered node decommission with {} node(s) from the {} cluster".format([node['hostname']for node in nodes_to_decommission_node], cluster_name))
        
        rk_support_authentication=''
        for node in cluster['nodes']:
            host = node['ipv6']['address']
            interface = 'ens160' if 'bond0' in node['ipv6']['interface'] else '0'
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                ssh.connect(host + '%' + interface, username="rksupport", key_filename="pkey.pem")
            except paramiko.SSHException as e:
                self.log("[i] Error: {}".format(e))
                self.log("Ignoring node {}.\n".format(node['hostname']))
                continue
            else:
                self.log("Successfully connected to node {}.".format(node['hostname']))
            command = 'sudo /opt/rubrik/src/scripts/dev/get_local_spray_token.py --username support$'
            self.log("Trying '{}'".format(command))
            try:
                _, stdout, stderr = ssh.exec_command(command)
                rk_support = stdout.read().decode('utf-8')
            except paramiko.SSHException as e:
                self.log("[i] Error: {}", e)
            
            ssh.close()
           # print(type(rk_support))
            rk=rk_support.split("'")
           # print(rk)
            rk_support_authentication=rk[0].strip()

           # print(rk_support_authentication)
        url = 'https://' + cluster_ip + '/api' + '/internal' + '/job/' + status

        header = {"Authorization":f"Bearer {rk_support_authentication}"}
        print(header)
        result=''
        while True:
            try:
                response = requests.get(url, headers= header, verify=False)
                self.log("GET " + url + "\n")
            except requests.exceptions.ConnectionError as err:
                self.log("decommission_node: Connection refused.")
                raise Exception(err)
            status=response.json()
            self.log(status)
            
            if status['status'] == 'RUNNING':
                self.log("Node decommission is ongoing")
                time.sleep(300)
                continue
            
            elif status['status'] == 'FAILURE' or status['status'] == "FAILED":
                result='failed'
                self.log(" Node decommission is failed")
                break

            elif status['status'] == 'SUCCEEDED':
                result='success'
                self.log(" Node decommission happened successfully")
                break
            else:
                self.log("{}".format(status))
                break

        if result == 'success':
            self.log("decommission_node: Successfully removed {} node(s) from the {} cluster.".format([node['hostname'] for node in nodes_to_decommission_node], cluster_name))
        else:
            self.log("decommission_node: Node decommission of {} node(s) to the {} cluster has failed\n".format([node['hostname'] for node in nodes_to_decommission_node], cluster_name))




    def replace_node(self,param=0):

        cluster = self.cluster
        input = self.input

        cluster_name = cluster['cluster']['name']
        cluster_username = cluster['bootstrap_credentials']['username']
        cluster_password = cluster['bootstrap_credentials']['password']
        cluster_ip, cluster_node = self.check_bootstrap()
        if not cluster_ip:
            self.log("[!] Error: Either the cluster is not bootstrapped, or there is some other error. Node addition can't continue. Exiting...")
            return

       # self.decommission_node()
        print(cluster_ip)
        time.sleep(10)

        rk_support_authentication = ''

        for index, node in enumerate(self.cluster['nodes'], start=1):
            if param != index and param != 0:
                continue
            host = node['ipv6']['address']
            interface = 'ens160' if 'bond0' in node['ipv6']['interface'] else '0'
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            try:
                ssh.connect(host + '%' + interface, username = "ubuntu", key_filename = "pkey.pem")
                

            except paramiko.SSHException as e:
                self.log("[i] Error: {}".format(e))
                self.log("Ignoring node [{}] - {}.\n".format(index, node['hostname']))
                continue
            else:
                self.log("Successfully connected to node [{}] - {}.".format(index, node['hostname']))

            command = 'sudo /opt/rubrik/src/scripts/dev/get_local_spray_token.py --username support$'
            self.log("Trying '{}'".format(command))
            try:
                _, stdout, stderr = ssh.exec_command(command)
                rk_support = stdout.read().decode('utf-8')
            except paramiko.SSHException as e:
                self.log("[i] Error: {}", e)

            ssh.close()
            rk = rk_support.split("'")
            rk_support_authentication = rk[0].strip()
            print(rk_support_authentication)

        node_to_replace_node = input['decommission_node']
        for node in node_to_replace_node:
            host = node['ipv6']['address']
            interface = 'ens160' if 'bond0' in node['ipv6']['interface'] else '0'
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            try:
                ssh.connect(host + '%' + interface, username=cluster_username, password=cluster_password)

            except paramiko.SSHException as e:
                self.log("[i] Error: {}".format(e))
                self.log("Ignoring node [{}] - {}.\n".format(index, node['hostname']))
                continue
            else:
                self.log("Successfully connected to node [{}] - {}.".format(index, node['hostname']))


            command = 'cluster reset_node preserve_hdd'
            try:
                stdin, stdout, stderr = ssh.exec_command(command)
                if 'reset_node preserve_hdd' in command:
                    stdin.write('yes\n')
          #          stdin.write('\n')
                    self.log("reset node preserve hdd is going on node {}.".format(node['hostname']))
          #          self.log("\n\n" + node['hostname'] + " >> " + command + "\n" + stdout.read().decode())
                    time.sleep(1100)
                    
                    
            except paramiko.SSHException as e:
                self.log("[i] Error: {}".format(e))
            self.log("\n\n" + node['hostname'] + " >> " + command + "\n" + stdout.read().decode())
            err = stderr.read().decode()
            if err:
                self.log(err)

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
                self.log("Successfully connected to node after reset_node preserve hdd {}.".format(node['hostname']))

            command = 'cat /tmp/sdtests/reset_node.out.txt'
            try:
                stdin, stdout, stderr = ssh.exec_command(command)
                reset_node_check = stdout.read()
                check = "Ran sdreset successfully on node {}".format(node['hostname'])
                if check.encode().strip() in reset_node_check:
                    print("reset_node preserve hdd successfully completed")

                else:
                    print("unable to complete the reset_node preserve hdd")

            except paramiko.SSHException as e:
                self.log("[i] Error: {}", e)
            ssh.close()



        time.sleep(10)
        node_replacement_data={}
        for node in node_to_replace_node:
            node_replacement_data['newNodeId']=node['hostname']
            node_replacement_data['oldNodeId']=node['hostname']
        
        


        node_replacement_data["preserveHdds"] = True
        print(node_replacement_data)
        url = 'https://' + cluster_ip + '/api' + '/internal' + '/node_management/replace_node'
        print(url)
        header = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                "Authorization": f"Bearer {rk_support_authentication}"

            }

        try:
            response = requests.post(url, data=json.dumps(node_replacement_data), headers=header, verify=False)
            self.log(url)

        except requests.exceptions.ConnectionError as err:
            self.log("Node replacement: Connection refused.")


            raise Exception(err)

        status = response.json()
        self.log(status)



