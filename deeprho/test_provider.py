import argparse
import os
import logging
import multiprocessing as mp
from deeprho import popgen
from deeprho.data_provider_parallel import global_window_size, window_size


def build_configuration(args):
    configuration = {}
    configuration['rate'] = args.mutation_rate
    configuration['ploidy'] = args.ploidy
    if args.rate_map is not None:
        map = popgen.utils.load_recombination_map_from_file(args.rate_map)
        configuration['recombination_rate'] = map
        configuration['sequence_length'] = map.sequence_length
    else:
        configuration['recombination_rate'] = args.recombination_rate
        configuration['sequence_length'] = args.sequence_length
    if args.demography is not None:
        configuration['demography'] = popgen.utils.load_demography_from_file(args.demography, mode='generation', generation=29)
    else:
        configuration['population_size'] = args.ne
    return configuration

def simulate_single_genome(configs, args):
    simulator = popgen.Simulator(configs)
    print(configs)
    genome = next(simulator(args.npop, 1))
    return genome


def run(args):
    assert args.out is not None, f'no output name.'
    if args.demography is not None:
        assert os.path.exists(args.demography)
    if args.rate_map is not None:
        assert os.path.exists(args.rate_map)
    configs = build_configuration(args)
    genome = simulate_single_genome(configs, args)
    with open(args.out, 'w') as vcf_file:
        genome.ts.write_vcf(output=vcf_file)


def gt_args(parser):
    parser.add_argument('--npop', type=int, help='number of haplotypes', default=100)
    parser.add_argument('--ne', type=float, help='effective population size', default=1e5)
    parser.add_argument('--ploidy', type=int, help='ploidy', default=1)
    parser.add_argument('--mutation-rate', type=float, help='mutation rate', default=2.5e-8)
    parser.add_argument('--demography', type=str, help='demography file path', default=None)
    parser.add_argument('--recombination-rate', type=float, help='recombination rate')
    parser.add_argument('--sequence-length', type=float, help='sequence length of genome', default=5e5)
    parser.add_argument('--rate-map', type=str, help='recombination rate map', default=None)
    parser.add_argument('--num-thread', type=int, help='number of threads', default=mp.cpu_count() - 2)
    parser.add_argument('--out', type=str, help='output path')
    parser.add_argument('--verbose', help='show loggings', action='store_true')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='simulate whole genome')
    gt_args(parser)
    args = parser.parse_args(['--npop','5',
                              '--ploidy', '2',
                              # '--mutation-rate', '2.5e-8',
                              '--rate-map', '../examples/test_recombination_map.txt',
                              '--demography', '../examples/ACB_pop_sizes.csv',
                              '--demography', 'ms.txt.demo.csv',
                              '--out', '../garbo/test5.vcf'])
    run(args)