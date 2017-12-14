# pylint: disable=locally-disabled
# make code as python 3 compatible as possible
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import collections
import contextlib
import json
import logging
import os
import re
import subprocess
import sys
import threading

import fasteners
import graphviz

import editor

from . import graphs, specifiers, datastore, render

if sys.version_info[0] != 3:
    # FileNotFoundError does not exist in python 2
    raise Exception('Only works with python 3')


LOGGER = logging.getLogger()


def build_parser(): # pylint: disable=too-many-locals,too-many-locals,too-many-statements
    parser = argparse.ArgumentParser(description='Maintain a labelled digraph')
    parser.add_argument('--debug', action='store_true', help='Include debug output (to stderr)')
    parser.add_argument('--config-dir', type=str, default=os.path.join(os.environ['HOME'], '.config', 'clidigraph'))
    parser.add_argument('--graph', type=str, default='graph')
    parsers = parser.add_subparsers(dest='command')

    parsers.add_parser('tags', help='Show tags')

    nodes_parser = parsers.add_parser('nodes', help='Show nodes')
    nodes_parser.add_argument('specifier', type=str, nargs='?')

    nodes_parser.add_argument('--tag', '-t', type=str, help='Output nodes with these  tags', action='append')

    remove_parser = parsers.add_parser('nonode')
    remove_parser.add_argument('node', action='append', type=str)

    tag_parser = parsers.add_parser('tag', help='Tag a node')
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
        '--collapse', '-c', type=str, action='append',
        help='Collapse nodes after this point'
        ' Use tag:TAGNAME to show all nodes with a tag')
    show_parser.add_argument(
        '--around', '-r', type=str, action='append',
        help='Show nodes both before and after this.'
        ' Use tag:TAGNAME to show all nodes with a tag')
    show_parser.add_argument(
        '--before', '-b', type=str, action='append',
        help='Show nodes that lead to this node.'
        ' Use tag:TAGNAME to show all nodes with a tag')
    show_parser.add_argument(
        '--after', '-a', type=str, action='append',
        help='Show the nodes that can be reached from these nodes', )
    show_parser.add_argument(
        '--after-all', '-A', action='store_true',
        help='Add descendants to all selected node.')
    show_parser.add_argument(
        '--between', '-B', type=str,
        action='append', nargs=2,
        metavar=('FROM', 'TWO'),
        help='Include nodes between these two specifiers')
    show_parser.add_argument(
        '--neighbours', '-n', type=str,
        action='append', nargs=2,
        metavar=('NODE', 'DEPTH'),
        help='Show node and neighbours up to a depth of DEPTH.'
        ' If depth is signed +2 or -2 then show parents or children')
    show_parser.add_argument(
        '--highlight', '-H', action='append',
        type=str, help='Highlight nodes matching this specifier')
    show_parser.add_argument(
        '--group', '-G', action='append',
        type=str, metavar=('name', 'selector'), help='Place these node in a group. And color them the same color', nargs=2)
    show_parser.add_argument(
        '--contract', '-C', type=str, action='append',
        metavar='selector_list',
        help='Place these node in a group. And color them the same color')
    show_parser.add_argument(
        '--nodes', '-N', type=str, action='append',
        metavar='selector',
        help='Include items matching this selector')

    config_parser = parsers.add_parser('config', help='Change settings')
    action = config_parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--list', action='store_true', default=False)
    action.add_argument('--set', type=str, default=False, nargs=2)

    rename_parser = parsers.add_parser('rename', help='Rename a node')
    rename_parser.add_argument('old', type=str)
    rename_parser.add_argument('new', type=str)

    info_parser = parsers.add_parser('info', help='Show information for a node')
    info_parser.add_argument('node_selector', type=str)

    node_parser = parsers.add_parser('node', help='Add a node')
    node_parser.add_argument('name', type=str)
    node_parser.add_argument(
        '--tag', '-T', type=str,
        help='Mark the node with this tag')
    node_parser.add_argument(
        '--from', '-f', type=str, action='append', dest='from_nodes',
        help='Add a link from this node')
    node_parser.add_argument(
        '--to', '-t', type=str, action='append', dest='to_nodes',
        help='Add a link to this node')
    node_parser.add_argument(
        '--label', '-l', type=str, default=graphs.DEFAULT,
        help='Mark edges with this label')

    label_parser = parsers.add_parser('label', help='Label an existing edge')
    label_parser.add_argument('source', type=str)
    label_parser.add_argument('target', type=str)
    label_parser.add_argument('label', type=str)

    edge_parser = parsers.add_parser('edge', help='Add an edge')
    edge_parser.add_argument('source', type=str)
    edge_parser.add_argument('target', type=str)
    edge_parser.add_argument('label', type=str, default=graphs.DEFAULT, nargs='?')

    notes_parser = parsers.add_parser('note', help='Change the node associates with an entry')
    notes_parser.add_argument('node_selector', type=str)
    notes_parser.add_argument('note', type=str, nargs='?')
    notes_parser.add_argument(
        '--edit', action='store_true', default=False,
        help='Edit value with an editor')

    no_edge = parsers.add_parser('noedge', help='Remove an edge')
    no_edge.add_argument('source', type=str)
    no_edge.add_argument('target', type=str)
    no_edge.add_argument('label', type=str, default=graphs.DEFAULT, nargs='?')

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



