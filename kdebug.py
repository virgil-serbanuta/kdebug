#!/usr/bin/env python3

import curses
import subprocess
import sys
import threading
import time
import traceback

debug = []

class StringFinder:
  def __init__(self, bytes_to_id):
    self.__bytes_to_id = bytes_to_id
    self.__positions = []

  def processByte(self, b):
    deleted = 0
    retv = []
    for i in range(0, len(self.__positions)):
      (index, subindex) = self.__positions[i]
      (current_bytes, current_id) = self.__bytes_to_id[index]
      if b[0] == current_bytes[subindex]:
        subindex += 1
        if subindex == len(current_bytes):
          retv.append(current_id)
          deleted += 1
        else:
          self.__positions[i - deleted] = (index, subindex)
      else:
        deleted += 1
    if deleted:
      self.__positions = self.__positions[:-deleted]
    for i in range(0, len(self.__bytes_to_id)):
      (current_bytes, current_id) = self.__bytes_to_id[i]
      if current_bytes[0] == b[0]:
        if len(current_bytes) == 1:
          retv.append(current_id)
        else:
          self.__positions.append((i, 1))
    #print(self.__positions)
    return retv

  def processBytes(self, bs):
    for i in range(0, len(bs)):
      self.processByte(bs[i:i+1])

  def reset(self):
    self.__positions = []

class AtomicValue:
  def __init__(self, value):
    self.__value = value
    self.__mutex = threading.Lock()

  def set(self, value):
    self.__mutex.acquire()
    try:
      self.__value = value
    finally:
      self.__mutex.release()

  def get(self):
    self.__mutex.acquire()
    try:
      return self.__value
    finally:
      self.__mutex.release()

class EndState:
  NOTHING = 1
  STUCK = 2
  FAILED_END = 3

  def __init__(self):
    self.__message = EndState.NOTHING

  def setStuck(self):
    self.__message = EndState.STUCK

  def setFailedEnd(self):
    self.__message = EndState.FAILED_END

  def reset(self):
    self.__message = EndState.NOTHING

  def isStuck(self):
    return self.__message == EndState.STUCK

  def isFailedEnd(self):
    return self.__message == EndState.FAILED_END


class Node:
  NORMAL = 0
  PROOF_END = 1
  PROOF_END_FAILED = 2
  STUCK = 3

  def __init__(self, number):
    self.__number = number
    self.__state = Node.NORMAL

  def number(self):
    return self.__number

  def setState(self, state):
    self.__state = state

  def getKonfig(self):
    return str(self)

  def __str__(self):
    if self.__state == Node.NORMAL:
      return str(self.__number)
    if self.__state == Node.PROOF_END:
      return '(%d)' % self.__number
    if self.__state == Node.PROOF_END_FAILED:
      return 'failed_end(%d)' % self.__number
    if self.__state == Node.STUCK:
      return 'stuck(%d)' % self.__number
    assert False

class NodeTree:
  def __init__(self, root, message_thread):
    self.__nodes = [Node(root)]
    self.__children = []
    self.__all_nodes = set([root])
    self.__changeListeners = []
    self.__message_thread = message_thread

  def getId(self):
    return self.__nodes[0].number()

  def addChild(self, parent, child):
    assert parent in self.__all_nodes, ("parent=%d, child=%d, self.__all_nodes=%s" % (parent, child, self.__all_nodes))
    self.__all_nodes.add(child)
    if self.__children:
      for c in self.__children:
        if c.__containsNode(parent):
          c.addChild(parent, child)
          self.__notifyChangeListeners()
          return
      assert False, ('parent=%d child=%d' % (parent, child))
    else:
      assert parent == self.__nodes[-1].number()
      self.__nodes.append(Node(child))

  def addChildren(self, parent, children):
    assert parent in self.__all_nodes
    for child in children:
      self.__all_nodes.add(child)
    if self.__children:
      for child in self.__children:
        if child.__containsNode(parent):
          child.addChildren(parent, children)
          self.__notifyChangeListeners()
          return
      assert False
    else:
      assert parent == self.__nodes[-1].number()
      self.__children = [
        NodeTree(child, self.__message_thread) for child in children]
      self.__notifyChangeListeners()

  def setNodeState(self, number, state):
    self.__findNode(number).setState(state)
    self.__notifyChangeListeners()

  def startNode(self):
    return self.__nodes[0]

  def endNode(self):
    return self.__nodes[-1]

  def children(self):
    return self.__children

  def addChangeListener(self, listener):
    self.__changeListeners.append(listener)

  def findNode(self, node_id):
    return self.__findNode(node_id)

  def __notifyChangeListeners(self):
    for l in self.__changeListeners:
      self.__message_thread.add(l.onChange)

  def __findNode(self, number):
    assert number in self.__all_nodes, '%d %s' % (number, self.__all_nodes)
    for c in self.__children:
      if number in c.__all_nodes:
        return c.__findNode(number)
    for n in self.__nodes:
      if n.number() == number:
        return n
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

