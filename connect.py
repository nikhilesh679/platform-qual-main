# connect.py or ssh_module.py
import paramiko

def connecting_node():
    host = 'fe80::1270:fdff:fe88:1c85'
    interface = 'ens192'
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Attempt to connect, handle errors and return None if unsuccessful
    try:
        ssh.connect(host + '%' + interface, username="ubuntu", key_filename="pkey.pem")
        print("Successfully connected to node")
        return ssh
    except paramiko.SSHException as e:
        print("[i] Error: {}".format(e))
        return None
