import time
import json
import requests

class SetUpNetwork():

    def __init__(self):
        ''' This is init method for the setupnetwork'''

    def setup(self):

        cluster = self.cluster
        cluster_name = cluster['cluster']['name']
        admin_email = cluster['bootstrap_credentials']['email']
        admin_password = cluster['bootstrap_credentials']['password']

        setupnetwork_ip = cluster['nodes'][0]['ipv6']['address']
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
        enable_encryption = True
        node_data_ips = {}


        dns_search_domains = [domain for domain in cluster['cluster']['dns_search_domains']]
        dns_nameservers = [server for server in cluster['cluster']['dns_nameservers']]
        ntp_servers = [server for server in cluster['cluster']['ntp_servers']]

        if node_config is None or isinstance(node_config, dict) is not True:
            raise Exception("You must provide a valid dictionary for 'node_config' holding node names and management IPs.")

        if dns_search_domains is None:
            dns_search_domains = []
        elif isinstance(dns_search_domains, list) is not True:
            raise Exception("You must provide a valid list for 'dns_search_domains'.")

        if dns_nameservers is None:
            dns_nameservers = ['8.8.8.8']
        elif isinstance(dns_nameservers, list) is not True:
            raise Exception("You must provide a valid list for 'dns_nameservers'.")

        if ntp_servers is None:
            ntp_servers = ['pool.ntp.org']
        elif isinstance(ntp_servers, list) is not True:
            raise Exception("You must provide a valid list for 'ntp_servers'.")

        using_ipmi_config = False
        using_data_config = False

        if ipmi_gateway is not None and ipmi_subnet_mask is not None and isinstance(node_ipmi_ips, dict):
            using_ipmi_config = True

        if data_gateway is not None and data_subnet_mask is not None and isinstance(node_data_ips, dict):
            using_data_config = True

        setupnetwork_config={}

        setupnetwork_config["enableSoftwareEncryptionAtRest"] = enable_encryption
        setupnetwork_config["name"] = cluster_name
        setupnetwork_config["dnsNameservers"] = dns_nameservers
        setupnetwork_config["dnsSearchDomains"] = dns_search_domains
        setupnetwork_config["ntpServerConfigs"] = []
        for server in ntp_servers:
            setupnetwork_config["ntpServerConfigs"].append({"server": server})
        
        setupnetwork_config["adminUserInfo"] = {}
        setupnetwork_config["adminUserInfo"]['password'] = admin_password
        setupnetwork_config["adminUserInfo"]['emailAddress'] = admin_email
        setupnetwork_config["adminUserInfo"]['id'] = "admin"

        setupnetwork_config["nodeConfigs"] = {}
        for node_name, node_ip in node_config.items():
            setupnetwork_config["nodeConfigs"][node_name] = {}
            setupnetwork_config["nodeConfigs"][node_name]['managementIpConfig'] = {}
            setupnetwork_config["nodeConfigs"][node_name]['managementIpConfig']['netmask'] = management_subnet_mask
            setupnetwork_config["nodeConfigs"][node_name]['managementIpConfig']['gateway'] = management_gateway
            setupnetwork_config["nodeConfigs"][node_name]['managementIpConfig']['address'] = node_ip
            if management_vlan is not None:
                setupnetwork_config["nodeConfigs"][node_name]['managementIpConfig']['vlan'] = management_vlan

        if (using_ipmi_config):
            for node_name, ipmi_ip in node_ipmi_ips.items():
                if node_name not in setupnetwork_config["nodeConfigs"]:
                    raise Exception("Non-existent node name specified in IPMI addresses.")
                setupnetwork_config["nodeConfigs"][node_name]['ipmiIpConfig'] = {}
                setupnetwork_config["nodeConfigs"][node_name]['ipmiIpConfig']['netmask'] = ipmi_subnet_mask
                setupnetwork_config["nodeConfigs"][node_name]['ipmiIpConfig']['gateway'] = ipmi_gateway
                setupnetwork_config["nodeConfigs"][node_name]['ipmiIpConfig']['address'] = ipmi_ip
                if ipmi_vlan is not None:
                    setupnetwork_config["nodeConfigs"][node_name]['ipmiIpConfig']['vlan'] = ipmi_vlan

        if (using_data_config):
            for node_name, data_ip in node_data_ips.items():
                if node_name not in setupnetwork_config["nodeConfigs"]:
                    raise Exception("Non-existent node name specified in DATA addresses.")
                setupnetwork_config["nodeConfigs"][node_name]['dataIpConfig'] = {}
                setupnetwork_config["nodeConfigs"][node_name]['dataIpConfig']['netmask'] = data_subnet_mask
                setupnetwork_config["nodeConfigs"][node_name]['dataIpConfig']['gateway'] = data_gateway
                setupnetwork_config["nodeConfigs"][node_name]['dataIpConfig']['address'] = data_ip
                if data_vlan is not None:
                    setupnetwork_config["nodeConfigs"][node_name]['dataIpConfig']['vlan'] = data_vlan

        setupnetwork_config['isSetupNetworkOnly']=True
        print(setupnetwork_config)

        url = 'https://[' + setupnetwork_ip + '%' + 'ens192]/api' + '/internal' + '/cluster/me/setupnetwork'
        header = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Host': '[' + setupnetwork_ip + ']'
            }

        try:
            response = requests.post(url, data=json.dumps(setupnetwork_config), verify=False, headers=header, auth=None, timeout=30)
            self.log(url)

        except BaseException as err:
            self.log("setupnetwork: Connection refused.")
            self.log("[!] FAILURE: {}".format(err))
            return

        status = response.json()
        print(status)
        time.sleep(30)
        ip = cluster['nodes'][0]['ipv4']['address']

        id=status['id']
        params = {'request_id': id}

        result=''
        url = 'https://' + ip + '/api' + '/internal' + '/cluster/me/setupnetwork'

        while True:
            try:
                response = requests.get(url, params=params, verify=False, auth=None)
                self.log("GET " + url + "\n")

            except requests.exceptions.ConnectionError as err:
                self.log("setupnetwork: Connection refused.")
                raise Exception(err)

            status=response.json()
            time.sleep(20)
            if status['status'] == 'IN_PROGRESS':
                self.log("completed: {}".format([key for key, value in status.items() if value == 'SUCCESS']))
                self.log("not started: {}".format([key for key, value in status.items() if value == 'NOT_STARTED']))
                self.log("currently ongoing: {}".format(status['message']))
                self.log("setupnetwork status: {}\n".format(status['status']))

                continue

            elif status['status'] == 'IN_PROGRESS':
                continue

            elif status['status'] == 'FAILURE' or status['status'] == "FAILED":
                raise Exception("{}".format(status['message']))
            

            elif status['status'] == 'SUCCESS':
                self.log("setupnetwork_status: {}".format(status['status']))
                self.log("setupnetwork: {}\n".format(status['message']))
                break
            else:
                self.log("{}".format(status))
                break

        self.log("setupnetwork completed successfully")

        

    def setup_ipv6(self):


        cluster = self.cluster
        cluster_name = cluster['cluster']['name']
        admin_email = cluster['bootstrap_credentials']['email']
        admin_password = cluster['bootstrap_credentials']['password']
        setupnetwork_ip = cluster['nodes'][0]['ipv6']['address']
        interface = cluster['nodes'][0]['ipv6']['interface']
        management_gateway = cluster['nodes'][0]['global_ipv6']['gateway']
        management_subnet_mask = cluster['nodes'][0]['global_ipv6']['netmask']
        node_config = {}
        for node in cluster['nodes']:
            node_config[node['hostname']] = node['global_ipv6']['address']
        management_vlan = None


        ipmi_gateway = cluster['nodes'][0]['ipmi_global_ipv6']['gateway']
        ipmi_subnet_mask = cluster['nodes'][0]['ipmi_global_ipv6']['netmask']
        ipmi_vlan = None
        node_ipmi_ips = {}
        for node in cluster['nodes']:
            node_ipmi_ips[node['hostname']] = node['ipmi_global_ipv6']['address']

        data_gateway = None
        data_subnet_mask = None
        data_vlan = None
        enable_encryption = True


        node_data_ips = {}
        dns_search_domains = [domain for domain in cluster['cluster']['dns_search_domains']]
        dns_nameservers = [server for server in cluster['cluster']['dns_nameservers']['ipv6']]
        ntp_servers = [server for server in cluster['cluster']['ntp_servers']]

        if node_config is None or isinstance(node_config, dict) is not True:
            raise Exception("You must provide a valid dictionary for 'node_config' holding node names and management IPs.")

        if dns_search_domains is None:
            dns_search_domains = []

        elif isinstance(dns_search_domains, list) is not True:
            raise Exception("You must provide a valid list for 'dns_search_domains'.")

        if dns_nameservers is None:
            dns_nameservers = ['8.8.8.8']
        elif isinstance(dns_nameservers, list) is not True:
            raise Exception("You must provide a valid list for 'dns_nameservers'.")


        if ntp_servers is None:
            ntp_servers = ['pool.ntp.org']
        elif isinstance(ntp_servers, list) is not True:
            raise Exception("You must provide a valid list for 'ntp_servers'.")


        using_ipmi_config = False
        using_data_config = False

        if ipmi_gateway is not None and ipmi_subnet_mask is not None and isinstance(node_ipmi_ips, dict):
            using_ipmi_config = True

        if data_gateway is not None and data_subnet_mask is not None and isinstance(node_data_ips, dict):
            using_data_config = True

        setupnetwork_config = {}


        setupnetwork_config["enableSoftwareEncryptionAtRest"] = enable_encryption
        setupnetwork_config["name"] = cluster_name
        setupnetwork_config["dnsNameservers"] = dns_nameservers
        setupnetwork_config["dnsSearchDomains"] = dns_search_domains
        setupnetwork_config["ntpServerConfigs"] = []
        for server in ntp_servers:
            setupnetwork_config["ntpServerConfigs"].append({"server": server})

        setupnetwork_config["adminUserInfo"] = {}
        setupnetwork_config["adminUserInfo"]['password'] = admin_password
        setupnetwork_config["adminUserInfo"]['emailAddress'] = admin_email
        setupnetwork_config["adminUserInfo"]['id'] = "admin"

        setupnetwork_config["nodeConfigs"] = {}
        for node_name, node_ip in node_config.items():
            setupnetwork_config["nodeConfigs"][node_name] = {}
            setupnetwork_config["nodeConfigs"][node_name]['managementIpConfig'] = {}
            setupnetwork_config["nodeConfigs"][node_name]['managementIpConfig']['netmask'] = management_subnet_mask
            setupnetwork_config["nodeConfigs"][node_name]['managementIpConfig']['gateway'] = management_gateway
            setupnetwork_config["nodeConfigs"][node_name]['managementIpConfig']['address'] = node_ip
            if management_vlan is not None:
                setupnetwork_config["nodeConfigs"][node_name]['managementIpConfig']['vlan'] = management_vlan

        if (using_ipmi_config):
            for node_name, ipmi_ip in node_ipmi_ips.items():
                if node_name not in setupnetwork_config["nodeConfigs"]:
                    raise Exception("Non-existent node name specified in IPMI addresses.")
                setupnetwork_config["nodeConfigs"][node_name]['ipmiIpConfig'] = {}
                setupnetwork_config["nodeConfigs"][node_name]['ipmiIpConfig']['netmask'] = ipmi_subnet_mask
                setupnetwork_config["nodeConfigs"][node_name]['ipmiIpConfig']['gateway'] = ipmi_gateway
                setupnetwork_config["nodeConfigs"][node_name]['ipmiIpConfig']['address'] = ipmi_ip
                if ipmi_vlan is not None:
                    setupnetwork_config["nodeConfigs"][node_name]['ipmiIpConfig']['vlan'] = ipmi_vlan

        if (using_data_config):
            for node_name, data_ip in node_data_ips.items():
                if node_name not in setupnetwork_config["nodeConfigs"]:
                    raise Exception("Non-existent node name specified in DATA addresses.")
                setupnetwork_config["nodeConfigs"][node_name]['dataIpConfig'] = {}
                setupnetwork_config["nodeConfigs"][node_name]['dataIpConfig']['netmask'] = data_subnet_mask
                setupnetwork_config["nodeConfigs"][node_name]['dataIpConfig']['gateway'] = data_gateway
                setupnetwork_config["nodeConfigs"][node_name]['dataIpConfig']['address'] = data_ip
                if data_vlan is not None:
                    setupnetwork_config["nodeConfigs"][node_name]['dataIpConfig']['vlan'] = data_vlan

        setupnetwork_config['isSetupNetworkOnly'] = True
        setupnetwork_config['isIpv6Mode'] = True

        print(setupnetwork_config)
        url = 'https://[' + setupnetwork_ip + '%' + 'ens160]/api' + '/internal' + '/cluster/me/setupnetwork'
        header = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Host': '[' + setupnetwork_ip + ']'
        }

        try:
            response = requests.post(url, data=json.dumps(setupnetwork_config), verify=False, headers=header, auth=None,timeout=30)

            self.log(url)


        except BaseException as err:
            self.log("setupnetwork: Connection refused.")
            self.log("[!] FAILURE: {}".format(err))
            return

        status = response.json()
        print(status)







        

    