class Handler:
  STARTING = 0
  STEPPING = 1
  PROMPT_IDLE = 2

  def __init__(self, stdin, log, message_thread, life, end_state):
    self.__stdin = stdin
    self.__state = AtomicValue(Handler.STARTING)
    self.__log = log
    self.__pending_commands = []
    self.__unexpanded_nodes = []
    self.__parsers = []
    self.__nodes_seen = set([])
    self.__node_tree = NodeTree(0, message_thread)
    self.__last_config_number = -1
    self.__next_node_state = Node.NORMAL
    self.__last_command = b'step'
    self.__life = life
    self.__end_state = end_state

  def onAtPrompt(self, config_number):
    self.__log.write(b'onAtPrompt\n')
    last_command = self.__last_command.decode('ascii')

    if self.__state == Handler.STARTING:
      assert config_number == 0

    if not config_number in self.__nodes_seen:
      if config_number != self.__node_tree.getId():
        self.__node_tree.addChild(self.__last_config_number, config_number)
      self.__nodes_seen.add(config_number)
      self.__unexpanded_nodes.append(config_number)

    if not self.__pending_commands:
      self.__expandNodeIfNeeded()

    if self.__pending_commands:
      self.__parsersPrepareForStep()
      self.__sendCommand(self.__pending_commands[0])
      self.__pending_commands = self.__pending_commands[1:]
    else:
      self.__state = Handler.PROMPT_IDLE

    """
    if self.__state.get() == Handler.STARTING:
      assert config_number == 0
      self.__nodes_seen.add(config_number)
      self.__parsersPrepareForStep()  # Must be called before the step command
      self.__sendCommand(b'step\n')
      self.__state.set(Handler.STEPPING)
    else:
      if not config_number in self.__nodes_seen:
        self.__node_tree.addChild(self.__last_config_number, config_number)
        self.__nodes_seen.add(config_number)
        self.__unexpanded_nodes.append(config_number)
      if not self.__pending_commands:
        self.__expandNodeIfNeeded()
      if self.__pending_commands:
        self.__parsersPrepareForStep()
        self.__sendCommand(self.__pending_commands[0])
        self.__pending_commands = self.__pending_commands[1:]
      else:
        # self.__node_tree.print(0)
        self.__sendCommand(b'exit\n')
        self.__life.die()
    """

    self.__last_config_number = config_number
    if last_command.startswith('step'):
      self.__node_tree.setNodeState(config_number, self.__next_node_state)
    self.__next_node_state = Node.NORMAL

  def onBranches(self, steps, branches):
    # print("steps=%d branches=%s" % (steps, branches))
    self.__node_tree.addChildren(self.__last_config_number, branches)
    for c in branches:
      self.__nodes_seen.add(c)
    # self.__parsersPrepareForStep()
    self.__unexpanded_nodes += branches
    # self.__pending_commands.append(bytes('select %d\n' % branches[0], 'ascii'))
    # self.__pending_commands.append(b'step 100\n')

  def onProofEnd(self, steps):
    if self.__end_state.isStuck():
      self.__next_node_state = Node.STUCK
    elif self.__end_state.isFailedEnd():
      self.__next_node_state = Node.PROOF_END_FAILED
    else:
      self.__next_node_state = Node.PROOF_END
    # self.__parsersPrepareForStep()

  def setParsers(self, parsers):
    self.__parsers = parsers

  def die(self):
    self.__life.die()
    try:
      self.__sendCommand(b'exit\n')
    except BrokenPipeError:
      pass

  def nodeTree(self):
    return self.__node_tree

  def __parsersPrepareForStep(self):
    for p in self.__parsers:
      p.prepareForStep()

  def __expandNodeIfNeeded(self):
    if self.__unexpanded_nodes:
      self.__pending_commands.append(bytes('select %d\n' % self.__unexpanded_nodes[0], 'ascii'))
      self.__pending_commands.append(b'step\n')
      self.__unexpanded_nodes = self.__unexpanded_nodes[1:]

  def __selectConfig(self, config_number):
    self.__parsersPrepareForStep()
    self.__sendCommand(bytes('select %d\n' % config_number, 'ascii'))

  def __step(self):
    self.__parsersPrepareForStep()
    self.__sendCommand(b'step\n')

  def __sendCommand(self, command):
    self.__stdin.write(command)
    self.__stdin.flush()
    self.__log.write(command)
    self.__log.flush()
    self.__last_command = command

