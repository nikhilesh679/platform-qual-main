#!/usr/bin/python3
#------------------------------------------------------------------------------
# Copyright (c) 2021, HCL Technologies Ltd. All rights reserved.
#------------------------------------------------------------------------------

"""
This module contains Rubrik Platform Qualification code
"""


import pprint
import time
import paramiko

pp = pprint.PrettyPrinter(indent=2)

class GenericCLI():
    """This class contains functions related to the Bootstrapping of a Rubrik Cluster.

    Arguments:
        None
    """

    def test_cli(self, param=0):
        """This method runs the generic CLI commands and basic hardware health commands in order to test cluster functionality.

        Keyword Arguments:
            param {int} -- The node ID in the nodes list (1, 2, 3, ...). (Default = 0, denotes all nodes)
        """

        cluster = self.cluster
        cluster_name = cluster['cluster']['name']
        bootstrapped, node = self.check_bootstrap()
        if bootstrapped:
            self.log("Starting Generic CLI and Hardware health tests..")
            
            cluster_username = cluster['bootstrap_credentials']['username']
            cluster_password = cluster['bootstrap_credentials']['password']
            self.log("Running the Generic CLI and h/w health tests on the given cluster - {}.".format(cluster_name))
            for index, node in enumerate(cluster['nodes'], start=1):
                if param != index and param != 0:
                    continue

                host = node['ipv6']['address']
                interface = 'ens192' if 'bond0' in node['ipv6']['interface'] else '0'

                # Connect to the node via link local address and run PXE mfg tests
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                try:
                    ssh.connect(host+'%'+interface, username = cluster_username, password = cluster_password)
                    # ssh = ShellHandler(host + "%" + interface, cluster_username, cluster_password)
                except:
                    self.log("[!] Cannot connect to the node [{}] - {} of cluster {}. Ignoring node {}.\n".format(index, node['hostname'], cluster_name, index))
                    continue
                else:
                    self.log("Sucessfully connected to node [{}] - {}.".format(index, node['hostname']))
                commands = [
                        # 'network re_ip',
                   'network route',
                   'network hostname',
                   'network hosts',
                   'network ifconfig',
                   'network ping google.com -c 4',
                 #  'network set_default_gateway',
                   'network static_route add',
                   'network static_route delete',
                   'network check_connectivity ' + cluster['nodes'][(index) % len(cluster['nodes'])]['ipv4']['address'] + ' 22',
                   'support cluster_support_bundle',
                   'support local_support_bundle',
                   'support log_view',
                  # 'support tunnel open',
                   'cluster hw_health',
                 #  'network re_ip'  
                ]
                delay = 0.5
                self._command_executor(cluster_username, ssh, commands, node, delay)
                ssh.close()
                self.log("Successfully tested generic CLI commands for the node {} of cluster - {}.\n\n".format(node['hostname'], cluster_name))
        # sys.exit()

        self.log("Starting remaining HW Health tests..")
        self.log("Running the hw health tests on the cluster - {}.".format(cluster_name))
        for index, node in enumerate(cluster['nodes'], start=1):
            if param != index and param != 0:
                continue

            host = node['ipv6']['address']
            interface = 'ens192' if 'bond0' in node['ipv6']['interface'] else '0'
            cluster_username = 'ubuntu'
            next_node = cluster['nodes'][(index) % len(cluster['nodes'])]

            # Connect to the node via link local address and run HW health tests
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                ssh.connect(host + "%" + interface, username = cluster_username, key_filename = "pkey.pem")
            except:
                self.log("[!] Cannot connect to the node [{}] - {} via link local address for running h/w health tests. Ignoring node {}.\n".format(index, node['hostname'], index))
                continue
            else:
                self.log("Successfully connected to node [{}] - {}.".format(index, node['hostname']))
            
            self.log("Attempting display output commands ")
            commands = [
                
                'sudo ipmitool lan print 1','sudo ipmitool mc info'
                
            ]
            delay = 0.5
            self._command_executor(cluster_username, ssh, commands, node, delay)
            
            self.log("Attempting network failover with 'down'and 'up' command")
            commands = [
                'cat /proc/net/bonding/bond0',
               # 'sudo ifconfig eth3 down',
               # 'cat /proc/net/bonding/bond0'
            ]
            delay = 3
            self._command_executor(cluster_username, ssh, commands, node, delay)

           # self.log("Attempting network failover with 'up' command")
           # commands = [
              #  'cat /proc/net/bonding/bond0',
            #   'sudo ifconfig eth3 up',
            #    'cat /proc/net/bonding/bond0'
           # ]
           # delay = 3
           # self._command_executor(cluster_username, ssh, commands, node, delay)

           # self.log("Attempting powering on and off a remote node")
           # ip = next_node['ipmi']['address']
           # user = next_node['ipmi']['default_admin_user']
           # passw = ''
           # if bootstrapped:
           #     passw = 'RubrikAdminPassw'
           # else:
           #     passw = 'ADMIN'
            
           # commands = [
           #      'sudo ipmitool -I lanplus -H ' + ip + ' -U ' + user + ' -P ' + passw + ' power status',
           #      'sudo ipmitool -I lanplus -H ' + ip + ' -U ' + user + ' -P ' + passw + ' power off',
           #      'sudo ipmitool -I lanplus -H ' + ip + ' -U ' + user + ' -P ' + passw + ' power status',
           #      'sudo ipmitool -I lanplus -H ' + ip + ' -U ' + user + ' -P ' + passw + ' power on',
           #      'sudo ipmitool -I lanplus -H ' + ip + ' -U ' + user + ' -P ' + passw + ' power status'
           # ]
           # delay = 10
           # self._command_executor(cluster_username, ssh, commands, node, delay)

            ssh.close()
            self.log("Successfully tested hardware health tests for the node [{}] - {}.\n\n".format(index, node['hostname']))
            print("\n\tWaiting 10 minutes for cluster to recover the rebooted node(s) before starting tests on the next node.\n")
            time.sleep(600)

    def _command_executor(self, user, ssh, commands, node, delay):
        """This is a helper method to executed the required commands on the cluster.
        
        Arguments:
            user {str} -- User as whom the command needs to be executed. (admin/ubuntu)
            ssh {SSHClient} -- Paramiko SSHClient object for execution of the commands.
            commands {list(str)} -- List of commands to be executed.
            node {dict} -- Dictionary containing the node details with key-value structure as defined in the Rubrik's cluster YAML files.
            delay {int} -- Gap time in seconds in between the commands execution.
        """
        
        for command in commands:
            stdin = None
            # stdout = None
            self.log("Trying '{}'".format(command))
            
            try:
                stdin, stdout, stderr = ssh.exec_command(command)
                # stdin, stdout, stderr = ssh.execute(command)
                if 'support_bundle' in command:
                    stdin.write('local')
                    stdin.write('\n')
                    
                if 'static_route add' in command:
                    stdin.write('10.0.0.0\n')
                    stdin.write('255.255.0.0\n')
                    stdin.write('N\n')
                    stdin.write('bond0\n')
                    stdin.write('10.0.0.255\n')
                    stdin.write('yes')
                    stdin.write('\n')
                
                if 'static_route delete' in command:
                    stdin.write('1\n')
                    stdin.write('yes')
                    stdin.write('\n')
                
                if 'support log_view' in command:
                    stdin.write('exit')
                    stdin.write('\n')

                if 'set_default_gateway' in command:
                    stdin.write('bond0\n')
                    stdin.write('10.0.0.255')
                    stdin.write('\n')

                if 're_ip' in command:
                    stdin.write('10.0.0.255\n')
                    stdin.write('255.255.0.0\n')
                    stdin.write('\n')
                    stdin.write('\n')
                    stdin.write('\n')
                    stdin.write('\n')
                    stdin.write('\n')
                    stdin.write('Yes')
                    stdin.write('\n')
                
                if 'cat /proc/net/bonding/bond0' in command:
                    link_checking=stdout.readlines()
                    for link in link_checking:
                        link_items = link.split(":")
                        if link_items[0]=="Currently Active Slave":
                            correct_link=link_items[1]
                            commands=[f'ethtool {correct_link}','ethtool eth2']
                            count=0
                            for command in commands:
                                stdin, stdout, stderr = ssh.exec_command(command)
                                ethtool_output= stdout.readlines()
                                for che_link in ethtool_output:
                                    ethtool_details=che_link.split(":")
                                    if ethtool_details[0].strip('\t')=="Link detected":
                                        if ethtool_details[1].strip()=="yes":
                                            count+=1
                                if count==2:
                                     commands=[f"sudo ifconfig {correct_link.strip()} down","cat /proc/net/bonding/bond0", f"sudo ifconfig {correct_link.strip()} up","cat /proc/net/bonding/bond0"]
                                     for command in commands:
                                         stdin, stdout, stderr = ssh.exec_command(command)
                                         print(stdout.readlines())
                                         time.sleep(2)
                                else:
                                    continue
                                                
                    



            
            except BaseException as e:
                self.log("[i] Error: {}".format(e))
            
            if user == 'admin':
                self.log("\n" + node['hostname'] + " >> " + command + "\n" + stdout.read().decode())
                print('\n')
            elif user == 'ubuntu':
                self.log("\nubuntu@" + node['hostname'] + ":~$ " + command + "\n" + stdout.read().decode())
                print('\n')
            err = stderr.read().decode()
            if err:
                self.log(err)
            time.sleep(delay)
