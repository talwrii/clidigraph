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


class SpecifierMatch(object):
    def __init__(self, data, graph):
        self.data = data
        self.graph = graph

    def get_neighbour(self, rest):
        depth, root_specifier = rest.split(':', 1)
        root_nodes = get_matching_nodes(self.data, self.graph, root_specifier)
        return set(graphs.merge_graphs(*[
            neighbour_graph(self.graph, root, depth)
            for root in root_nodes])["nodes"]) - set(root_nodes)

    def get_not(self, rest):
        return set(self.graph["nodes"]) - get_matching_nodes(self.data, self.graph, rest)

    def get_strict_before(self, rest):
        bases = get_matching_nodes(self.data, self.graph, rest)
        nodes = set()
        for b in bases:
            nodes |= (set(graphs.before_graph(self.graph, b)['nodes']) - set([b]))
        return nodes

    def get_strict_after(self, rest):
        bases = get_matching_nodes(self.data, self.graph, rest)
        nodes = set()
        for b in bases:
            nodes |= (graphs.after_graph(self.graph, b)['nodes']  - set([b]))
        return nodes

    def get_between(self, rest):
        from_spec, to_spec = rest.split('::')
        to_nodes = get_matching_nodes(self.data, self.graph, to_spec)
        from_nodes = get_matching_nodes(self.data, self.graph, from_spec)
        return graphs.between_graph(self.graph, from_nodes, to_nodes)["nodes"]

    def get_after(self, rest):
        bases = get_matching_nodes(self.data, self.graph, rest)
        return graphs.merge_graphs(*(graphs.after_graph(self.graph, b) for b in bases))["nodes"]

    def get_before(self, rest):
        bases = get_matching_nodes(self.data, self.graph, rest)
        before_graph = graphs.merge_graphs(*(graphs.before_graph(self.graph, b) for b in bases))
        return set(before_graph['nodes'])

    def get_root(self, rest):
        del rest
        return get_roots(self.graph)

    def get_tag(self, rest):
        return get_nodes(self.data, self.graph, tag=rest)

    @classmethod
    def specifiers(cls):
        return [method[len('get_'):].replace('_', '-') for method in dir(cls) if method.startswith('get_')]


def get_matching_nodes(data, graph, specifier):
    if specifier.startswith('raw:'):
        single, = [n for n in graph["nodes"] if n == specifier.split(':')[1]]
        return set([single])

    if ',' in specifier:
        return set.union(*map(set, (get_matching_nodes(data, graph, s) for s in specifier.split(','))))
    result = set()

    if ':' in specifier:
        head, rest = specifier.split(':', 1)
        spec = SpecifierMatch(data, graph)
        return getattr(spec, 'get_' + head.replace('-', '_'))(rest)
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

    for name, info in data['node_info'].items():
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
