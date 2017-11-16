# make code as python 3 compatible as possible
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import contextlib
import json
import os
import threading

import fasteners
import graphviz


def build_parser():
    parser = argparse.ArgumentParser(description='Maintain a labelled digraph')
    parser.add_argument('--config-dir', type=str, default=os.path.join(os.environ['HOME'], '.config', 'clidigraph'))
    parser.add_argument('--graph', type=str, default='graph')
    parsers = parser.add_subparsers(dest='command')

    remove_parser = parsers.add_parser('remove')
    remove_parser.add_argument('node', action='append', type=str)

    parsers.add_parser('dump', help='Dump the data (liable to change)')
    parsers.add_parser('show', help='Show all nodes')

    node_parser = parsers.add_parser('node', help='Add a node')
    node_parser.add_argument('name', type=str)

    edge_parser = parsers.add_parser('edge', help='')
    edge_parser.add_argument('source', type=str)
    edge_parser.add_argument('target', type=str)
    edge_parser.add_argument('label', type=str, default=DEFAULT, nargs='?')

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

def render_graph(data):
    rendered_nodes = set()
    graphviz_graph = graphviz.Digraph()

    for node in data['nodes']:
        if node not in rendered_nodes:
            rendered_nodes.add(node)
            graphviz_graph.node(node)

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

        return graphviz_graph.source

def main():
    args = build_parser().parse_args()

    if not os.path.isdir(args.config_dir):
    	os.mkdir(args.config_dir)

    data_file = os.path.join(args.config_dir, args.graph)
    with with_data(data_file) as data:
        data.setdefault('edges', dict())
        data.setdefault('nodes', list())
        if args.command == 'dump':
            print(json.dumps(data, indent=4))
        elif args.command == 'edge':
            if args.source not in data['nodes']:
                raise Exception('{} is not a node'.format(args.source))

            if args.target not in data['nodes']:
                raise Exception('{} is not a node'.format(args.target))

            data['edges'].setdefault(args.source, [])
            data['edges'][args.source].append((args.label, args.target))
        elif args.command == 'show':
            print(render_graph(data))
        elif args.command == 'remove':
            for node in args.node:
                if node in data['edges']:
                    del data['edges'][node]

                if node in data['nodes']:
                    data['nodes'].remove(node)

            for graph_node in data['edges']:
                for pair in list(data['edges'][graph_node]):
                    k, target = pair
                    if target in args.node:
                        data['edges'][graph_node].remove(pair)
        elif args.command == 'node':
            data['nodes'].append(args.name)
            print(data)
        else:
            raise ValueError(args.command)

DEFAULT = 'default'
