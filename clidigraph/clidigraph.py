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
    parser.add_argument('--debug', action='store_true', help='Include debug output (to stderr)')
    parser.add_argument('--config-dir', type=str, default=os.path.join(os.environ['HOME'], '.config', 'clidigraph'))
    parser.add_argument('--graph', type=str, default='graph')
    parsers = parser.add_subparsers(dest='command')

    parsers.add_parser('tags', help='Show tags')

    nodes_parser = parsers.add_parser('nodes', help='Show nodes')
    nodes_parser.add_argument('--tag', '-t', type=str, help='Output nodes with these  tags', action='append')

    remove_parser = parsers.add_parser('nonode')
    remove_parser.add_argument('node', action='append', type=str)

    tag_parser = parsers.add_parser('tag', help='Run the trigger event')
    tag_parser.add_argument('tag', type=str)
    tag_parser.add_argument('node', type=str)
    tag_parser.add_argument('--new', '-n', action='store_true', help='Create a new tag')

    notag_parser = parsers.add_parser('notag', help='Delete a tag')
    notag_parser.add_argument('tag', type=str)

    parsers.add_parser('trigger', help='Run the trigger event')
    parsers.add_parser('dump', help='Dump the data (liable to change)')
    parsers.add_parser('shell', help='Open a python shell to edit data')

    show_parser = parsers.add_parser('show', help='Show all nodes')
    show_parser.add_argument(
        '--before', '-b', type=str, action='append',
        help='Show nodes that lead to this node.'
        ' Use tag:TAGNAME to show all nodes with a tag')
    show_parser.add_argument(
        '--after', '-a', type=str, action='append',
        help='Show the nodes that can be reached from these nodes', )
    show_parser.add_argument(
        '--neighbours', '-n', type=str,
        action='append', nargs=2,
        metavar=('NODE', 'DEPTH'),
        help='Show node and neighbours up to a depth of DEPTH.'
        ' If depth is signed +2 or -2 then show parents or children')


    config_parser = parsers.add_parser('config', help='Change settings')
    action = config_parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--list', action='store_true', default=False)
    action.add_argument('--set', type=str, default=False, nargs=2)

    rename_parser = parsers.add_parser('rename', help='Rename a node')
    rename_parser.add_argument('old', type=str)
    rename_parser.add_argument('new', type=str)

    node_parser = parsers.add_parser('node', help='Add a node')
    node_parser.add_argument('name', type=str)
    node_parser.add_argument('--tag', '-t', type=str, help='Mark the node with this tag')

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

def get_nodes(data, tag=None):
    get_tag(data, tag)
    if tag is None:
        raise ValueError(tag)

    for name, info in data['node_info'].items():
        if tag in info.get('tags', list()):
            yield name

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

def before_graph(graph, x, depth=None):
    "Return the subgraph of things leading to x."
    return reverse_graph(after_graph(reverse_graph(graph), x, depth))


def reverse_graph(graph):
    result = dict()
    result['nodes'] = list(graph['nodes'])
    result['edges'] = dict()
    for source in graph['edges']:
        for label, target in graph['edges'][source]:
            result['edges'].setdefault(target, list())
            result['edges'][target].append((label, source))

    return result

def after_graph(graph, root, depth=None):
    result = dict(edges={}, nodes=set())

    visited = set()

    depths = range(depth) if depth is not None else itertools.count()

    border = set([root])
    result['nodes'].update(border)
    for _ in depths:
        new_border = set()
        for x in border:
            result['edges'].setdefault(x, set())
            result['edges'][x] = list(graph['edges'].get(x, []))
            for _, target in result['edges'][x]:
                new_border.add(target)

        new_border -= visited
        result['nodes'].update(new_border)
        visited |= new_border
        if not new_border:
            break

        border = new_border
    return result

def merge_graphs(*graphs):
    return reduce(merge_graph_pair, graphs)

def merge_graph_pair(a, b):
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
    colors = ('red', 'lightgreen', 'blue', 'purple')
    if len(tag) > len(colors):
        raise Exception('Too many colors')

    return dict(zip(tags, colors))[tag]

def empty_graph():
    return dict(nodes=list(), edges={})

def root_graph(data):
    return dict(nodes=data['nodes'], edges=data['edges'])


