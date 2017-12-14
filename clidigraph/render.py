import graphviz
import logging

LOGGER = logging.getLogger('render')


from . import graphs

HIGHLIGHT_COLOR = 'yellow'
def render_graph(data, graph, highlighted_nodes, grouped_nodes):
    rendered_nodes = set()
    graphviz_graph = graphviz.Digraph()

    def render_node(name):
        node_info = data['node_info'].get(name, dict())

        tags = node_info.get('tags')

        tag = sorted(tags)[0] if tags else None
        kwargs = dict()

        if tag:
            kwargs["tooltip"] = 'tag:' + tag
        else:
            kwargs["tooltip"] = ''

        if name in (set.union(*grouped_nodes.values()) if grouped_nodes else set()):
            for group_name, nodes in grouped_nodes.items():
                if name in nodes:
                    kwargs["fillcolor"] = get_tag_color(group_name, grouped_nodes, data)
                    kwargs["style"] = 'filled'
                    break
            else:
                raise Exception('unreachable')
        elif name in highlighted_nodes:
            kwargs["fillcolor"] = HIGHLIGHT_COLOR
            kwargs["style"] = 'filled'
        elif tag:
            kwargs["fillcolor"] = get_tag_color(tag, grouped_nodes, data)
            kwargs["style"] = 'filled'

        if name in highlighted_nodes:
            kwargs["tooltip"] += '\nhighlighted\n'

        if name in (set.union(*grouped_nodes.values()) if grouped_nodes else set()):
            for group_name, nodes in grouped_nodes.items():
                if name in nodes:
                    kwargs["tooltip"] += '\ngroup:' + group_name

        if node_info.get('note', None):
            kwargs['peripheries'] = '2'

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

            if label == graphs.DEFAULT:
                graphviz_graph.edge(source, target)
            elif label == graphs.IMPLICIT:
                graphviz_graph.edge(source, target, style='dashed')
            else:
                graphviz_graph.edge(source, target, label=label)

    return graphviz_graph.source

def get_tag_color(tag, groups, data):
    groups = set(groups)
    tags = sorted(data['tags'])

    if groups & set(tags):
        raise ValueError(groups & set(tags))
    # Colors can be found here:
    # http://graphviz.org/doc/info/colors.html
    colors = ('pink', 'lightgreen', 'lightblue', 'bisque', 'orange', 'green')

    if HIGHLIGHT_COLOR in colors:
        raise ValueError((HIGHLIGHT_COLOR, colors))

    required_colors = set(tags) | set(groups)
    if len(required_colors) > len(colors):
        raise Exception('Too many colors {}'.format(required_colors))

    return dict(zip(sorted(tags) + sorted(groups), colors))[tag]