class Life:
  def __init__(self):
    self.__is_running = AtomicValue(True)
    self.__message_thread = None

  def setMessageThread(self, message_thread):
    self.__message_thread = message_thread

  def isRunning(self):
    return self.__is_running.get()

  def die(self):
    #  raise ""
    self.__is_running.set(False)
    self.__message_thread.die()

#-------------------------------------
#         StdErr thread
#-------------------------------------

class StdErrParser:

  STR_STUCK = 1
  STR_FAILED_END = 2

  def __init__(self, end_state, log, message_thread):
    self.__end_state = end_state
    self.__log = log
    self.__message_thread = message_thread
    self.__string_finder = StringFinder(
        [
            (b'WarnStuckClaimState', StdErrParser.STR_STUCK),
            (b'The proof has reached the final configuration, but the claimed implication is not valid.', StdErrParser.STR_FAILED_END),
        ])

  def process(self, byte):
    self.__log.write(byte)

    found = self.__string_finder.processByte(byte)
    if StdErrParser.STR_STUCK in found:
      self.__message_thread.add(self.__end_state.setStuck)
    elif StdErrParser.STR_FAILED_END in found:
      self.__message_thread.add(self.__end_state.setFailedEnd)

  def prepareForStep(self):
    self.__string_finder.reset()
    self.__message_thread.add(self.__end_state.reset)

def communicateWithStdErr(stderr, life, stdErrParser):
  try:
    while life.isRunning():
      a = stderr.read(1)
      if a == b'':
        continue
      stdErrParser.process(a)
  except Exception as e:
    debug.append(''.join(traceback.TracebackException.from_exception(e).format(chain=True)))
    raise
  finally:
    life.die()

#-------------------------------------
#         StdOut thread
#-------------------------------------