def render_graph(data, graph):
    rendered_nodes = set()
    graphviz_graph = graphviz.Digraph()

    def render_node(name):
        tags = data['node_info'].get(name, dict()).get('tags')
        tag = sorted(tags)[0] if tags else None
        if tag:
            kwargs = dict(tooltip='tag:' + tag, fillcolor=get_tag_color(tag, data), style='filled')
        else:
            kwargs = dict()
        LOGGER.debug('Color of %r %r %r', name, tag, kwargs)
        return graphviz_graph.node(name, **kwargs)

    for node in graph['nodes']:
        if node not in rendered_nodes:
            rendered_nodes.add(node)
            render_node(node)

    for source in graph['edges']:

        if source not in rendered_nodes:
            rendered_nodes.add(source)
            render_node(source)

        for (label, target) in graph['edges'][source]:

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

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    if not os.path.isdir(args.config_dir):
    	os.mkdir(args.config_dir)

    data_file = os.path.join(args.config_dir, args.graph)
    with with_data(data_file) as data:
        data.setdefault('tags', dict())
        data.setdefault('edges', dict())
        data.setdefault('nodes', list())
        data.setdefault('node_info', dict())
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
            source = get_node(data, args.source)
            target = get_node(data, args.target)
            data['edges'][source].remove([args.label, target])
        elif args.command == 'show':

            before_nodes = args.before and set.union(*(get_spec_nodes(data, spec) for spec in args.before))
            after_nodes = args.after and set.union(*(get_spec_nodes(data, spec) for spec in args.after))
            graph = None
            if before_nodes:
                graph = graph or empty_graph()
                graph = merge_graphs(graph, *[before_graph(data, node) for node in before_nodes])

            if after_nodes:
                graph = graph or empty_graph()
                graph = merge_graphs(graph, *[after_graph(data, node) for node in after_nodes])

            if args.neighbours:
                for specifier, depth in args.neighbours:
                    if depth.startswith('+'):
                        down_depth = int(depth[1:])
                        up_depth = 0
                    elif depth.startswith('-'):
                        up_depth = int(depth[1:])
                        down_depth = 0
                    else:
                        up_depth = down_depth = int(depth)

                    graph = graph or empty_graph()
                    seeds = get_spec_nodes(data, specifier)
                    graph = merge_graphs(graph, *[
                        merge_graphs(
                            before_graph(data, node, depth=up_depth),
                            after_graph(data, node, depth=down_depth),
                            )
                        for node in seeds])

            if graph is None:
                graph = root_graph(data)

            print(render_graph(data, graph))

        elif args.command == 'nonode':
            for node in args.node:
                if node in data['edges']:
                    del data['edges'][node]

                if node in data['nodes']:
                    data['nodes'].remove(node)
                    data['node_info'].pop(node)

            for graph_node in data['edges']:
                for pair in list(data['edges'][graph_node]):
                    k, target = pair
                    if target in args.node:
                        data['edges'][graph_node].remove(pair)
        elif args.command == 'rename':
            old, = [n for n in data['nodes'] if re.search(args.old, n)]

            if args.new in data['nodes']:
                raise Exception('{!r} is already a node'.format(args.new))

            old_info = data['node_info'].pop(old, dict())
            data['nodes'].remove(old)
            data['nodes'].append(args.new)
            if old in data['edges']:
                data['edges'][args.new] = data['edges'].pop(old)

            data['node_info'][args.new] = old_info

            for source in list(data["edges"]):
                data["edges"][source] = [(label, args.new if target == old else target) for label, target in data["edges"][source]]


        elif args.command == 'node':
            trigger_change = True
            if args.name in data['nodes']:
                raise Exception('Not {!r} already exists'.format(args.name))
            data['nodes'].append(args.name)

            if args.tag:
                data['node_info'].setdefault(args.name, dict())['tag'] = args.tag

        elif args.command == 'tag':
            node = get_node(data, args.node)
            if args.new:
                tag = args.tag
                data["tags"][tag] = list()
            else:
                tag = get_tag(data, args.tag)

            data["node_info"].setdefault(node, dict())
            data["node_info"][node].setdefault('tags', list()).append(tag)

        elif args.command == 'notag':
            tag = get_tag(data, args.tag)
            data['tags'].remove(tag)
            for v in data["node_info"].values():
                if tag in v:
                    v.remove(tag)

        elif args.command == 'nodes':
            for node in sorted(data['nodes']):
                node_tag = data['node_info'].get(node, dict()).get('tag')
                if args.tag is None or node_tag in args.tag:
                    print(node)
        elif args.command == 'tags':
            for tag in sorted(data['tags']):
                print(tag)
        elif args.command == 'trigger':
            pass
        else:
            raise ValueError(args.command)

        if TRIGGERS_CHANGE[args.command]:
            subprocess.check_call(data['settings']['trigger'], shell=True)

def get_node(data, source):
    source, = [n for n in data['nodes'] if re.search(source, n)]
    return source

def get_tag(data, name):
    tag, = [t for t in data['tags'] if re.search(name, t)]
    return tag

def get_spec_nodes(data, specifier):
    result = set()
    if specifier.startswith('tag:'):
        _, tag = specifier.split(':', 1)
        result.update(get_nodes(data, tag=tag))
    else:
        result.add(specifier)
    return result


TRIGGERS_CHANGE = dict(show=False, node=True, config=False, nodes=False, edge=True, dump=False, nonode=True, trigger=True, shell=True, noedge=True, rename=True, tag=True, tags=False, notag=True)
