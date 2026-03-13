#!/usr/bin/python3
#------------------------------------------------------------------------------
# Copyright (c) 2021, HCL Technologies Ltd. All rights reserved.
#------------------------------------------------------------------------------

"""
This module contains Rubrik Platform Qualification code
"""

import click
import pprint
from PQ import platformQual


pp = pprint.PrettyPrinter(indent=2)

options = ['pxe', 'testpxe', 'test_iso', 'bootstrap', 'testbootstrap', 'cli', 'upgrade', 'addnode','decommission','install','setup','setup_ipv6','replace','preserve','entitle','rotatekeys']
options.sort()
@click.command()
@click.option('-o', '--option',type=click.Choice(options))

# Defining main function
def main(option):
    print("\n\tWelcome to Platform Qual testing.\n")
    obj = platformQual.Connect(enable_logging=True)
    
    if option == 'pxe':
        obj.pxe_mfg()
        
    elif option == 'testpxe':
        obj.test_pxe_mfg()

    elif option == 'test_iso':
        obj.test_iso_mfg()

    
    elif option == 'bootstrap':
        obj.bootstrap()
    
    elif option == 'testbootstrap':
        obj.test_cluster_bootstrap()
    
    elif option == 'cli':
        obj.test_cli()
    
    elif option == 'upgrade':
        obj.upgrade()
    
    elif option == 'addnode':
        obj.add_node()

    elif option == 'decommission':
        obj.decommission_node()
    
    elif option == 'install':
        obj.install()

    elif option == 'setup':
        obj.setup()

    elif option == 'setup_ipv6':
        obj.setup_ipv6()

    elif option == 'replace':
        obj.replace_node()

    elif option == 'preserve':
        obj.preserve()

    elif option == 'entitle':
        obj.entitleNode()

    elif option == 'rotatekeys':
        obj.rotate_keys()

    # obj = PxeMfg(enable_logging=True)
    # obj.pxe_mfg(2)
    # obj.test_pxe_mfg(1)


if __name__ == "__main__":
    main()
