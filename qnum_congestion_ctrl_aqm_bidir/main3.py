"""
Main file of the project
"""

from omnetpypy import Experiment

if __name__ == '__main__':

    config_file = "config.yaml"
    topology_file = "yaml/topology.yaml"

    experiment = Experiment(config_file=config_file)
    experiment.run_simulations()
