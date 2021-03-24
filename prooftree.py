import messages

class Node:
  NORMAL = 0
  PROOF_END = 1
  PROOF_END_FAILED = 2
  STUCK = 3
  ERROR = 4

  def __init__(self, number, ui_data):
    self.__number = number
    self.__state = Node.NORMAL
    self.__konfig = []
    self.__ui_data = ui_data
    self.__change_listeners = messages.Listeners()
    self.__ui_data.getChangeListeners().add(self.__change_listeners.notify)

  def getChangeListeners(self):
    return self.__change_listeners

  def number(self):
    return self.__number

  def getUIData(self):
    return self.__ui_data

  def setState(self, state):
    self.__state = state
    self.__change_listeners.notify()

  def getKonfig(self):
    if self.hasKonfig():
      return self.__konfig
    else:
      return ['Not loaded yet.']

  def hasKonfig(self):
    return bool(self.__konfig)

  def setKonfig(self, konfig):
    self.__konfig = konfig
    self.__change_listeners.notify()

  def __str__(self):
    if self.__state == Node.NORMAL:
      return str(self.__number)
    if self.__state == Node.PROOF_END:
      return '(%d)' % self.__number
    if self.__state == Node.PROOF_END_FAILED:
      return 'failed_end(%d)' % self.__number
    if self.__state == Node.ERROR:
      return 'error(%d)' % self.__number
    if self.__state == Node.STUCK:
      return 'stuck(%d)' % self.__number
    assert False

class NodeTree:
  def __init__(self, root, message_thread, ui_data_constructor):
    self.__nodes = [Node(root, ui_data_constructor())]
    self.__children = []
    self.__all_nodes = set([root])
    self.__change_listeners = messages.Listeners()
    self.__message_thread = message_thread
    self.__ui_data_constructor = ui_data_constructor

  def getChangeListeners(self):
    return self.__change_listeners

  def getId(self):
    return self.__nodes[0].number()

  def addChild(self, parent, child):
    assert parent in self.__all_nodes, ("parent=%d, child=%d, self.__all_nodes=%s" % (parent, child, self.__all_nodes))
    self.__all_nodes.add(child)
    if self.__children:
      for c in self.__children:
        if c.__containsNode(parent):
          c.addChild(parent, child)
          return
      assert False, ('parent=%d child=%d' % (parent, child))
    else:
      assert parent == self.__nodes[-1].number()
      new_node = Node(child, self.__ui_data_constructor())
      self.__nodes.append(new_node)
      new_node.getChangeListeners().add(self.__change_listeners.notify)
      self.__change_listeners.notify()

  def addChildren(self, parent, children):
    assert parent in self.__all_nodes
    for child in children:
      self.__all_nodes.add(child)
    if self.__children:
      for child in self.__children:
        if child.__containsNode(parent):
          child.addChildren(parent, children)
          self.__change_listeners.notify()
          return
      assert False
    else:
      assert parent == self.__nodes[-1].number()
      self.__children = []
      for child in children:
        new_tree = NodeTree(child, self.__message_thread, self.__ui_data_constructor)
        new_tree.getChangeListeners().add(self.__change_listeners.notify)
        self.__children.append(new_tree)
      self.__change_listeners.notify()

  def setNodeState(self, number, state):
    self.__findNode(number).setState(state)

  def startNode(self):
    return self.__nodes[0]

  def endNode(self):
    return self.__nodes[-1]

  def children(self):
    return self.__children

  def nodes(self):
    return self.__nodes

  # TODO: Remove
  def addChangeListener(self, listener):
    self.__changeListeners.append(listener)

  def __notifyChangeListeners(self):
    for l in self.__changeListeners:
      self.__message_thread.add(l.onChange)

  def findNode(self, node_id):
    return self.__findNode(node_id)

  def findTree(self, node_id):
    return self.__findTree(node_id)

  def __findNode(self, number):
    assert number in self.__all_nodes, '%d %s' % (number, self.__all_nodes)
    for c in self.__children:
      if number in c.__all_nodes:
        return c.__findNode(number)
    for n in self.__nodes:
      if n.number() == number:
        return n
    assert False

  def __findTree(self, number):
    assert number in self.__all_nodes, '%d %s' % (number, self.__all_nodes)
    if number == self.getId():
      return self
    for c in self.__children:
      if number in c.__all_nodes:
        return c.__findTree(number)
    assert False

  def __containsNode(self, number):
    return number in self.__all_nodes

  def print(self, indent):
    if len(self.__nodes) > 1:
      print(
          '%s%s -> %s -> %s' %
          ( '  ' * indent,
            self.__nodes[0],
            self.__nodes[-1],
            [str(c.__nodes[0]) for c in self.__children]
          ))
    else:
      print(
          '%s%s -> %s' %
          ( '  ' * indent,
            self.__nodes[0],
            [str(c.__nodes[0]) for c in self.__children]
          ))
    for c in self.__children:
      c.print(indent + 1)

