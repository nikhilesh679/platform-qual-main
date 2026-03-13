import paramiko

class entitlement():

    def entitleNode(self,param=0):

        cluster= self.cluster
        input=self.input

        for index, node in enumerate(self.cluster['nodes'], start=1):
            if param != index and param != 0:

                continue

            host = node['ipv6']['address']
            interface = 'ens160' if 'bond0' in node['ipv6']['interface'] else '0'
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                ssh.connect(host + "%" + interface, username="admin", password="rubrik")

            except paramiko.SSHException as e:
                self.log("[i] Error: {}".format(e))

            else:
                self.log("Successfully connected to node {}.".format(node['hostname']))

            vendor=''
            if node['hostname'].startswith("RDL740"):
                vendor="RDL740"

            elif node['hostname'].startswith("RHPDL360"):
                vendor="RHPDL360"
            elif node['hostname'].startswith("RC240"):
                vendor="RC240"

            elif node['hostname'].startswith("RDL6420"):
                vendor="RDL6420"
            elif node['hostname'].startswith("RC220"):
                vendor="RC220"
            elif node['hostname'].startswith("RHPDL380"):
                vendor="RHPDL380"

            else:
                self.log("Node entitlement Id is not there")

            entitlement_id=""
        
            for id,value in input['entitlement_ids'].items():
        
                if id == vendor:
                    entitlement_id= value
            print(entitlement_id)
            command='cluster entitle_node'
            try:
                stdin, stdout, stderr = ssh.exec_command(command)
                if 'entitle_node' in command:
                    stdin.write("1\n")
                    stdin.write("guruprasad.b@rubrik.com\n")
                    stdin.write("Entitle_node@2023\n")
                    stdin.write(entitlement_id)
                    stdin.write("\n")
                    stdin.write("n\n")
                    stdin.write("n\n")

            except paramiko.SSHException as e:
                self.log("[i] Error: {}".format(e))

            self.log("\n\n" + node['hostname'] + " >> " + command + "\n" + stdout.read().decode())
            err = stderr.read().decode()
            if err:
                self.log(err)
            ssh.close()

