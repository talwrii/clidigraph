# clidigraph

**Experimental code liable to dramatic change. Untested. Use with caution**

A minimal command-line program to store and query digraphs. This is not optimised for performance and is designed to be easy-to-use from the shell. Outputs to [graphviz dot](http://graphviz.org/).


# Query language

```
# Add an edge
clidigraph node one two three

clidigraph edge one two

# Dump the graph to graphviz
clidigraph show

# Draw a picture of the graph
clidigraph show | dot -Tpng > /tmp/picture.png; sxiv /tmp/picture.png

# Show the ancestors of thing
clidigraph show --nodes 'after:thing'

# Show which endpoints are connected to which starting points by paths
clidigraph show --contract tag:start,tag:end
```

# Alternatives and prior work

There are many graph databases, some of which provide powerful querying mechanisms. After a brief review, the author found most of these too heavy-weight (high set-up costs). [This post](https://news.ycombinator.com/item?id=10991751) suggested [tinkergraph](http://tinkerpop.apache.org/) and [cayley](https://github.com/cayleygraph/cayley) as lightweight, single process solutions.

[neo4j](https://neo4j.com/) is a widely used graph database.

Many semantic web standards like [rdf](https://www.w3.org/2001/sw/wiki/RDF) and [SPARQL](https://www.w3.org/TR/rdf-sparql-query/) deal with similar types of activity: creating labelled graphs, querying them and manipulating them.
