"Selecting nodes in graphs"

from __future__ import absolute_import, division, print_function, unicode_literals

import re

from . import graphs, datastore


def get_node(data, source):
    if source.startswith('raw:'):
        result, = [n for n in data['nodes'] if n == source.split(':', 1)[1]]
    else:
        result, = [n for n in data['nodes'] if re.search(source, n)]
    return result

def get_matching_edges(data, graph, specifier):
    head, rest = specifier.split(':', 1)
    result = []
    if head == 'to':
        nodes = get_matching_nodes(data, graph, rest)
        backward = graphs.reverse_graph(data)
        for node in nodes:
            for label, target in backward['edges'][node]:
                result.append((target, label, node))
    else:
        raise NotImplementedError(head)
    return result


def get_matching_nodes(data, graph, specifier):
    if specifier.startswith('raw:'):
        single, = [n for n in graph["nodes"] if n == specifier.split(':')[1]]
        return set([single])

    if ',' in specifier:
        return set.union(*(get_matching_nodes(data, graph, s) for s in specifier.split(',')))
    result = set()

    if ':' in specifier:
        head, rest = specifier.split(':', 1)
        if specifier.startswith('neighbour:'):
            _, rest = specifier.split(':', 1)
            depth, root_specifier = rest.split(':', 1)
            root_nodes = get_matching_nodes(data, graph, root_specifier)
            return set(graphs.merge_graphs(*[
                neighbour_graph(graph, root, depth)
                for root in root_nodes])["nodes"]) - set(root_nodes)
        elif head == 'not':
            return set(graph["nodes"]) - get_matching_nodes(data, graph, rest)
        elif head == 'strict-before':
            bases = get_matching_nodes(data, graph, rest)
            nodes = set()
            for b in bases:
                nodes |= (set(graphs.before_graph(graph, b)['nodes']) - set([b]))
            return nodes
        elif head == 'strict-after':
            bases = get_matching_nodes(data, graph, rest)
            nodes = set()
            for b in bases:
                nodes |= (graphs.after_graph(graph, b)['nodes']  - set([b]))
            return nodes
        elif head == 'between':
            from_spec, to_spec = rest.split('::')
            to_nodes = get_matching_nodes(data, graph, to_spec)
            from_nodes = get_matching_nodes(data, graph, from_spec)
            return graphs.between_graph(graph, from_nodes, to_nodes)["nodes"]
        elif head == 'after':
            bases = get_matching_nodes(data, graph, rest)
            return graphs.merge_graphs(*(graphs.after_graph(graph, b) for b in bases))["nodes"]
        elif head == 'before':
            bases = get_matching_nodes(data, graph, rest)
            before_graph = graphs.merge_graphs(*(graphs.before_graph(graph, b) for b in bases))
            return set(before_graph['nodes'])
        elif specifier.startswith('root:'):
            result.update(get_roots(graph))
        elif specifier.startswith('tag:'):
            _, tag = specifier.split(':', 1)
            result.update(get_nodes(data, graph, tag=tag))
        else:
            raise ValueError(specifier)
    else:
        result |= set([node for node in graph['nodes'] if re.search(specifier, node)])
    return result

def neighbour_graph(graph, root, depth):
    if depth.startswith('+'):
        down_depth = int(depth[1:])
        up_depth = 0
    elif depth.startswith('-'):
        up_depth = int(depth[1:])
        down_depth = 0
    else:
        up_depth = down_depth = int(depth)

    return graphs.merge_graphs(
        graphs.before_graph(graph, root, depth=up_depth),
        graphs.after_graph(graph, root, depth=down_depth),
        )

def get_nodes(data, graph, tag=None):
    datastore.get_tag(data, tag=tag)
    if tag is None:
        raise ValueError(tag)

    for name, info in node_info.items():
        if tag in info.get('tags', list()):
            if name in graph['nodes']:
                yield name

def get_roots(data):
    nodes = set(data["nodes"])
    for source in data["edges"]:
        for _, target in data['edges'][source]:
            if target in nodes:
                nodes.remove(target)
    return nodes
