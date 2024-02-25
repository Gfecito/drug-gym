import argparse
import dgym as dg

def get_data(path):

    deck = dg.MoleculeCollection.load(
        f'{path}/DSi-Poised_Library_annotated.sdf',
        reactant_names=['reagsmi1', 'reagsmi2', 'reagsmi3']
    )

    reactions = dg.ReactionCollection.from_json(
        path = f'{path}/All_Rxns_rxn_library.json',
        smarts_col = 'reaction_string',
        classes_col = 'functional_groups'
    )

    building_blocks = dg.datasets.disk_loader(f'{path}/Enamine_Building_Blocks_Stock_262336cmpd_20230630.sdf')
    fingerprints = dg.datasets.fingerprints(f'{path}/Enamine_Building_Blocks_Stock_262336cmpd_20230630_atoms.fpb')

    import torch
    import pyarrow.parquet as pq
    table = pq.read_table(f'{path}/sizes.parquet')[0]
    sizes = torch.tensor(table.to_numpy())

    return deck, reactions, building_blocks, fingerprints, sizes

def get_oracles(path, sigma=0.5):

    # Docking oracles
    from dgym.envs.oracle import DockingOracle, NoisyOracle
    from dgym.envs.utility import ClassicUtilityFunction

    config = {
        'center_x': 44.294,
        'center_y': 28.123,
        'center_z': 2.617,
        'size_x': 22.5,
        'size_y': 22.5,
        'size_z': 22.5,
        'search_mode': 'balanced',
        'scoring': 'gnina',
        'seed': 5
    }

    # Create noiseless evaluators
    docking_oracle = DockingOracle(
        'ADAM17 affinity',
        receptor_path=f'{path}/ADAM17.pdbqt',
        config=config
    )

    # Make utility functions
    ideal = (8.5, 11)
    acceptable = (7.125, 11)
    
    docking_utility = ClassicUtilityFunction(
        docking_oracle,
        ideal=ideal, acceptable=acceptable
    )

    noisy_docking_utility = ClassicUtilityFunction(
        NoisyOracle(docking_oracle, sigma),
        ideal=ideal, acceptable=acceptable
    )

    return docking_oracle, docking_utility, noisy_docking_utility

def get_drug_env(
        deck,
        reactions, building_blocks, fingerprints, sizes,
        docking_oracle,
        docking_utility
    ):
    
    import pandas as pd
    from dgym.molecule import Molecule
    from dgym.envs.designer import Designer, Generator
    from dgym.envs.drug_env import DrugEnv

    designer = Designer(
        Generator(building_blocks, fingerprints, sizes),
        reactions,
        cache = True
    )

    # select first molecule
    import random
    def select_molecule(deck):
        initial_index = random.randint(0, len(deck))
        initial_molecule = deck[initial_index]
        if len(initial_molecule.reactants) == 2 \
            and designer.match_reactions(initial_molecule):
            return initial_molecule
        else:
            return select_molecule(deck)

    initial_molecules = [select_molecule(deck) for _ in range(5)]
    initial_library = dg.MoleculeCollection(initial_molecules) # 659
    initial_library.update_annotations()

    drug_env = DrugEnv(
        designer,
        library = initial_library,
        assays = [docking_oracle],
        budget = 500,
        utility_function = docking_utility,
    )

    return drug_env

def get_drug_agent(docking_utility, args):

    from dgym.agents import SequentialDrugAgent
    from dgym.agents.exploration import EpsilonGreedy

    # Run the experiment
    sequence = [
        {'name': 'ideate', 'parameters': {'temperature': 0.5, 'size': 10, 'strict': False}},
        {'name': 'ideate', 'parameters': {'temperature': 0.5, 'size': 10, 'strict': True}},
        {'name': 'ADAM17 affinity'},
    ]

    drug_agent = SequentialDrugAgent(
        sequence = sequence,
        utility_function = docking_utility,
        exploration_strategy = EpsilonGreedy(epsilon = args.epsilon),
        branch_factor = 1
    )

    return drug_agent


# Parse command line arguments
parser = argparse.ArgumentParser()
parser.add_argument("--epsilon", type=float, help="Epsilon parameter in the exploration strategy")
parser.add_argument("--out_dir", type=str, help="Where to put the resulting JSONs")

args = parser.parse_args()

# Load all data
path = '../../../../dgym-data'
(
    deck,
    reactions,
    building_blocks,
    fingerprints,
    sizes
) = get_data(path)

# Make oracles
docking_oracle, docking_utility, noisy_docking_utility = get_oracles(path, sigma=0.5)

# Get environment
drug_env = get_drug_env(
    deck,
    reactions, building_blocks, fingerprints, sizes,
    docking_oracle,
    docking_utility
)

# Get agent
drug_agent = get_drug_agent(noisy_docking_utility, args)

# Run experiment
from dgym.experiment import Experiment
experiment = Experiment(drug_agent, drug_env)
result = experiment.run(**vars(args))

# Export results
import json
import uuid
from utils import serialize_with_class_names

file_path = f'{args.out_dir}/selection_epsilon_{uuid.uuid4()}.json'
result_serialized = serialize_with_class_names(result)
json.dump(result_serialized, open(file_path, 'w'))