class OutputParser:
  STARTING = 0
  AT_PROMPT = 1
  STEPPING = 2

  STATE_START = 0
  STATE_NUMBER = 1
  STATE_PROMPT_after_number = 2
  STATE_SPLIT_after_steps = 3
  STATE_SPLIT_branches = 4

  STR_PROMPT_Kore_p = 1
  STR_PROMPT_Kore_pnp_gt_ = 2
  STR_SPLIT = 3
  STR_SPLIT_BRANCHES = 4
  STR_SPLIT_BRANCHES_COMMA = 5
  STR_SPLIT_BRANCHES_END = 6
  STR_SPLIT_PROOF_END = 7

  BYTES_PREFIX = b'\x00\xff\x00'

  def __init__(self, handler, log, message_thread):
    self.__state = OutputParser.STARTING
    self.__substate = OutputParser.STATE_START
    self.__number = 0
    self.__step_number = 0
    self.__branches = []
    self.__substate_after_number = OutputParser.STATE_START
    self.__log = log
    self.__handler = handler
    self.__message_thread = message_thread
    self.__string_finder = StringFinder(
        [
            (b'\nKore (', OutputParser.STR_PROMPT_Kore_p),
            (OutputParser.BYTES_PREFIX + b')> ', OutputParser.STR_PROMPT_Kore_pnp_gt_),
            (b'\nStopped after ', OutputParser.STR_SPLIT),
            (OutputParser.BYTES_PREFIX + b' step(s) due to branching on [', OutputParser.STR_SPLIT_BRANCHES),
            (OutputParser.BYTES_PREFIX + b',', OutputParser.STR_SPLIT_BRANCHES_COMMA),
            (OutputParser.BYTES_PREFIX + b']', OutputParser.STR_SPLIT_BRANCHES_END),
            (OutputParser.BYTES_PREFIX + b' step(s) due to reaching end of proof on current branch.', OutputParser.STR_SPLIT_PROOF_END)
        ])

  def process(self, byte):
    self.__log.write(byte)
    self.__log.flush()
    if self.__state == OutputParser.STARTING:
      self.__processWaitForPrompt(byte)
    elif self.__state == OutputParser.STEPPING:
      self.__processWaitForPrompt(byte)
    else:
      print("%s %d" % ([byte], self.__state))
      raise "issue"

  # TODO: Called from different thread, make it thread safe.
  def prepareForStep(self):
    self.__log.write(b'Reset\n')
    self.__state = OutputParser.STEPPING
    self.__substate = OutputParser.STATE_START
    self.__string_finder.reset()
    self.process(b'\n')

  def __processWaitForPrompt(self, byte):
    if self.__substate == OutputParser.STATE_START:
      found = self.__string_finder.processByte(byte)
      if OutputParser.STR_PROMPT_Kore_p in found:
        self.__number = 0
        self.__substate = OutputParser.STATE_NUMBER
        self.__substate_after_number = OutputParser.STATE_PROMPT_after_number
      elif OutputParser.STR_SPLIT in found:
        assert self.__state == OutputParser.STEPPING
        self.__number = 0
        self.__substate = OutputParser.STATE_NUMBER
        self.__substate_after_number = OutputParser.STATE_SPLIT_after_steps
    elif self.__substate == OutputParser.STATE_NUMBER:
      if b'0' <= byte and byte <= b'9':
        self.__number = 10 * self.__number + (byte[0] - (b'0')[0])
      else:
        self.__string_finder.processBytes(OutputParser.BYTES_PREFIX)
        self.__substate = self.__substate_after_number
        self.__processWaitForPrompt(byte)
    elif self.__substate == OutputParser.STATE_PROMPT_after_number:
      found = self.__string_finder.processByte(byte)
      if OutputParser.STR_PROMPT_Kore_pnp_gt_ in found:
        self.__log.write(b'onAtPrompt')
        self.__message_thread.add(
            self.__handler.onAtPrompt,
            self.__number
        )
        self.__substate = OutputParser.STATE_START
        self.process(b'\n')
      else:
        assert not found
    elif self.__substate == OutputParser.STATE_SPLIT_after_steps:
      if self.__number >= 0:
        self.__step_number = self.__number
        self.__number = -1
        self.__branches = []
      found = self.__string_finder.processByte(byte)
      if OutputParser.STR_SPLIT_BRANCHES in found:
        self.__number = 0
        self.__substate = OutputParser.STATE_NUMBER
        self.__substate_after_number = OutputParser.STATE_SPLIT_branches
      elif OutputParser.STR_SPLIT_PROOF_END in found:
        self.__log.write(b'onProofEnd')
        self.__message_thread.add(
            self.__handler.onProofEnd,
            self.__step_number
        )
        self.__substate = OutputParser.STATE_START
        self.process(b'\n')
      else:
        assert not found, found
    elif self.__substate == OutputParser.STATE_SPLIT_branches:
      if self.__number >= 0:
        self.__branches.append(self.__number)
        self.__number = -1
      found = self.__string_finder.processByte(byte)
      if OutputParser.STR_SPLIT_BRANCHES_COMMA in found:
        self.__number = 0
        self.__substate = OutputParser.STATE_NUMBER
        self.__substate_after_number = OutputParser.STATE_SPLIT_branches
      elif OutputParser.STR_SPLIT_BRANCHES_END in found:
        self.__log.write(b'onBranches')
        self.__message_thread.add(
            self.__handler.onBranches,
            self.__step_number,
            self.__branches
        )
        self.__substate = OutputParser.STATE_START
        self.process(b'\n')
      else:
        assert not found

def communicateWithStdOut(stdout, life, stdOutParser):
  try:
    while life.isRunning():
      a = stdout.read(1)
      if a == b'':
        continue
      stdOutParser.process(a)
  except Exception as e:
    debug.append(''.join(traceback.TracebackException.from_exception(e).format(chain=True)))
    raise
  finally:
    life.die()

