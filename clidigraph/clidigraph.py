# make code as python 3 compatible as possible
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import contextlib
import itertools
import json
import logging
import os
import re
import subprocess
import threading

import fasteners
import graphviz

LOGGER = logging.getLogger()

DEFAULT = 'default'

def build_parser():
    parser = argparse.ArgumentParser(description='Maintain a labelled digraph')
    parser.add_argument('--config-dir', type=str, default=os.path.join(os.environ['HOME'], '.config', 'clidigraph'))
    parser.add_argument('--graph', type=str, default='graph')
    parsers = parser.add_subparsers(dest='command')

    nodes_parser = parsers.add_parser('nodes', help='Show nodes')
    remove_parser = parsers.add_parser('nonode')
    remove_parser.add_argument('node', action='append', type=str)

    parsers.add_parser('trigger', help='Run the trigger event')
    parsers.add_parser('dump', help='Dump the data (liable to change)')
    parsers.add_parser('shell', help='Open a python shell to edit data')

    show_parser = parsers.add_parser('show', help='Show all nodes')
    show_parser.add_argument('--before', '-b', type=str, help='Show nodes that lead to this node', action='append')
    show_parser.add_argument('--after', '-a', type=str, help='Show the nodes that can be reached from these nodes', action='append')

    config_parser = parsers.add_parser('config', help='Change settings')
    action = config_parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--list', action='store_true', default=False)
    action.add_argument('--set', type=str, default=False, nargs=2)

    rename_parser = parsers.add_parser('rename', help='Rename a node')
    rename_parser.add_argument('old', type=str)
    rename_parser.add_argument('new', type=str)

    node_parser = parsers.add_parser('node', help='Add a node')
    node_parser.add_argument('name', type=str)

    edge_parser = parsers.add_parser('edge', help='Add an edge')
    edge_parser.add_argument('source', type=str)
    edge_parser.add_argument('target', type=str)
    edge_parser.add_argument('label', type=str, default=DEFAULT, nargs='?')

    no_edge = parsers.add_parser('noedge', help='Remove an edge')
    no_edge.add_argument('source', type=str)
    no_edge.add_argument('target', type=str)
    no_edge.add_argument('label', type=str, default=DEFAULT, nargs='?')


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

def before_graph(graph, x):
    "Return the subgraph of things leading to x."
    return reverse_graph(after_graph(reverse_graph(graph), x))

def reverse_graph(graph):
    result = dict()
    result['nodes'] = list(graph['nodes'])
    result['edges'] = dict()
    for source in graph['edges']:
        for label, target in graph['edges'][source]:
            result['edges'].setdefault(target, list())
            result['edges'][target].append((label, source))

    return result

def after_graph(graph, root):
    result = dict(edges={}, nodes=set())
    border = set([root])

    visited = set()
    while border:
        new_border = set()
        for x in border:
            result['edges'].setdefault(x, set())
            result['edges'][x] = list(graph['edges'].get(x, []))
            for _, target in result['edges'][x]:
                new_border.add(target)

        new_border -= visited
        border = new_border
        visited |= new_border
    return result


def merge_graph(a, b):
    result = dict(nodes=[], edges=dict())
    existing_edges = set()
    result['nodes'] = list(sorted(set(itertools.chain(a['nodes'], b['nodes']))))

    for source in set.union(set(a['edges']), set(b['edges'])):
        result['edges'][source] = list(set.union(
            set(map(tuple, a['edges'].get(source, list()))),
            set(map(tuple, b['edges'].get(source, list())))))
    return result

def get_tag_color(tag, data):
    tags = sorted(data['tags'])
    colors = ('red', 'green', 'blue', 'purple')
    if len(tag) > len(colors):
        raise Exception('Too many colors')

    return dict(zip(tags, colors))[tag]

