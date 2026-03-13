# !/usr/bin/python3
# ------------------------------------------------------------------------------
# Copyright (c) 2021, HCL Technologies Ltd. All rights reserved.
# ------------------------------------------------------------------------------

"""
This module contains Rubrik Platform Qualification code
"""

import click
import pprint
from PQ import platformQual


class PQE:

    def __init__(self):
        self.options = ['pxe', 'testpxe', 'bootstrap', 'testbootstrap', 'cli', 'upgrade', 'addnode', 'decommission',
                        'install', 'setup', 'replace', 'preserve', 'entitle']
        self.options.sort()
        self.obj = platformQual.Connect(enable_logging=True)

    def run_test(self, option):
        print("\n\tWelcome to Platform Qual testing.\n")

        if option == 'pxe':
            self.obj.pxe_mfg()
        elif option == 'testpxe':
            self.obj.test_pxe_mfg()
        elif option == 'bootstrap':
            self.obj.bootstrap()
        elif option == 'testbootstrap':
            self.obj.test_cluster_bootstrap()
        elif option == 'cli':
            self.obj.test_cli()
        elif option == 'upgrade':
            self.obj.upgrade()
        elif option == 'addnode':
            self.obj.add_node()
        elif option == 'decommission':
            self.obj.decommission_node()
        elif option == 'install':
            self.obj.install()
        elif option == 'setup':
            self.obj.setup()
        elif option == 'replace':
            self.obj.replace_node()
        elif option == 'preserve':
            self.obj.preserve()
        elif option == 'entitle':
            self.obj.entitleNode()


@click.command()
@click.option('-o', '--option', type=click.Choice(PQE().options))
def main(option):
    pqe = PQE()
    pqe.run_test(option)


if __name__ == "__main__":
    main()