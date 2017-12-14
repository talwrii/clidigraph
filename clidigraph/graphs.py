"Utilities to operate on graphs"

import functools
import itertools

DEFAULT = 'default'
IMPLICIT = 'implicit'

def merge_graphs(*graphs):
    return functools.reduce(merge_graph_pair, graphs)

def merge_graph_pair(a, b):
    result = dict(nodes=[], edges=dict())
    result['nodes'] = list(sorted(set(itertools.chain(a['nodes'], b['nodes']))))

    for source in set.union(set(a['edges']), set(b['edges'])):
        result['edges'][source] = list(set.union(
            set(map(tuple, a['edges'].get(source, list()))),
            set(map(tuple, b['edges'].get(source, list())))))

    return result

def between_graph(graph:dict, from_nodes:set, to_nodes:set) -> dict:
    # This is O(n) but n is small

    before_graphs = merge_graphs(*(before_graph(graph, n) for n in to_nodes))
    after_graphs = merge_graphs(*(after_graph(graph, n) for n in from_nodes))
    return intersect_graph(before_graphs, after_graphs)

def intersect_graph(a, b):
    nodes = set.intersection(set(a['nodes']), set(b['nodes']))
    return edge_set_to_graph(
        nodes,
        set.intersection(edge_set(a), edge_set(b)))

def edge_set(graph):
    return set((a, b, c) for a in graph['edges'] for b, c in graph['edges'][a])

def edge_set_to_graph(nodes, sett):
    all_nodes = set(itertools.chain.from_iterable((a, b) for (a, _, b) in sett)) | set(nodes)
    edge_dict = dict()
    for a, b, c in sett:
        edge_dict.setdefault(a, list())
        edge_dict[a].append((b, c))
    return dict(edges=edge_dict, nodes=all_nodes)

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

def contract_graph(graph, kept_nodes):
    # ignore labels for the moment
    result = dict(edges={}, nodes=set())

    kept_nodes = kept_nodes & set(graph["nodes"])

    for node in kept_nodes:
        result['nodes'].add(node)
        pseudo_neighbours = set([node])

        for label, neighbour in graph['edges'].get(node, []):
            if neighbour in kept_nodes:
                result['edges'].setdefault(node, [])
                # Maintain labels for not implied edges
                result['edges'][node].append((label, neighbour))

        visited = set()
        while pseudo_neighbours - visited:
            border = set()
            for base in pseudo_neighbours - visited:
                for _, target in graph['edges'].get(base, []):
                    if target in kept_nodes:
                        result['edges'].setdefault(node, [])
                        if target not in [t for _, t in result['edges'].get(node, [])]:
                            result['edges'][node].append((IMPLICIT, target))
                    else:
                        border.add(target)
            visited |= pseudo_neighbours
            pseudo_neighbours |= border
    return result

def induce_graph(graph, nodes):
    result = dict(edges={}, nodes=set(nodes))

    for n in nodes:
        result['edges'][n] = [
            (l, target)
            for l, target in graph["edges"].get(n, []) if target in nodes]

    return result

def remove_label(graph, label):
    result = dict(edges={}, nodes=set(graph["nodes"]))
    for node in graph['edges']:
        result["edges"][node] = [(l, x) for l, x in  graph['edges'][node] if l != label]

    return result

