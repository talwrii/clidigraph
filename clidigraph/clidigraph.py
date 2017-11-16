# make code as python 3 compatible as possible
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)


import graphviz
import argparse
import contextlib
import json
import os
import threading

import fasteners


def build_parser():
    parser = argparse.ArgumentParser(description='Maintain a labelled digraph')
    parser.add_argument('--config-dir', type=str, default=os.path.join(os.environ['HOME'], '.config', 'clidigraph'))
    parser.add_argument('--name', type=str, default='graph')
    parsers = parser.add_subparsers(dest='command')

    remove_parser = parsers.add_parser('remove')
    remove_parser.add_argument('node', action='append', type=str)

    subparser = parsers.add_parser('show', help='Show all nodes')
    subparser = parsers.add_parser('edge', help='')
    subparser.add_argument('source', type=str)
    subparser.add_argument('target', type=str)
    subparser.add_argument('label', type=str, default=DEFAULT, nargs='?')
    return parser

def read_json(filename):
    if os.path.exists(filename):
        with open(filename) as stream:
            return json.loads(stream.read())
    else:
        return dict()

DATA_LOCK = threading.Lock()
@contextlib.contextmanager
def with_data(data_file):
    "Read from a json file, write back to it when we are finished"
    with fasteners.InterProcessLock(data_file + '.lck'):
        with DATA_LOCK:
            data = read_json(data_file)
            yield data

            output = json.dumps(data)
            with open(data_file, 'w') as stream:
                stream.write(output)



def main():
    args = build_parser().parse_args()

    if not os.path.isdir(args.config_dir):
    	os.mkdir(args.config_dir)

    data_file = os.path.join(args.config_dir, args.name)
    with with_data(data_file) as data:
        data.setdefault('edges', dict())
        if args.command == 'edge':
            data['edges'].setdefault(args.source, [])
            data['edges'][args.source].append((args.label, args.target))
        elif args.command == 'show':
            rendered_nodes = set()
            graphviz_graph = graphviz.Digraph()
            for source in data['edges']:

                if source not in rendered_nodes:
                    rendered_nodes.add(source)
                    graphviz_graph.node(source)

                for (label, target) in data['edges'][source]:

                    if target not in rendered_nodes:
                        rendered_nodes.add(target)
                        graphviz_graph.node(target)

                    if label == DEFAULT:
                        graphviz_graph.edge(source, target)
                    else:
                        graphviz_graph.edge(source, target, label=label)
            print(graphviz_graph.source)
        elif args.command == 'remove':
            for node in args.node:
                if node in data['edges']:
                    del data['edges'][node]

            for graph_node in data['edges']:
                for pair in list(data['edges'][graph_node]):
                    k, target = pair
                    if target in args.node:
                        data['edges'][graph_node].remove(pair)

        else:
            raise ValueError(args.command)

DEFAULT = 'default'