def empty_graph():
    return dict(nodes=list(), edges={})

def root_graph(data):
    return dict(nodes=data['nodes'], edges=data['edges'])


DEFAULT_SETTINGS = dict(trigger=None)

def main(): # pylint: disable=too-many-branches
    args = build_parser().parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    if not os.path.isdir(args.config_dir):
    	os.mkdir(args.config_dir)

    data_file = os.path.join(args.config_dir, args.graph)

    if args.command == 'note':
        note_command(data_file, args)
    else:
        with with_clidi_data(data_file) as data:
            for key, value in DEFAULT_SETTINGS.items():
                data['settings'].setdefault(key, value)
            if args.command == 'dump':
                print(json.dumps(data, indent=4))
            elif args.command == 'shell':
                shell_command(data)
            elif args.command == 'config':
                config_command(args, data)

            elif args.command == 'edge':
                add_edge(data, args.source, args.target, args.label)
            elif args.command == 'label':
                label_edge(data, args.source, args.target, args.label or graphs.DEFAULT)
            elif args.command == 'noedge':
                source = specifiers.get_node(data, args.source)
                target = specifiers.get_node(data, args.target)
                data['edges'][source].remove([args.label, target])
            elif args.command == 'show':
                show(args, data)
            elif args.command == 'nonode':
                delete_node_command(args, data)
            elif args.command == 'rename':
                return rename_command(data, args.old, args.new)
            elif args.command == 'node':
                create_node(
                    data,
                    args)
            elif args.command == 'tag':
                create_tag_command(data, args)
            elif args.command == 'notag':
                delete_tag_command(data, args)
            elif args.command == 'nodes':
                list_node_command(args, data)
            elif args.command == 'tags':
                for tag in sorted(data['tags']):
                    print(tag)
            elif args.command == 'trigger':
                pass
            elif args.command == 'info':
                show_node_info_command(data, args)
            else:
                raise ValueError(args.command)

    if TRIGGERS_CHANGE[args.command]:
        LOGGER.debug('Triggering change')
        subprocess.check_call(data['settings']['trigger'], shell=True)

def note_command(data_file, args):
    with with_clidi_data(data_file) as data:
        item = data['node_info'].setdefault(specifiers.get_node(data, args.node_selector), {})

        if not args.edit:
            item['note'] = args.note

    new_value = editor.edit(contents=item.get('note', '').encode('utf8')).decode('utf8')
    with with_clidi_data(data_file) as data:
        data['node_info'][specifiers.get_node(data, args.node_selector)]['note'] = new_value

def config_command(args, data):
    if args.list:
        for key, item in data['settings'].items():
            print(key, item)
    elif args.set:
        key, value = args.set
        data['settings'][key] = value

    else:
        raise Exception('No action')

def shell_command(data):
    import IPython
    IPython.embed()
    IPython.start_ipython(user_ns=dict(data=data))

def create_tag_command(data, args):
    node = specifiers.get_node(data, args.node)
    if args.new:
        tag = args.tag
        data["tags"][tag] = list()
    else:
        tag = datastore.get_tag(data, args.tag)

    data["node_info"].setdefault(node, dict())
    data["node_info"][node].setdefault('tags', list()).append(tag)

def delete_tag_command(data, args):
    tag = datastore.get_tag(data, args.tag)
    data['tags'].remove(tag)
    for v in data["node_info"].values():
        if tag in v:
            v.remove(tag)

def show_node_info_command(data, args):
    node = specifiers.get_node(data, args.node_selector)
    print('-------------------')
    print('name: ' + node)
    for key, value in data['node_info'].get(node, dict()).items():
        print(key + ':')
        print(value)

def list_node_command(args, data):
    if args.specifier is None:
        nodes = data['nodes']
    else:
        nodes = specifiers.get_matching_nodes(data, args.specifier)

    for node in sorted(nodes):
        node_tag = data['node_info'].get(node, dict()).get('tag')
        if args.tag is None or node_tag in args.tag:
            print(node)

def delete_node_command(args, data):
    for node in args.node:
        if node in data['edges']:
            del data['edges'][node]

        if node in data['nodes']:
            data['nodes'].remove(node)
            data['node_info'].pop(node, None)

    for graph_node in data['edges']:
        for pair in list(data['edges'][graph_node]):
            _, target = pair
            if target in args.node:
                data['edges'][graph_node].remove(pair)

