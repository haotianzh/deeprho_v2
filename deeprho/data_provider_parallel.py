import os
import time
import logging
from deeprho import popgen
import argparse
import numpy as np
import pickle
from sklearn.model_selection import train_test_split
import multiprocessing as mp
from multiprocessing.dummy import Pool
##########################################################################
# Settings of deeprho:
#   global_window_size = 1000 (for genealogies inference through RENT+)
#   window_size = 50 (for estimates' resolution (usually larger window size shows better performance))
# Settings of simulator:
#   n_sam = 1000
#   n_draw = 5
#   n_pop = 100
#   ne = 1e5
#   ploidy = 1
#   mutation_rate = 2.5e-8
#   sequence_length = 5e5
#   r_min = 1e-9
#   r_max = 1e-6
#
# configs = {
#     'sequence_length': 5e5,
#     'population_size': 1e5,
#     'rate': 2.5e-8,
#     'recombination_rate': 3.9e-8,
#     'ploidy': 1
# }
##########################################################################
global_window_size = 1000
window_size = 50


def build_configuration(args):
    configuration = {}
    configuration['sequence_length'] = 5e5
    configuration['rate'] = args.mutation_rate
    configuration['ploidy'] = args.ploidy
    if args.demography is not None:
        configuration['demography'] = popgen.utils.load_demography_from_file(args.demography)
    else:
        configuration['population_size'] = args.ne
    return configuration


def recombination_rate_quadratic_interpolation(nsam, i, rmin, rmax):
    rate = np.square((np.sqrt(rmax)-np.sqrt(rmin))/(nsam-1)*i + np.sqrt(rmin))
    return rate

def recombination_rate_const_interpolation(nsam, i, rmin, rmax):
    rate = (rmax-rmin) / (nsam-1)*i + rmin
    return rate

def save_training_data(path, data):
    assert path is not None, f'no file provided.'
    assert not os.path.exists(path), f'file has already existed.'
    x, y = data
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2)
    with open(path, mode='wb') as out:
        pickle.dump((x_train, x_test, y_train, y_test), out)
    logging.info(f'train size: {x_train.shape[0]}. test size: {x_test.shape[0]}')
    logging.info(f'training data has been stored in {args.out}')

def simulate(configs, args, r):
    haplotypes = []
    genealogies = []
    rhos = []
    configs['recombination_rate'] = r
    simulator = popgen.Simulator(configs)
    for data in simulator(args.npop, 1):
        logging.info(f'sampling in {r}, {data}')
        data = popgen.utils.filter_replicate(data)
        reps = popgen.utils.cut_replicate(data, window_size=global_window_size)
        haps = [rep.haplotype for rep in reps]
        inferred_genealogies = popgen.utils.rentplus(haps, num_thread=args.num_thread)
        for hap, gen in zip(haps, inferred_genealogies):
            for j in range(args.ndraw):
                start = np.random.choice(range(hap.nsites - window_size))
                haplotypes.append(hap.matrix[:, start:start + window_size])
                genealogies.append(gen[start: start + window_size])
                length = hap.positions[start + window_size] - hap.positions[start]
                ## have to redesign when demography included
                scaled_rho = 2 * configs['population_size'] * r * length
                rhos.append(scaled_rho)
    return haplotypes, genealogies, rhos


def run(args):
    assert args.out is not None, f'no output name.'
    assert args.rmax >= args.rmin, f'r_max should be greater than r_min.'
    if args.verbose:
        logging.basicConfig(format=f'[deeprho_v2] {os.path.basename(__file__)} %(levelname)s %(asctime)s - %(message)s',
                            level=logging.INFO,
                            datefmt='%m/%d %I:%M:%S')
    logging.info(f'----------- simulation -------------')
    logging.info(f'nsam:{args.nsam}, ndraw:{args.ndraw}')
    pool = Pool(args.num_thread // 2)
    haplotypes = []
    genealogies = []
    rhos = []
    # init simulator
    configs = build_configuration(args)
    # generate random haplotypes and infer their genealogies.
    paras = [(configs.copy(), args, recombination_rate_const_interpolation(args.nsam, i, args.rmin, args.rmax)) for i in range(args.nsam)]
    with pool:
        results = pool.starmap(simulate, paras)
    for result in results:
        haplotypes += result[0]
        genealogies += result[1]
        rhos += result[2]

    # build the whole set, train set and test set. compute Linkage Disequilibrium, ld_cluster, Robinson-Foulds distance, and also triplet distance.
    rfdistance = popgen.utils.rfdist([list(val) for val in genealogies], num_thread=args.num_thread)
    tridistance = popgen.utils.triplet_dist([list(val) for val in genealogies], num_thread=args.num_thread)
    lds = popgen.utils.linkage_disequilibrium(haplotypes)
    lds = np.expand_dims(np.array(lds), axis=-1)
    rfs = np.expand_dims(np.array(rfdistance), axis=-1)
    tris = np.expand_dims(np.array(tridistance), axis=-1)
    data = np.concatenate([lds,rfs,tris], axis=-1).astype(np.float64)
    rhos = np.array(rhos).reshape(-1,1)
    save_training_data(args.out, (data, rhos))
    
def gt_args(parser):
    parser.add_argument('--nsam', type=int, help='number of sampling for rhos', default=200)
    parser.add_argument('--ndraw', type=int, help='number of draws per sample', default=5)
    parser.add_argument('--npop', type=int, help='number of haplotypes', default=100)
    parser.add_argument('--ne', type=float, help='effective population size', default=1e5)
    parser.add_argument('--ploidy', type=int, help='ploidy', default=1)
    parser.add_argument('--mutation-rate', type=float, help='mutation rate', default=2.5e-8)
    parser.add_argument('--demography', type=str, help='demography file path', default=None)
    parser.add_argument('--rmin', type=float, help='minimum recombination rate', default=1e-9)
    parser.add_argument('--rmax', type=float, help='maximum recombination rate', default=5e-7)
    parser.add_argument('--num-thread', type=int, help='number of threads', default=mp.cpu_count() - 2)
    parser.add_argument('--out', type=str, help='output path')
    parser.add_argument('--verbose', help='show loggings', action='store_true')


if __name__ == '__main__':
    logging.basicConfig(format=f'[deeprho_v2] {os.path.basename(__file__)} %(levelname)s %(asctime)s - %(message)s',
                        level=logging.INFO,
                        datefmt='%m/%d %I:%M:%S')
    parser = argparse.ArgumentParser('data simulator')
    gt_args(parser)
    args = parser.parse_args()
    run(args)


    
