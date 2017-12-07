"Utilities to operate on graphs"

import functools
import itertools

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
