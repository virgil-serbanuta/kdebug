#!/usr/bin/env python3

import sys

import messages
import svg

class GraphParser(object):
  BETWEEN_THINGS = 0
  ADDING_THING = 1
  ADDING_NODE = 2
  ADDING_EDGE = 3
  AFTER_ADD = 4

  def __init__(self):
    super().__init__()
    self.__nodes = set()
    self.__edges = {}
    self.__state = GraphParser.BETWEEN_THINGS
    self.__first = None
    self.__second = None

  def __str__(self) -> str:
    return str(self.__edges)

  def startElement(self):
    assert self.__state == GraphParser.BETWEEN_THINGS
    self.__state = GraphParser.ADDING_THING

  def addTitle(self, title):
    assert self.__state == GraphParser.ADDING_THING
    pos = title.find('&')
    if pos < 0:
      self.__state = GraphParser.ADDING_NODE
      self.__nodes.add(int(title))
    else:
      self.__state = GraphParser.ADDING_EDGE
      first = int(title[:pos])
      pos = title.rfind(';')
      assert pos > 0
      second = int(title[pos + 1:])
      assert first in self.__nodes, [first, self.__nodes]
      assert second in self.__nodes, [second, self.__nodes]
      self.__first = first
      self.__second = second

  def addText(self, text):
    if self.__state == GraphParser.ADDING_EDGE:
      if not self.__first in self.__edges:
        self.__edges[self.__first] = {}
      self.__edges[self.__first][self.__second] = text
    elif self.__state == GraphParser.ADDING_NODE:
      pass
    else:
      raise Exception("Invalid state: %d" % self.__state)
    self.__state = GraphParser.AFTER_ADD

  def endElement(self):
    assert self.__state == GraphParser.AFTER_ADD
    self.__state = GraphParser.BETWEEN_THINGS

  def edges(self):
    return self.__edges
 
def parseSvg(content):
  START = 0
  IN_GRAPH = 1
  IN_GRAPH_G = 2
  IN_GRAPH_G_TITLE = 3
  IN_GRAPH_G_TEXT = 4
  
  state = START
  graph = GraphParser()

  for c in content:
    if state == START:
      if isinstance(c, svg.TagOpen):
        if c.name() == 'g':
          state = IN_GRAPH
    elif state == IN_GRAPH:
      if isinstance(c, svg.TagOpen):
        if c.name() == 'g':
          state = IN_GRAPH_G
          graph.startElement()
      elif isinstance(c, svg.TagClose):
        if c.name() == 'g':
          state = START
    elif state == IN_GRAPH_G:
      if isinstance(c, svg.TagOpen):
        if c.name() == 'title':
          state = IN_GRAPH_G_TITLE
        elif c.name() == 'text':
          state = IN_GRAPH_G_TEXT
      elif isinstance(c, svg.TagClose):
        if c.name() == 'g':
          graph.endElement()
          state = IN_GRAPH
    elif state == IN_GRAPH_G_TITLE:
      if isinstance(c, str):
        graph.addTitle(c)
      elif isinstance(c, svg.TagClose):
        if c.name() == 'title':
          state = IN_GRAPH_G
    elif state == IN_GRAPH_G_TEXT:
      if isinstance(c, str):
        graph.addText(c)
      elif isinstance(c, svg.TagClose):
        if c.name() == 'text':
          state = IN_GRAPH_G
    else:
      raise Exception("Invalid state: %d" % state)
  return graph.edges()

def parseGraph(file_name):
  with open(file_name, 'r') as f:
    contents = f.read()
  ast = svg.parseTags(contents)
  return parseSvg(ast)

class UIGraph(object):
  def __init__(self):
    self.__change_listeners = messages.Listeners()
    self.__graph = {}
    self.__computeIncomingEdges()

  def getChangeListeners(self):
    return self.__change_listeners

  def setGraph(self, graph):
    self.__graph = graph
    self.__computeIncomingEdges()
    self.__change_listeners.notify()

  def graph(self):
    return self.__graph

  def incomingEdge(self, node_id):
    if node_id in self.__incoming_edges:
      return self.__incoming_edges[node_id]
    return None

  def __computeIncomingEdges(self):
    self.__incoming_edges = {}
    for (_, d) in self.__graph.items():
      for (node, edge) in d.items():
        assert not node in self.__incoming_edges
        self.__incoming_edges[node] = edge

def main(argv):
  if len(argv) != 1:
    print('Usage:\n    svg.py input-file')
    sys.exit(1)
  graph = parseGraph(argv[0])
  print(graph)

if __name__ == '__main__':
    main(sys.argv[1:])