def render_graph(data, before, after):
    rendered_nodes = set()
    graphviz_graph = graphviz.Digraph()

    def render_node(name):
        tag = data['node_info'].get(name, dict()).get('tag')
        if tag:
            kwargs = dict(fillcolor=get_tag_color(tag, data), style='filled')
        else:
            kwargs = dict()
        LOGGER.debug('Color of %r %r %r', name, tag, kwargs)
        return graphviz_graph.node(name, **kwargs)

    if after is not None or before is not None:
        result_graph = dict(nodes=list(), edges={})
        if after:
            for after_node in after:
                result_graph = merge_graph(
                    result_graph,
                    after_graph(data, after_node))

        if before:
            for before_node in before:
                result_graph = merge_graph(
                    result_graph,
                    before_graph(data, before_node))
    else:
        result_graph = data

    for node in result_graph['nodes']:
        if node not in rendered_nodes:
            rendered_nodes.add(node)
            render_node(node)

    for source in result_graph['edges']:

        if source not in rendered_nodes:
            rendered_nodes.add(source)
            render_node(source)

        for (label, target) in result_graph['edges'][source]:

            if target not in rendered_nodes:
                rendered_nodes.add(target)
                render_node(target)

            if label == DEFAULT:
                graphviz_graph.edge(source, target)
            else:
                graphviz_graph.edge(source, target, label=label)

    return graphviz_graph.source



DEFAULT_SETTINGS = dict(trigger=None)

def main():
    args = build_parser().parse_args()

    if not os.path.isdir(args.config_dir):
    	os.mkdir(args.config_dir)

    data_file = os.path.join(args.config_dir, args.graph)
    with with_data(data_file) as data:
        data.setdefault('edges', dict())
        data.setdefault('nodes', list())
        data.setdefault('settings', dict())
        for key, value in DEFAULT_SETTINGS.items():
            data['settings'].setdefault(key, value)
        if args.command == 'dump':
            print(json.dumps(data, indent=4))
        elif args.command == 'shell':
            import IPython
            IPython.embed()
            try:
                IPython.start_ipython(user_ns=dict(data=data))
            except Exception:
                pass

        elif args.command == 'config':
            if args.list:
                for key, item in data['settings'].items():
                    print(key, item)
            elif args.set:
                key, value = args.set
                data['settings'][key] = value

            else:
                raise Exception('No action')

        elif args.command == 'edge':
            possible_sources = [n for n in data['nodes'] if re.search(args.source, n)]
            possible_targets = [n for n in data['nodes'] if re.search(args.target, n)]
            try:
                source, = possible_sources
            except:
                raise ValueError(possible_sources)
            target, =  possible_targets

            data['edges'].setdefault(source, [])
            data['edges'][source].append((args.label, target))
        elif args.command == 'noedge':
            source, = [n for n in data['nodes'] if re.search(args.source, n)]
            data['edges'][source].remove([args.label, target])
        elif args.command == 'show':
            print(render_graph(data, before=args.before, after=args.after))
        elif args.command == 'nonode':
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
        elif args.command == 'rename':
            old, = [n for n in data['nodes'] if re.search(args.old, n)]

            if args.new in data['nodes']:
                raise Exception('{!r} is already a node'.format(args.new))
            data['nodes'].remove(old)
            data['nodes'].append(args.new)
            if old in data['edges']:
                data['edges'][args.new] = data['edges'].pop(old)

            for source in list(data["edges"]):
                data["edges"][source] = [(label, args.new if target == old else target) for label, target in data["edges"][source]]



        elif args.command == 'node':
            trigger_change = True
            if args.name in data['nodes']:
                raise Exception('Not {!r} already exists'.format(args.name))
            data['nodes'].append(args.name)
        elif args.command == 'nodes':
            for node in sorted(data['nodes']):
                print(node)
        elif args.command == 'trigger':
            pass
        else:
            raise ValueError(args.command)

        if TRIGGERS_CHANGE[args.command]:
            subprocess.check_call(data['settings']['trigger'], shell=True)

TRIGGERS_CHANGE = dict(show=False, node=True, config=False, nodes=False, edge=True, dump=False, nonode=True, trigger=True, shell=True, noedge=True, rename=True)
