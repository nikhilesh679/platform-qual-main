#!/usr/bin/python3
#------------------------------------------------------------------------------
# Copyright (c) 2021, HCL Technologies Ltd. All rights reserved.
#------------------------------------------------------------------------------

"""
This module contains Rubrik Platform Qualification code
"""



import os
import ansible_runner

class UsbPrecheck():
    """This class holds the methods used in USB manufacturing pre-check
    Arguments:
        None
    """

    # def __init__(self, enable_logging=True):
    #     PlatformQual.__init__(self, enable_logging=enable_logging)
    
    def hw_check(self):
        input = self.input
        cluster = self.cluster
        # Set ANSIBLE_HOST_KEY_CHECKING=False
        os.environ['ANSIBLE_HOST_KEY_CHECKING'] = "False"
        # ANSIBLE_DEBUG=1

        for index, node in enumerate(cluster['nodes'], start=1):

            self.log("Starting USB pre-requisite checks on the node [{}] - {}".format(index, node['hostname']))

            vendor = {
                "RDL740" : "dell740",
                "RDL6420" : "dell6420",
                "RHPDL360" : "hp360",
                "RHPDL380" : "hp380",
                "RC240" : "cisco240",
                "RC220" : "cisco220"
            }

            for entry in vendor.keys():
                if node['hostname'].startswith(entry):
                    vendor = vendor[entry]
                    # print(vendor)
                    break
            
            # check which IPMI is working
            ipmi_ip = node['ipmi']['address']
            ipv6_ip = node['ipv6']['address']
            ipmi_username = node['ipmi']['default_admin_user']
            ipmi_password = 'RubrikAdminPassw'

            self.log("usb-precheck: Waiting for the USB Pre-check to start.")
            
            with open(os.getcwd() + "/yaml_routines/inv", "w") as inv:
                print("[ipmi_hosts:vars]", file=inv)
                print("user={}".format(ipmi_username), file=inv)
                print("pass={}".format(ipmi_password), file=inv)
                print("[ipmi_hosts]", file=inv)
                print("{} ansible_ssh_user={} ansible_ssh_pass={}".format(ipmi_ip, ipmi_username, ipmi_password), file=inv)
            
            # run ansible playbook to grab data
            r = ansible_runner.run(
                playbook = os.getcwd() + "/yaml_routines/redfish_grab.yml",
                inventory = os.getcwd() + "/yaml_routines/inv",
                quiet = True
            )
            if r.status != 'successful':
                ipmi_password = "ADMIN"
                with open(os.getcwd() + "/yaml_routines/inv", "w") as inv:
                    lines = inv.readlines()
                    lines[2] = "pass={}".format(ipmi_password)
                    lines[4] = "{} ansible_ssh_user={} ansible_ssh_pass={}".format(ipmi_ip, ipmi_username, ipmi_password)
                    inv.writelines(lines)
                
                r = ansible_runner.run(
                    playbook = os.getcwd() + "/yaml_routines/redfish_grab.yml",
                    inventory = os.getcwd() + "/yaml_routines/inv",
                    quiet = True
                )
                if r.status != 'successful':
                    self.log("[!] Error: Node [{}] - {} is not accepting standard passwords. Ignoring node {}.".format(index, node['hostname'], index))
                    continue

            result = r.get_fact_cache(ipmi_ip)

            self.log("usb-precheck: Findings for the node [{}] - {} are displayed below.")
            print("")
            if vendor == 'dell740':
                pass
            elif vendor == 'dell6420':
                pass
            elif vendor == 'hp380':
                pass
            elif vendor == 'hp360':
                pass
            elif vendor == 'cisco240':
                TPM = result['system']['entries'][0][1]['TrustedModules'][0]
                USERS = result['user']['entries']
                # self.log("TPM: {}, {}".format(TPM['InterfaceType'], TPM['status']['state']))

            elif vendor == 'cisco220':
                pass

            # print(json.dumps(result, indent=2))