def show(args, data):
    before_nodes = args.before and set.union(
        *(
            specifiers.get_matching_nodes(data, spec)
            for spec in args.before))
    after_nodes = args.after and set.union(
        *(
            specifiers.get_matching_nodes(data, spec)
            for spec in args.after))

    if args.around:
        before_nodes = set.union(
            before_nodes or set(),
            *(specifiers.get_matching_nodes(data, spec) for spec in args.around))
        after_nodes = set.union(
            after_nodes or set(),
            *(specifiers.get_matching_nodes(data, spec) for spec in args.around))

    if args.group:
        grouped_nodes = collections.OrderedDict()
        for name, selector in args.group:
            grouped_nodes[name] = specifiers.get_matching_nodes(data, selector)
    else:
        grouped_nodes = dict()


    if args.highlight:
        highlighted_nodes = set.union(
            *(specifiers.get_matching_nodes(data, spec) for spec in args.highlight))
    else:
        highlighted_nodes = []

    graph = None
    if before_nodes is not None:
        graph = graph or empty_graph()
        graph = graphs.merge_graphs(graph, *[graphs.before_graph(data, node) for node in before_nodes])

    if args.between:
        graph = graph or empty_graph()
        for from_spec, to_spec in args.between:
            from_nodes = specifiers.get_matching_nodes(data, from_spec)
            to_nodes = specifiers.get_matching_nodes(data, to_spec)
            graph = graphs.merge_graphs(graph, graphs.between_graph(data, from_nodes, to_nodes))

    if args.nodes:
        graph = graph or empty_graph()
        induction_nodes = set()
        for spec in args.nodes:
            induction_nodes |= set(specifiers.get_matching_nodes(data, spec))


        graph = graphs.merge_graphs(graph, graphs.induce_graph(data, induction_nodes))


    if after_nodes is not None:
        graph = graph or empty_graph()
        graph = graphs.merge_graphs(graph, *[graphs.after_graph(data, node) for node in after_nodes])

    if args.neighbours:
        for specifier, depth in args.neighbours:
            graph = graph or empty_graph()
            seeds = specifiers.get_matching_nodes(data, specifier)
            graph = graphs.merge_graphs(graph, *[
                specifiers.neighbour_graph(data, seed, depth)
                for seed in seeds])

    if args.after_all and graph:
        graph = graphs.merge_graphs(graph, *[graphs.after_graph(data, node) for node in graph["nodes"]])


    if graph is None:
        graph = root_graph(data)

    if args.contract is not None:
        contraction_nodes = set.union(*(specifiers.get_matching_nodes(data, spec) for spec in args.contract))
        graph = graphs.contract_graph(graph, contraction_nodes)

    print(render.render_graph(data, graph, highlighted_nodes, grouped_nodes))

def create_node(data, args):
    if args.name in data['nodes']:
        raise Exception('Not {!r} already exists'.format(args.name))
    data['nodes'].append(args.name)

    if args.tag:
        data['node_info'].setdefault(args.name, dict())['tag'] = args.tag

    if args.from_nodes:
        for from_node in args.from_nodes:
            add_edge(data, from_node, 'raw:' + args.name, label=args.label)

    if args.to_nodes:
        for to_node in args.to_nodes:
            add_edge(data, 'raw:' + args.name, to_node, label=args.label)

def rename_command(data, old, new):
    old, = [n for n in data['nodes'] if re.search(old, n)]

    if new in data['nodes']:
        raise Exception('{!r} is already a node'.format(new))

    old_info = data['node_info'].pop(old, dict())
    data['nodes'].remove(old)
    data['nodes'].append(new)
    if old in data['edges']:
        data['edges'][new] = data['edges'].pop(old)

    data['node_info'][new] = old_info

    for source in list(data["edges"]):
        data["edges"][source] = [
            (label, new if target == old else target)
            for label, target in data["edges"][source]]

def add_edge(data, source_string, target_string, label=graphs.DEFAULT):
    source = specifiers.get_node(data, source_string)
    target = specifiers.get_node(data, target_string)
    data['edges'].setdefault(source, [])
    data['edges'][source].append((label, target))

def label_edge(data, source_string, target_string, label):
    source = specifiers.get_node(data, source_string)
    target = specifiers.get_node(data, target_string)

    if source not in data['edges']:
        raise Exception('No edges from {}'.format(source))

    edges = []
    for neighbour_label, neighbour in data['edges'][source]:
        if neighbour == target:
            edges.append((source, neighbour_label, target))

    if len(edges) > 1:
        raise Exception('Too many edges {}'.format(edges))
    elif len(edges) == 0:
        raise Exception('Too few edges')
    else:
        new_neighbours = [(l, x) for l, x in data['edges'][source] if x != target] + [(label, target)]
        data['edges'][source] = new_neighbours


@contextlib.contextmanager
def with_clidi_data(data_file):
    with with_data(data_file) as data:
        data.setdefault('tags', dict())
        data.setdefault('edges', dict())
        data.setdefault('nodes', list())
        data.setdefault('node_info', dict())
        data.setdefault('settings', dict())
        yield data


TRIGGERS_CHANGE = dict(
    show=False,
    info=False,
    node=True,
    config=False,
    nodes=False,
    edge=True,
    dump=False,
    nonode=True,
    trigger=True,
    shell=True,
    noedge=True,
    rename=True,
    tag=True,
    tags=False,
    notag=True,
    label=True,
    note=True)
