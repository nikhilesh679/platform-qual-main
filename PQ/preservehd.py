import paramiko
import time

class PreserveHdd():

    def preserve(self,param=0):

        cluster=self.cluster
        cluster_username = 'admin'
        cluster_password = 'rubrik'

        for index, node in enumerate(self.cluster['nodes'], start=1):
            if param != index and param != 0:
                continue


            host = node['ipv6']['address']
            interface = 'ens160' if 'bond0' in node['ipv6']['interface'] else '0'

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            commands=['cluster version', 'cluster mfg_status', 'cluster reset_node_status']
            

            try:
                ssh.connect(host + "%" + interface, username = cluster_username, password=cluster_password)
                shell = ssh.invoke_shell()
                time.sleep(1)

                for command in commands:
                    shell.send(command + '\n')
                    time.sleep(3)
                    output=""
                    
                    output += shell.recv(1024).decode()
                    print(output)
                    
                    print(output.strip())
                    print('-' * 40)
                #    output =shell.recv(1024)
               #     print(f'Executing command: {command}')
              #  print(output.decode())
            except paramiko.AuthenticationException:
                print(f"Authentication failed for host {host}")
            except paramiko.SSHException as sshException:
                print(f"SSH error occurred for host {host}: {str(sshException)}")
            except Exception as e:
                print(f"An error occurred for host {host}: {str(e)}")
            finally:
                ssh.close()
               
            



           # except paramiko.SSHException as e:
            #    self.log("[i] Error: {}".format(e))
                

    



