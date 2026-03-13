#!/usr/bin/python3
#------------------------------------------------------------------------------
# Copyright (c) 2021, HCL Technologies Ltd. All rights reserved.
#------------------------------------------------------------------------------

"""
This module contains Rubrik Platform Qualification code
"""

import pprint
import json
import time

pp = pprint.PrettyPrinter(indent=2)

class SecurityTest():
    """This class contains functions related to the Security TC of Key rotation.

    Arguments:
        none
    """

    def rotate_keys(self):
        """This method contains the procedure for security test case.
        
        Arguments:
            None
        """

        cluster = self.cluster
        input = self.input['kmip_data']
        cluster_name = cluster['cluster']['name']
        cluster_username = cluster['bootstrap_credentials']['username']
        cluster_password = cluster['bootstrap_credentials']['password']
        auth_tuple = (cluster_username, cluster_password)

        # Check whether cluster is bootstrapped
        cluster_ip, _ = self.check_bootstrap()

        if not cluster_ip:
            print("")
            self.log("[!] Error: Either the cluster '{}' is not bootstrapped, or there is some other error.")
            self.log("Security test can't continue. Exiting...\n\n")
            return
        
        # Check whether cluster is encrypted
        self.log("security-test: The cluster '{}' is bootstrapped. Checking whether it is encrypted.".format(cluster_name))
        url = 'https://' + cluster_ip + '/api' + '/internal' + '/cluster/me/is_encrypted'
        result_is_enc, data_is_enc = self.api_call('GET', url, 200, auth_tuple)
        
        if not result_is_enc:
            return {}
        
        if not data_is_enc['value']:
            self.log("security-test: The cluster '{}'  is not encrypted at the time of bootstrap. Neither software nor hardware encryption is present.".format(cluster_name))
            self.log("security-test: Such a cluster is unfit to run this security test case. Encrypt and retry.")
            self.log("Security test can't continue. Exiting...\n\n")
            return
        
        self.log("security-test: The cluster '{}' is encrypted.".format(cluster_name))
        print("")

        # Import a certificate
        self.log("security-test: Begin import-cert routine.")
        data_import_cert = self.import_certificate(input, cluster_ip, auth_tuple)

        if not data_import_cert:
            self.log("security-test: Importing certificate failed.")
            self.log("security-test: Exiting...\n\n")
            return

        # Specify client configuration
        self.log("security-test: Begin add-client routine.")
        data_add_client = self.add_kmip_client(input, cluster_ip, auth_tuple)

        if not data_add_client:
            self.log("security-test: Specifying client configuration failed.")
            self.log("security-test: Exiting...\n\n")
            return

        # Add a KMIP server
        self.log("security-test: Begin add-server routine.")
        data_add_server = self.add_kmip_server(input, data_import_cert, cluster_ip, auth_tuple)

        if not data_add_server:
            self.log("security-test: Adding KMIP server failed.")
            self.log("security-test: Exiting...\n\n")
            return

        # Rotate keys with KMIP (External + S/w)
        self.log("security-test: Begin rotate-kmip routine.")
        data_rotate_kmip = self._rotate('kmip', cluster_ip, auth_tuple)

        if not data_rotate_kmip:
            self.log("security-test: Key rotation with KMIP is failed.")
        
        # Rotate keys with TPM (Internal + H/w)
        self.log("security-test: Begin rotate-tpm routine.")
        data_rotate_tpm = self._rotate('tpm', cluster_ip, auth_tuple)

        if not data_rotate_tpm:
            self.log("security-test: Key rotation with TPM is failed.")
        
        self.log("security-test: Key rotation security test has ended.\n\n")

    def _rotate(self, key_protection, cluster_ip, auth_tuple):
        """This method triggers and monitors key rotation.

        Arguments:
            ...
        """

        self.log("key-rotate: Triggering a key rotation with '{}' for all nodes in the cluster. A reboot may be required depending on the rotation specification.".format(key_protection))
        
        rotate_keys_config = {
            "keyProtection": key_protection,
            "keyRecovery": False
        }
        url = 'https://' + cluster_ip + '/api/internal/cluster/me/security/key_rotation'
        result_key_rot, data_key_rot = self.api_call('POST', url, 202, auth_tuple, payload=rotate_keys_config)
        
        if not result_key_rot:
            return {}

        self.log("key-rotate: Successfully triggered key rotation with {}. Tracking progress...\n".format(key_protection))
        rotate_progress_url = 'https://' + cluster_ip + '/api/internal/cluster/me/security/request/' + data_key_rot['id']
        rotate_job = self.job_status(rotate_progress_url, auth_tuple)
        if rotate_job['status'] == 'CANCELED':
            self.log("key-rotate: Key rotation with '{}' is cancelled.".format(key_protection))
        elif rotate_job['status'] == 'SUCCEEDED':
            self.log("key-rotate: Key rotation with '{}' is succeeded.".format(key_protection))
        print("")
        return rotate_job

    def add_kmip_server(self, input, data_import_cert, cluster_ip, auth_tuple):
        """This method adds a certificate for KMIP Server to use into the cluster.

        Arguments:
            ...
        """

        self.log("add-kmip-server: Checking whether the server with the address '{}' is already added.".format(input['server_ip']))
        url = 'https://' + cluster_ip + '/api' + '/v1' + '/cluster/me/security/kmip/server'
        result_get_kmip_server, data_get_kmip_server = self.api_call('GET', url, 200, auth_tuple)
        
        if not result_get_kmip_server:
            return {}
        
        server_to_remove = None
        for entry in data_get_kmip_server:
            if entry['serverAddress'] == input['server_ip']:
                self.log("add-kmip-server: KMIP server with the address '{}' already added.".format(input['server_ip']))
                self.log("add-kmip-server: Checking if it is associated with the desired certificate.")
                if entry['serverCertificateId'] == data_import_cert['certId']:
                    self.log("add-kmip-server: It is associated with the desired certificate. Will reuse the same certificate for key rotation.")
                    return {'status' : 'SUCCEEDED'}
                else:
                    self.log("add-kmip-server: It is not associated with the desired certificate.")
                    self.log("add-kmip-server: Editing that server config.")
                break

        add_kmip_server_config = {
            "serverAddress": input['server_ip'],
            "serverCertificateId": data_import_cert['certId'],
            "serverPort": input['server_port']
            }

        self.log("add-kmip-server: Trying to configure the KMIP server.")
        url = 'https://' + cluster_ip + '/api' + '/v1' + '/cluster/me/security/kmip/server'
        result_add_kmip_server, data_add_kmip_server = self.api_call('PUT', url, 202, auth_tuple, payload=add_kmip_server_config)
        
        if not result_add_kmip_server:
            return {}
        
        self.log("add-kmip-server: Successfully triggered addition of KMIP server. Tracking progress...\n")
        addition_progress_url = 'https://' + cluster_ip + '/api/internal/cluster/me/security/request/' + data_add_kmip_server['id']
        addition_job = self.job_status(addition_progress_url, auth_tuple)
        if addition_job['status'] == 'CANCELED':
            self.log("add-kmip-server: Server addition is cancelled.")
        elif addition_job['status'] == 'SUCCEEDED':
            self.log("add-kmip-server: Successfully added the KMIP server.")
        print("")
        return addition_job

    def add_kmip_client(self, input, cluster_ip, auth_tuple):
        """This methods adds KMIP client configuration to the cluster.

        Arguments:
            ...
        """

        self.log("add-kmip-client: Checking whether there exists a client config already.")
        url = 'https://' + cluster_ip + '/api' + '/v1' + '/cluster/me/security/kmip/client'
        result_get_kmip_client, data_get_kmip_client = self.api_call('GET', url, 200, auth_tuple)
        
        if not result_get_kmip_client:
            return {}

        if data_get_kmip_client:
            self.log("add-kmip-client: KMIP client configuration already exists.")
            self.log("add-kmip-client: Modifying that configuration.")
        else:
            self.log("add-kmip-client: KMIP is not configured.")
            self.log("add-kmip-client: Specifying a new configuration.")

        add_kmip_client_config = {
            "username": input['client_username'],
            "password": input['client_password']
        }

        self.log("add-kmip-client: Trying to specify KMIP client configuration.")
        # url = url # Same as prev URL
        result_add_kmip_client, data_add_kmip_client = self.api_call('PUT', url, 202, auth_tuple, payload=add_kmip_client_config)
        
        if not result_add_kmip_client:
            return {}
        
        self.log("add-kmip-client: Successfully triggered the KMIP client specification. Now tracking progress till it's done.")
        client_progress_url = 'https://' + cluster_ip + '/api/internal/cluster/me/security/request/' + data_add_kmip_client['id']
        client_job = self.job_status(client_progress_url, auth_tuple)
        if client_job['status'] == 'CANCELED':
            self.log("add-kmip-client: Specifying KMIP client job is cancelled.")
        elif client_job['status'] == 'SUCCEEDED':
            self.log("add-kmip-client: KMIP client specification is successful.")
        print("")
        return client_job

    def import_certificate(self, input, cluster_ip, auth_tuple):
        """This method imports a certificate for KMIP Server to use into the cluster.

        Arguments:
            ...
        """

        self.log("import-cert: Checking whether the certificate with the name '{}' already exists.".format(input['cert_name']))
        url = 'https://' + cluster_ip + '/api' + '/v1' + '/certificate'
        result_get_certificate, data_get_certificate = self.api_call('GET', url, 200, auth_tuple)
        

        if not result_get_certificate:
            return{}
        
        cert_to_patch = None
        for entry in data_get_certificate['data']:
            if entry['name'] == input['cert_name']:
                self.log("import-cert: Certificate with the name '{}' already exists.".format(input['cert_name']))
                self.log("import-cert: Checking if it's associated with an existing KMIP configuration.")
                url = 'https://' + cluster_ip + '/api' + '/v1' + '/cluster/me/security/kmip/server'
                result_get_servers, servers = self.api_call('GET', url, 200, auth_tuple)
                
                if not result_get_servers:
                    return {}
                
                for server in servers:
                    if entry['certId'] == server['serverCertificateId']:
                        self.log("import-cert: It is associated with '{}' server. Deleting it.".format(server['serverAddress']))

                        url = 'https://' + cluster_ip + '/api' + '/v1' + '/cluster/me/security/kmip/server' + '?server_address=' + server['serverAddress']
                        result_del_server, data_del_server = self.api_call('DELETE', url, 202, auth_tuple)
                        
                        if not result_del_server:
                            return {}

                        self.log("import-cert: Successfully triggered deletion of that redundant certificate. Tracking progress...\n")
                        deletion_progress_url = 'https://' + cluster_ip + '/api/internal/cluster/me/security/request/' + data_del_server['id']
                        deletion_job = self.job_status(deletion_progress_url, auth_tuple)
                        if deletion_job['status'] == 'CANCELED':
                            self.log("import-cert: Server deletion is cancelled.")
                        elif deletion_job['status'] == 'SUCCEEDED':
                            self.log("import-cert: Server deletion is successful.")
                                    
                self.log("import-cert: Will now try to modify the data in the existing certificate instead.")
                cert_to_patch = entry['certId']
                break

        import_cert_config = {
            "name": input['cert_name'],
            "pemFile": input['cert_text'],
            "description": input['cert_name'] + " 1"
        }

        if cert_to_patch:
            self.log("import-cert: Trying to modify the given certificate for KMIP server.")
            url = 'https://' + cluster_ip + '/api' + '/v1' + '/certificate' + '/' + cert_to_patch
        else:
            self.log("import-cert: Trying to import the given certificate for KMIP server.")
            url = 'https://' + cluster_ip + '/api' + '/v1' + '/certificate'
        
        if cert_to_patch:
            result_add_certificate, data_add_certificate = self.api_call('PATCH', url, 200, auth_tuple, payload=import_cert_config)
        else:
            result_add_certificate, data_add_certificate = self.api_call('POST', url, 200, auth_tuple, payload=import_cert_config)
        
        if not result_add_certificate:
            return {}
        
        if cert_to_patch:
            self.log("import-cert: Successfully modified the given certificate.")
        else:
            self.log("import-cert: Successfully imported the given certificate.")
        print("")
        return data_add_certificate
