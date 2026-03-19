#!/usr/bin/python3
# ------------------------------------------------------------------------------
# Copyright (c) 2021, HCL Technologies Ltd. All rights reserved.
# ------------------------------------------------------------------------------

"""
This module contains Rubrik Platform Qualification code
"""

import os
import pprint
import time
import json
import paramiko
import requests
import subprocess

from tqdm import tqdm

pp = pprint.PrettyPrinter(indent=2)


class UpgradeCluster():
    """This class contains functions related to the CDM upgrade of a Rubrik Cluster.

    Arguments:
        none
    """

    def progress(self, transferred: int, total: int):
        """This method shows progressbar on console.

        Arguments:
            transferred {int} -- Number of bytes that have been transferred.
            total {int} -- Total number of bytes to be transferred.
        """

        # Return progress every 50 MB
        if (transferred / (1024 * 1024)) % 50 != 0:
            return
        pbar = tqdm(total=int(total), ascii=True, unit='iB', unit_scale=True)
        pbar.update(transferred)
        print("\tTransferred: {:.3f} GB out of: {:.3f} GB".format(transferred / (1024 * 1024 * 1024),
                                                                  total / (1024 * 1024 * 1024)), end='\r')

    def tqdmWrapViewBar(*args, **kwargs):
        """This methids defines tqdm viewer and configures callback.
        """

        pbar = tqdm(*args, **kwargs)  # make a progressbar
        last = [0]  # last known iteration, start at 0

        def viewBar2(transferred, total):
            if (transferred / (1024 * 1024)) % 50 != 0:
                pbar.total = int(total)
                pbar.update(int(transferred - last[0]))  # update pbar with increment
                # pbar.update(transferred)
                last[0] = transferred  # update last known iteration

        return viewBar2, pbar  # return callback, tqdmInstance

    def copy_tarball(self, node, username, password, src):
        """This method copies the tarball to the node with sftp.

        Arguments:
            node {str} -- Node IP address to enter the cluster
            username {str} -- Cluster username
            password {str} -- Cluster password
            src {str} -- Build URL of the desired version of tarball.
        """

        if os.path.isfile('./' + src.split('/')[-1]):
            os.remove('./' + src.split('/')[-1])

        # Staging
        # Download the tarball and sig file on localhost
        self.log("Staging: Downloading the tarball on localhost.")
        if os.path.isfile('./' + src.split('/')[-1]):
            self.log("Staging: It's already present in the current directory.")
        else:
            response = requests.get(src, stream=True)
            tarball_total_bytes = int(response.headers.get('content-length', 0))
            block_size = 50 * 1024 * 1024  # 50 Megabyte
            pbar = tqdm(total=tarball_total_bytes, unit='iB', unit_scale=True)
            with open(src.split('/')[-1], 'wb') as f:
                for data in response.iter_content(block_size):
                    pbar.update(len(data))
                    f.write(data)
            pbar.close()
            if tarball_total_bytes != 0 and pbar.n != tarball_total_bytes:
                print("ERROR, something went wrong. Exiting")
                return
            self.log("Staging: Downloading tarball finished.")

        self.log("Staging: Downloading the sig file on localhost.")
        src = src + '.sig'
        if os.path.isfile('./' + src.split('/')[-1]):
            self.log("Staging: It's already present in the current directory.")
        else:
            response = requests.get(src, stream=True)
            sig_total_bytes = int(response.headers.get('content-length', 0))
            block_size = 1024  # 1 Kilobyte
            pbar = tqdm(total=sig_total_bytes, unit='iB', unit_scale=True)
            with open(src.split('/')[-1], 'wb') as f:
                for data in response.iter_content(block_size):
                    pbar.update(len(data))
                    f.write(data)
            pbar.close()
            if sig_total_bytes != 0 and pbar.n != sig_total_bytes:
                print("ERROR, something went wrong. Exiting")
                return
            self.log("Staging: Downloading sig file finished.")
        src = src[:-4]
        print("")

        # Cleanup and transfer
        self.log("Transfer: Connecting to the node using SFTP.")
        tran = paramiko.Transport(node)
        tran.connect(None, username, password)
        sftp = paramiko.SFTPClient.from_transport(tran)

        # Cleanup
        # Empty the contents of '/upgrade'
        files = sftp.listdir(path='upgrade/')
        if files:
            for file in files:
                sftp.remove('upgrade/' + file)

        # Transfer
        # Send the tarball and sig file to the node via SFTP
        self.log("Transfer: Sending tarball to the node using SFTP.")
        cbk, pbar = self.tqdmWrapViewBar(total=tarball_total_bytes, unit='iB', unit_scale=True)
        sftp.put(src.split('/')[-1], 'upgrade/' + src.split('/')[-1], callback=cbk)
        pbar.close()
        self.log("Transfer: Uploading tarball finished.")

        self.log("Transfer: Sending sig file to the node using SFTP.")
        src = src + '.sig'
        cbk, pbar = self.tqdmWrapViewBar(total=sig_total_bytes, unit='iB', unit_scale=True)
        sftp.put(src.split('/')[-1], 'upgrade/' + src.split('/')[-1], callback=cbk)
        pbar.close()
        self.log("Transfer: Uploading tarball finished.")
        src = src[:-4]
        print("")

        # Clear localhost
        # Delete the downloaded file from localhost
        self.log("Transfer: Deleteing the downloaded file(s), if any.")
        if os.path.isfile('./' + src.split('/')[-1]):
            os.remove('./' + src.split('/')[-1])
        else:
            raise ValueError("file {} is not a file or dir.".format('./' + src.split('/')[-1]))

        src = src + '.sig'
        if os.path.isfile('./' + src.split('/')[-1]):
            os.remove('./' + src.split('/')[-1])
        else:
            raise ValueError("file {} is not a file or dir.".format('./' + src.split('/')[-1]))
        self.log("Transfer: Deleted the downloaded file(s), if any.")
        print("")

    def trigger_upgrade(self, host, username, password, node):
        """This methods triggeres upgrade task

        Arguments:
            host {str} -- IP of the cluster
            username {str} -- Username of the cluster.
            password {str} -- Password for the given username.
            node {dict} -- Dictionary containing the node details with key-value structure as defined in the Rubrik's cluster YAML files.
        """

        cluster = self.cluster
        cluster_name = cluster['cluster']['name']

        # Connect to the cluster
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.log("Trigger: Attempting to start the upgrade.")
        try:
            ssh.connect(host, username=username, password=password)
        except:
            self.log("[!] Cannot connect to the cluster. Exiting...\n")
            return
        else:
            self.log("Sucessfully connected to the cluster {}.".format(cluster_name))
        self.log("Trying '{}'".format('cluster upgrade start'))

        try:
            stdin, stdout, stderr = ssh.exec_command('cluster upgrade start')
            time.sleep(2)
            stdin.write('yes\n')
            stdin.flush()
            time.sleep(2)
            stdin.write('y\n')
            stdin.flush()
            time.sleep(2)
            stdin.write('y\n')
            stdin.flush()
        except BaseException as e:
            self.log("[i] Error: {}".format(e))

        self.log("\n" + node['hostname'] + " >> cluster upgrade start" + "\n" + stdout.read().decode())
        # print('\n')
        err = stderr.read().decode()
        if err:
            self.log(err)
        self.log("Trigger: Successfully triggered the upgrade.")
        print("")

    def monitor_upgrade(self, host, username, password, node):
        """This method monitors the ongoing upgrade task.

        Arguments:
            host {str} -- IP of the cluster
            username {str} -- Username of the cluster.
            password {str} -- Password for the given username.
            node {dict} -- Dictionary containing the node details with key-value structure as defined in the Rubrik's cluster YAML files.
        """

        cluster = self.cluster
        cluster_name = cluster['cluster']['name']

        # Connect to the cluster
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.log("Monitor: Starting to monitor the upgrade.")
        try:
            ssh.connect(host, username=username, password=password)
        except:
            self.log("[!] Cannot connect to the cluster. Exiting...\n")
            return
        else:
            self.log("Sucessfully connected to the cluster {}.".format(cluster_name))
        self.log("Trying '{}'".format('cluster upgrade status'))

        count = 0
        # stdout, stderr = None, None
        while True:
            try:
                _, stdout, stderr = ssh.exec_command('cluster upgrade status')  # channel
            except BaseException as e:
                self.log("[i] Error: {}".format(e))

            err = stderr.read().decode()
            if err:
                self.log(err)
                break

            output = stdout.read().decode()

            # print('\n')
            if "Current upgrade status: In progress" in output:
                count += 1
                if count == 20:
                    count = 0
                    self.log("\n" + node['hostname'] + " >> cluster upgrade status" + "\n" + output)
                    print('\n')
                time.sleep(10)
                continue
            elif "Last upgrade status: Completed successfully" in output:
                self.log("Monitor: Upgrade has been completed successfully.\n\n")
                break
            elif "Current state: ERROR" in output:
                self.log("[!] Failure: Upgrade operation has failed.")
                break
            elif "Last upgrade status: Failed" in output:
                self.log("[!] Failure: Upgrade operation has failed.")
                break
            else:
                self.log("[i] Error:\n{}".format(output))
                break

            # time.sleep(30)
        ssh.close()

    def upgrade(self):
        """This method triggers manages and monitors the upgrade testcase.

        Parameters:
            None
        """

        cluster = self.cluster
        input = self.input
        username = cluster['bootstrap_credentials']['username']
        password = cluster['bootstrap_credentials']['password']

        ip, node = self.check_bootstrap()

        if not ip:
            self.log(
                "[!] Error: Either the cluster is not bootstrapped, or there is some other error. Upgrade can't continue. Exiting...")
            return

        src = input['upgrade_dest']
        # print(ip)
        self.copy_tarball(ip, 'adminstaging', password, src)
        self.trigger_upgrade(ip, username, password, node)
        self.monitor_upgrade(ip, username, password, node)

    def install(self, param=0):
        """This method will trigger the cluster install"""

        cluster = self.cluster
        input = self.input

        src = input['upgrade_dest']
        password = input['install_pass']

        for node in cluster['nodes']:
            ip = node['ipv4']['address']

        self.copy_tarball(ip, 'adminstaging', password, src)

        install_info_config = {}
        install_build = input['upgrade_dest']

        tarball_str = install_build.split('/')[-1]
        print(tarball_str)

        install_info_config['tarball'] = tarball_str

        node_details = cluster['nodes']
        for node in node_details:
            install_info_config['hosts'] = [node['hostname']]

        install_info_config['preserveHdds'] = False

        print(install_info_config)

        self.log(
            "Attempting to trigger cluster install for {} node".format([node['hostname'] for node in node_details]))

        url = 'https://' + ip + '/api' + '/internal' + '/cluster/me/install'

        header = {'Content-Type': 'application/json', 'Accept': 'application/json'}

        try:
            response = requests.post(url, data=json.dumps(install_info_config), headers=header, verify=False, auth=None)

            self.log(url)

        except requests.exceptions.ConnectionError as err:
            self.log("Install node: Connection refused.")
            raise Exception(err)

        status = response.json()
        self.log(status)

        if response.status_code != 202:
            self.log("[!] Failed with status code {}.".format(response.status_code))
            self.log("[!] FAILURE: {}".format(response.json()['message']))
            return
        self.log(
            "cluster Install triggered successfully on {} node".format([node['hostname'] for node in node_details]))

        time.sleep(30)

        id = status['id']

        ipv6_addr = cluster['nodes'][0]['ipv6']['address']
        interface = cluster['nodes'][0]['ipv6']['interface']

        pinging = subprocess.call("ping -c 1 {}".format(ipv6_addr),
                                  shell=True,
                                  stdout=open('/dev/null', 'w'),
                                  stderr=subprocess.STDOUT)

        if pinging:
            url = 'https://[' + ipv6_addr + '%' + 'ens160]/api' + '/internal' + '/cluster/me/install' + '?' + 'request_id' + '=' + str(
                id)
            header = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Host': '[' + ipv6_addr + ']'
            }
            while True:
                try:
                    response = requests.get(url, verify=False, headers=header, auth=None)
                    self.log("GET " + url + "\n")

                except requests.exceptions.ConnectionError as err:
                    self.log("reboot is happening.")
                    time.sleep(700)


                finally:
                    response = requests.get(url, verify=False, headers=header, auth=None)

                status = response.json()
                self.log(status)

                if status['status'] == 'IN_PROGRESS':
                    self.log("Install is happening: {}".format(status['message']))
                    time.sleep(300)
                    continue
                elif status['status'] == 'SUCCESS':
                    self.log("Install: {}".format(status['status']))
                    self.log("Install: {}\n".format(status['message']))
                    break
                elif status['status'] == 'FAILURE' or status['status'] == "FAILED":
                    raise Exception("{}".format(status['message']))

                else:
                    self.log("{}".format(status))
                    break

            self.log("Install completed successfully for the node {}".format(node['hostname']))

        else:
            self.log("IPV6 is pinging.")