#-------------------------------------
#    Communication initialization
#-------------------------------------

def communicate(process, log, end_state, handler, life, message_thread):
  stdErrParser = StdErrParser(end_state, log, message_thread)
  stdOutParser = OutputParser(handler, log, message_thread)

  handler.setParsers([stdOutParser, stdErrParser])

  threading.Thread(
      target=lambda : communicateWithStdErr(process.stderr, life, stdErrParser),
      daemon=True
    ).start()
  threading.Thread(
      target=lambda : communicateWithStdOut(process.stdout, life, stdOutParser),
      daemon=True
    ).start()

#-------------------------------------
#           UI
#-------------------------------------

class Window:
  def __init__(self, window):
    self.__offsetX = 0
    self.__offsetY = 0
    self.__currentY = 0
    self.__minX = 0
    self.__minY = 0
    self.__maxX = 0
    self.__maxY = 0
    self.__window = window
    self.__lines = []
    self.__line_change_listeners = []

  def setCoords(self, minX, minY, maxX, maxY):
    self.__minX = minX
    self.__minY = minY
    self.__maxX = maxX
    self.__maxY = maxY

    available = self.availableY()
    if self.__currentY >= available + self.__offsetY:
      self.__currentY = available + self.__offsetY - 1

    self.assertConsistent()

  def assertConsistent(self):
    assert self.__minX >= 0
    assert self.__minY >= 0
    assert self.__maxX > self.__minX
    assert self.__maxY > self.__minY
    assert self.availableY() > 0
    assert self.availableX() > 0

    assert self.__currentY >= 0
    assert (self.__currentY < len(self.__lines)) or (not self.__lines), "currentY=%d lines=%s" % (self.__currentY, self.__lines)
    assert self.__currentY >= self.__offsetY
    assert self.__currentY - self.__offsetY < self.availableY()

  def up(self):
    self.assertConsistent()
    if self.__currentY == 0:
      return
    if self.__currentY == self.__offsetY:
      self.__offsetY -= 1
    self.__currentY -= 1
    self.assertConsistent()
    self.__callLineChangeListeners()

  def down(self):
    self.assertConsistent()
    if self.__currentY == len(self.__lines) - 1 or (not self.__lines):
      return
    self.__currentY += 1
    if self.__currentY == self.__offsetY + self.__maxY:
      self.__offsetY += 1
    self.assertConsistent()
    self.__callLineChangeListeners()

  def setDrawLines(self, lines):
    self.assertConsistent()

    self.__lines = lines

    lines_len = len(lines)
    if self.__offsetY >= lines_len:
      if lines_len > 0:
        self.__offsetY = len(lines) - 1
      else:
        self.__offsetY = 0
    self.clear()
    for y in range(0, lines_len):
      self.print(0, y, lines[y])

    self.assertConsistent()

  def clear(self):
    self.__window.addch(self.__minY, self.__minX, curses.ACS_ULCORNER)
    self.__window.addch(self.__minY, self.__maxX, curses.ACS_URCORNER)
    self.__window.addch(self.__maxY, self.__minX, curses.ACS_LLCORNER)
    self.__window.addch(self.__maxY, self.__maxX, curses.ACS_LRCORNER)

    self.__window.hline(self.__minY, self.__minX + 1, curses.ACS_HLINE, self.availableX())
    self.__window.hline(self.__maxY, self.__minX + 1, curses.ACS_HLINE, self.availableX())

    self.__window.vline(self.__minY + 1, self.__minX, curses.ACS_VLINE, self.availableY())
    self.__window.vline(self.__minY + 1, self.__maxX, curses.ACS_VLINE, self.availableY())

    # This is faster than clear()
    for i in range(self.__minY + 1, self.__maxY):
      for j in range(self.__minX + 1, self.__maxX):
        self.__window.addch(i, j, ' ')

  # uses 0-based coordinates.
  def print(self, x, y, message):
    self.assertConsistent()

    if y == self.__currentY:
      attr = curses.A_REVERSE
    else:
      attr = curses.A_NORMAL

    x -= self.__offsetX
    y -= self.__offsetY

    if y < 0 or y > self.availableY() - 1:
      return
    if x + len(message) < -1 or x > self.availableX() - 1:
      return
    if x < 0:
      message = message[-x:]
      x = 0
    if x + len(message) > self.availableX():
      message = message[:self.availableX() - x]
    self.__window.addstr(y + self.__minY + 1, x + self.__minX + 1, message, attr)

  def availableX(self):
    return self.__maxX - self.__minX - 1

  def availableY(self):
    return self.__maxY - self.__minY - 1

  def addLineChangeListener(self, listener):
    self.__line_change_listeners.append(listener)

  def __callLineChangeListeners(self):
    for listener in self.__line_change_listeners:
      listener(self.__currentY)

