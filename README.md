# clidigraph

A minimal command-line program to store and query digraphs. Inefficient, limited in use cases and easy use to use from the shell.


# Usage

```
# Add an edge
clidigraph add one two

# Dump the graph to graphviz
clidigraph show 

```

# Alternatives and prior work

There are many graph databases, some of which provide powerful querying mechanisms. After a brief review, the author found most of these too heavy weight (high set-up costs). [This post](https://news.ycombinator.com/item?id=10991751) suggested [tinkergraph](http://tinkerpop.apache.org/) and [cayley](https://github.com/cayleygraph/cayley) as lightweight, single process solutions.

[neo4j](https://neo4j.com/) is a widely used graph database.

Many semantic web standards like [rdf](https://www.w3.org/2001/sw/wiki/RDF) and [SPARQL](https://www.w3.org/TR/rdf-sparql-query/) deal with similar types of activity.


