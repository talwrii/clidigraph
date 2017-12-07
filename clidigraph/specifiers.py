"Selecting nodes in graphs"


from . import graphs
from . import datastore


def get_matching_nodes(data, specifier):
    result = set()

    if specifier.startswith('neighbour:'):
        _, rest = specifier.split(':', 1)
        root_specifier, depth = rest.rsplit(':', 1)
        root_nodes = get_matching_nodes(data, root_specifier)
        return set(graphs.merge_graphs(*[
            neighbour_graph(data, root, depth)
            for root in root_nodes])["nodes"]) - set(root_nodes)
    elif specifier.startswith('root:'):
        result.update(get_roots(data))
    elif specifier.startswith('tag:'):
        _, tag = specifier.split(':', 1)
        result.update(get_nodes(data, tag=tag))
    else:
        result.add(specifier)
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

def get_nodes(data, tag=None):
    datastore.get_tag(data, tag)
    if tag is None:
        raise ValueError(tag)

    for name, info in data['node_info'].items():
        if tag in info.get('tags', list()):
            yield name

def get_roots(data):
    nodes = set(data["nodes"])
    for source in data["edges"]:
        for _, target in data['edges'][source]:
            if target in nodes:
                nodes.remove(target)
    return nodes