class TreeWindow(Window):
  def __init__(self, stdscr, node_tree):
    super(TreeWindow, self).__init__(stdscr)
    self.__node_tree = node_tree
    self.__line_number_to_id = {}
    self.__node_change_listeners = []
    self.addLineChangeListener(self.__onLineChange)

  def draw(self, xMin, yMin, xMax, yMax):
    self.setCoords(xMin, yMin, xMax, yMax)
    nodes_with_ids = []
    self.__treeLines(['  '], self.__node_tree, nodes_with_ids)
    self.__line_number_to_id = {}
    for line_number in range(0, len(nodes_with_ids)):
      self.__line_number_to_id[line_number] = nodes_with_ids[line_number][0]
    lines = [line for (_, line) in nodes_with_ids]
    self.setDrawLines(lines)

  def addNodeChangeListener(self, listener):
    self.__node_change_listeners.append(listener)

  def __treeLines(self, indent, tree, output):
    display = []
    if indent:
      display = [l for l in indent[:-1]]
    display.append('+- ')
    if tree.startNode().number() == tree.endNode().number():
      display.append(str(tree.startNode()))
    else:
      display.append(str(tree.startNode()))
      display.append('-')
      display.append(str(tree.endNode()))
    output.append((tree.getId(), ''.join(display)))

    nextIndent = [l for l in indent]
    if tree.children():
      nextIndent.append('| ')
      for c in tree.children()[:-1]:
        self.__treeLines(nextIndent, c, output)
      nextIndent[-1] = '  '
      self.__treeLines(nextIndent, tree.children()[-1], output)

  def __onLineChange(self, new_line):
    node_id = self.__line_number_to_id[new_line]
    for listener in self.__node_change_listeners:
      listener(node_id)

class KonfigWindow(Window):
  def __init__(self, stdscr, node_tree):
    super(KonfigWindow, self).__init__(stdscr)
    self.__node_tree = node_tree
    self.__node_id = node_tree.getId()

  def draw(self, xMin, yMin, xMax, yMax):
    self.setCoords(xMin, yMin, xMax, yMax)
    lines = []
    self.__printKonfig(self.__node_tree.findNode(self.__node_id), lines)
    self.setDrawLines(lines)

  def setNode(self, node_id):
    self.__node_id = node_id

  def __printKonfig(self, node, output):
    output.append(node.getKonfig())

class WindowEvents:
  def __init__(self, window, display):
    self.__window = window
    self.__display = display

  def up(self):
    self.__window.up()
    self.__display.update()

  def down(self):
    self.__window.down()
    self.__display.update()

class Display:
  TREE_MIN_COLS = 20
  WINDOW_MIN_COLS = 20
  def __init__(self, stdscr, node_tree):
    self.__stdscr = stdscr
    curses.curs_set(False)
    self.__tree_window = TreeWindow(stdscr, node_tree)
    self.__tree_window_events = WindowEvents(self.__tree_window, self)
    self.__konfig_window = KonfigWindow(stdscr, node_tree)

  def currentWindow(self):
    return self.__tree_window_events

  def getTreeNodeWindow(self):
    return self.__tree_window

  def getKonfigWindow(self):
    return self.__konfig_window

  def update(self):
    assert curses.COLS > Display.TREE_MIN_COLS + Display.WINDOW_MIN_COLS
    self.__tree_window.draw(0, 0, Display.TREE_MIN_COLS, curses.LINES - 2)
    self.__konfig_window.draw(Display.TREE_MIN_COLS + 1, 0, curses.COLS - 1, curses.LINES - 2)
    self.__stdscr.addstr(curses.LINES - 1, 0, "F10-Quit")
    self.__stdscr.refresh()

#-------------------------------------
#           Process watcher
#-------------------------------------

class ProcessWatcher:
  def __init__(self, life, process):
    self.__life = life
    self.__process = process

  def run(self):
    try:
      self.__process.wait()
    except Exception as e:
      debug.append(''.join(traceback.TracebackException.from_exception(e).format(chain=True)))
      raise
    finally:
      self.__life.die()

def runProcessWatcher(life, process):
  threading.Thread(target=ProcessWatcher(life, process).run).start()

#-------------------------------------
#           COMMUNICATION
#-------------------------------------

class MessageThread:
  def __init__(self, life):
    self.__messages = []
    self.__life = life

    self.__block = threading.Event()
    self.__mutex = threading.Lock()
    threading.Thread(target=self.__run, daemon=True).start()

  def add(self, message, *args, **kwrds):
    self.__mutex.acquire()
    try:
      self.__messages.append((message, args, kwrds))
      self.__block.set()
    finally:
      self.__mutex.release()

  def die(self):
    # Assumes this is called from life.die()
    self.__block.set()

  def __run(self):
    try:
      while self.__life.isRunning():
        self.__block.wait()
        self.__block.clear()

        self.__mutex.acquire()
        try:
          messages = self.__messages
          self.__messages = []
        finally:
          self.__mutex.release()

        for (first, firstArgs, firstKwrds) in messages:
          first(*firstArgs, **firstKwrds)
    except Exception as e:
      debug.append(''.join(traceback.TracebackException.from_exception(e).format(chain=True)))
      raise
    finally:
      self.__life.die()

class TreeChangeListener:
  def __init__(self, display):
    self.__display = display

  def onChange(self):
    self.__display.update()

#-------------------------------------
#           COMMUNICATION
#-------------------------------------

class KeyboardReader:
  def __init__(self, message_thread, life, connector, window):
    self.__message_thread = message_thread
    self.__connector = connector
    self.__window = window
    self.__life = life
  
  def run(self):
    try:
      while self.__life.isRunning():
        c = self.__window.getch()
        if c == -1:
          time.sleep(0.1)
          continue
        self.__message_thread.add(self.__connector.keyEvent, c)
    except Exception as e:
      debug.append(''.join(traceback.TracebackException.from_exception(e).format(chain=True)))
      raise
    finally:
      self.__life.die()


def startKeyboardThread(message_thread, life, connector, window):
  threading.Thread(
      target=KeyboardReader(message_thread, life, connector, window).run,
      daemon=True
    ).start()

#-------------------------------------
#       Connecting everything
#-------------------------------------

class ConnectEverything:
  def __init__(self, life, windows):
    self.__life = life
    self.__windows = windows
    windows.getTreeNodeWindow().addNodeChangeListener(self.__onNodeChange)

  def keyEvent(self, c):
    if c == curses.KEY_F10:
      self.__life.die()
    elif c == curses.KEY_UP:
      self.__windows.currentWindow().up()
    elif c == curses.KEY_DOWN:
      self.__windows.currentWindow().down()

  def __onNodeChange(self, node_id):
    self.__windows.getKonfigWindow().setNode(node_id)
    self.__windows.update()

def main(argv, stdscr):
  stdscr.nodelay(True)

  live = Life()  # Live is life.

  log = open('debug.log', 'wb')

  message_thread = MessageThread(live)
  live.setMessageThread(message_thread)


  p = subprocess.Popen(
      argv,
      bufsize=0,
      stdin=subprocess.PIPE,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE)

  runProcessWatcher(live, p)

  end_state = EndState()
  handler = Handler(p.stdin, log, message_thread, live, end_state)

  d = Display(stdscr, handler.nodeTree())
  d.update()

  handler.nodeTree().addChangeListener(TreeChangeListener(d))

  connector = ConnectEverything(live, d)
  startKeyboardThread(message_thread, live, connector, stdscr)

  try:
    communicate(p, log, end_state, handler, live, message_thread)
    while live.isRunning():
      try:
        p.wait(1)
      except subprocess.TimeoutExpired:
        pass
  finally:
    p.kill()

if __name__ == "__main__":
  try:
    curses.wrapper(lambda stdscr : main(sys.argv[1:], stdscr))
  finally:
    print('***********************************')
    print('\n'.join(debug))
