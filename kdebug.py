#!/usr/bin/env python3

import curses
import curses.ascii
import subprocess
import sys
import threading
import time

import indent
import konfig
import errors
import messages

debug = []
UI_THREAD = None

def assertOnUIThread():
  assert threading.current_thread().ident == UI_THREAD.ident

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
  ERROR = 4

  def __init__(self):
    self.__message = EndState.NOTHING

  def setStuck(self):
    self.__message = EndState.STUCK

  def setFailedEnd(self):
    self.__message = EndState.FAILED_END

  def setError(self):
    self.__message = EndState.ERROR

  def reset(self):
    self.__message = EndState.NOTHING

  def isStuck(self):
    return self.__message == EndState.STUCK

  def isFailedEnd(self):
    return self.__message == EndState.FAILED_END

  def isError(self):
    return self.__message == EndState.ERROR

class Node:
  NORMAL = 0
  PROOF_END = 1
  PROOF_END_FAILED = 2
  STUCK = 3
  ERROR = 4

  def __init__(self, number):
    self.__number = number
    self.__state = Node.NORMAL
    self.__konfig = []

  def number(self):
    return self.__number

  def setState(self, state):
    self.__state = state

  def getKonfig(self):
    if self.hasKonfig():
      return self.__konfig
    else:
      return ['Not loaded yet.']

  def hasKonfig(self):
    return bool(self.__konfig)

  def setKonfig(self, konfig):
    self.__konfig = konfig

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
      self.__notifyChangeListeners()

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

  def nodes(self):
    return self.__nodes

  def addChangeListener(self, listener):
    self.__changeListeners.append(listener)

  def findNode(self, node_id):
    return self.__findNode(node_id)

  def findTree(self, node_id):
    return self.__findTree(node_id)

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
    self.__unknown_konfigs = []
    self.__parsers = []
    self.__nodes_seen = set([])
    self.__node_tree = NodeTree(0, message_thread)
    self.__last_config_number = -1
    self.__next_node_state = Node.NORMAL
    self.__life = life
    self.__end_state = end_state

  def onAtPrompt(self, config_number):
    self.__log.write(b'onAtPrompt\n')

    if self.__state == Handler.STARTING:
      assert config_number == 0

    if not config_number in self.__nodes_seen:
      if config_number != self.__node_tree.getId():
        self.__node_tree.addChild(self.__last_config_number, config_number)
      self.__nodes_seen.add(config_number)
      self.__unexpanded_nodes.append(config_number)

    if not self.__pending_commands:
      self.__getKonfigIfNeeded()

    if not self.__pending_commands:
      self.__expandNodeIfNeeded()

    # TODO: remove
    if config_number == 0 and not self.__node_tree.findNode(config_number).hasKonfig():
      self.__unknown_konfigs.append(0)

    if self.__pending_commands:
      self.__pending_commands[0]()
      self.__pending_commands = self.__pending_commands[1:]
    else:
      self.__state = Handler.PROMPT_IDLE

    self.__last_config_number = config_number
    if self.__next_node_state != Node.NORMAL:
      self.__node_tree.setNodeState(config_number, self.__next_node_state)
      self.__next_node_state = Node.NORMAL

  def onBranches(self, steps, branches):
    self.__node_tree.addChildren(self.__last_config_number, branches)
    for c in branches:
      self.__nodes_seen.add(c)
    self.__unexpanded_nodes += branches
    self.__unknown_konfigs.append(self.__last_config_number)
    self.__unknown_konfigs += branches

  def onProofEnd(self, steps):
    if self.__end_state.isStuck():
      self.__next_node_state = Node.STUCK
    elif self.__end_state.isFailedEnd():
      self.__next_node_state = Node.PROOF_END_FAILED
    elif self.__end_state.isError():
      self.__next_node_state = Node.ERROR
    else:
      self.__next_node_state = Node.PROOF_END

  def onKonfig(self, node_id, konfig_lines):
    self.__node_tree.findNode(node_id).setKonfig(konfig_lines)

  def setParsers(self, parsers):
    self.__parsers = parsers

  def die(self):
    self.__life.die()
    try:
      self.__sendCommand(b'exit\n')
    except BrokenPipeError:
      pass

  def requestKonfig(self, node_id):
    self.__unknown_konfigs.append(node_id)
    self.__restartIfWaitingAtPrompt()

  def nodeTree(self):
    return self.__node_tree

  def __restartIfWaitingAtPrompt(self):
    if self.__state == Handler.PROMPT_IDLE:
      self.onAtPrompt(self.__last_config_number)

  def __parsersPrepareForStep(self):
    for p in self.__parsers:
      p.prepareForStep()

  def __parsersPrepareForKonfig(self):
    for p in self.__parsers:
      p.prepareForKonfig()

  def __getKonfigIfNeeded(self):
    while self.__unknown_konfigs:
      node_id = self.__unknown_konfigs[0]
      self.__unknown_konfigs = self.__unknown_konfigs[1:]
      if self.__node_tree.findNode(node_id).hasKonfig():
        continue

      self.__pending_commands.append(lambda: self.__selectConfig(node_id))
      self.__pending_commands.append(self.__konfig)
      return True
    return False

  def __expandNodeIfNeeded(self):
    if self.__unexpanded_nodes:
      node_id = self.__unexpanded_nodes[0]
      self.__unexpanded_nodes = self.__unexpanded_nodes[1:]

      self.__pending_commands.append(lambda: self.__selectConfig(node_id))
      self.__pending_commands.append(self.__step)

      return True
    return False

  def __selectConfig(self, config_number):
    self.__parsersPrepareForStep()
    self.__sendCommand(bytes('select %d\n' % config_number, 'ascii'))

  def __step(self):
    self.__parsersPrepareForStep()
    self.__sendCommand(b'step\n')

  def __konfig(self):
    self.__parsersPrepareForKonfig()
    self.__sendCommand(b'konfig\n')

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
  STR_ERROR = 3

  def __init__(self, end_state, log, message_thread):
    self.__end_state = end_state
    self.__log = log
    self.__message_thread = message_thread
    self.__string_finder = StringFinder(
        [
            (b'WarnStuckClaimState', StdErrParser.STR_STUCK),
            (b'ErrorException', StdErrParser.STR_ERROR),
            (b'The proof has reached the final configuration, but the claimed implication is not valid.', StdErrParser.STR_FAILED_END),
        ])

  def process(self, byte):
    self.__log.write(byte)

    found = self.__string_finder.processByte(byte)
    if StdErrParser.STR_STUCK in found:
      self.__message_thread.add(self.__end_state.setStuck)
    elif StdErrParser.STR_FAILED_END in found:
      self.__message_thread.add(self.__end_state.setFailedEnd)
    elif StdErrParser.STR_ERROR in found:
      self.__message_thread.add(self.__end_state.setError)

  def prepareForStep(self):
    self.__string_finder.reset()
    self.__message_thread.add(self.__end_state.reset)

  def prepareForKonfig(self):
    self.__string_finder.reset()
    self.__message_thread.add(self.__end_state.reset)

def communicateWithStdErr(stderr, life, stdErrParser):
  while life.isRunning():
    a = stderr.read(1)
    if a == b'':
      continue
    stdErrParser.process(a)

#-------------------------------------
#         StdOut thread
#-------------------------------------

class OutputParser:
  STARTING = 0
  AT_PROMPT = 1
  STEPPING = 2
  KONFIG = 3

  STATE_START = 0
  STATE_NUMBER = 1
  STATE_PROMPT_after_number = 2
  STATE_SPLIT_after_steps = 3
  STATE_SPLIT_branches = 4
  STATE_CONFIG_START_after_number = 5
  STATE_IN_CONFIG = 6

  STR_PROMPT_Kore_p = 1
  STR_PROMPT_Kore_pnp_gt_ = 2
  STR_SPLIT = 3
  STR_SPLIT_BRANCHES = 4
  STR_SPLIT_BRANCHES_COMMA = 5
  STR_SPLIT_BRANCHES_END = 6
  STR_SPLIT_PROOF_END = 7
  STR_CONFIG_START_before_number = 8
  STR_CONFIG_START_after_number = 9

  BYTES_PREFIX = b'\x00\xff\x00'

  def __init__(self, handler, log, message_thread):
    self.__state = OutputParser.STARTING
    self.__substate = OutputParser.STATE_START
    self.__number = 0
    self.__step_number = 0
    self.__konfig_number = 0
    self.__branches = []
    self.__konfig_line = []
    self.__konfig_lines = []
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
    self.__konfig_string_finder = StringFinder(
        [
            (b'\nKore (', OutputParser.STR_PROMPT_Kore_p),
            (OutputParser.BYTES_PREFIX + b')> ', OutputParser.STR_PROMPT_Kore_pnp_gt_),
            (b'\nConfig at node ', OutputParser.STR_CONFIG_START_before_number),
            (OutputParser.BYTES_PREFIX + b' is:', OutputParser.STR_CONFIG_START_after_number)
        ])

  def process(self, byte, log=True):
    if log:
      self.__log.write(byte)
      self.__log.flush()
    if self.__state == OutputParser.STARTING:
      self.__processWaitForPromptStepping(byte)
    elif self.__state == OutputParser.STEPPING:
      self.__processWaitForPromptStepping(byte)
    elif self.__state == OutputParser.KONFIG:
      self.__processWaitForPromptKonfig(byte)
    else:
      assert False, ("%s %d" % ([byte], self.__state))

  # TODO: Called from different thread, make it thread safe.
  def prepareForStep(self):
    self.__log.write(b'Reset\n')
    self.__state = OutputParser.STEPPING
    self.__substate = OutputParser.STATE_START
    self.__string_finder.reset()
    self.process(b'\n')

  # TODO: Called from different thread, make it thread safe.
  def prepareForKonfig(self):
    self.__log.write(b'Reset Konfig\n')
    self.__state = OutputParser.KONFIG
    self.__substate = OutputParser.STATE_START
    self.__string_finder.reset()
    self.process(b'\n')

  def __processPromptState(self, found):
    if self.__substate == OutputParser.STATE_START or self.__substate == OutputParser.STATE_IN_CONFIG:
      if OutputParser.STR_PROMPT_Kore_p in found:
        self.__number = 0
        self.__substate = OutputParser.STATE_NUMBER
        self.__substate_after_number = OutputParser.STATE_PROMPT_after_number
        return True
    if self.__substate == OutputParser.STATE_PROMPT_after_number:
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
      return True
    return False

  def __processNumber(self, byte, string_finder):
    if self.__substate == OutputParser.STATE_NUMBER:
      if b'0' <= byte and byte <= b'9':
        self.__number = 10 * self.__number + (byte[0] - (b'0')[0])
      else:
        string_finder.processBytes(OutputParser.BYTES_PREFIX)
        self.__substate = self.__substate_after_number
        self.process(byte, False)
      return True
    return False

  def __processWaitForPromptKonfig(self, byte):
    found = self.__konfig_string_finder.processByte(byte)

    if self.__processPromptState(found):
      if self.__substate == OutputParser.STATE_START:
        assert self.__konfig_lines
        normalized = konfig.normalize(self.__konfig_lines)
        self.__log.write(bytes('onKonfig(%d, [%s, ...])' % (self.__konfig_number, normalized), 'ascii'))
        self.__message_thread.add(
            self.__handler.onKonfig,
            self.__konfig_number,
            normalized
        )
      return
    if self.__processNumber(byte, self.__konfig_string_finder):
      return

    if self.__substate == OutputParser.STATE_START:
      if OutputParser.STR_CONFIG_START_before_number in found:
        assert self.__state == OutputParser.KONFIG
        self.__number = 0
        self.__substate = OutputParser.STATE_NUMBER
        self.__substate_after_number = OutputParser.STATE_CONFIG_START_after_number
      return
    if self.__substate == OutputParser.STATE_CONFIG_START_after_number:
      if OutputParser.STR_CONFIG_START_after_number in found:
        assert self.__state == OutputParser.KONFIG
        self.__konfig_number = self.__number
        self.__substate = OutputParser.STATE_IN_CONFIG
        self.__konfig_line = []
        self.__konfig_lines = []
    elif self.__substate == OutputParser.STATE_IN_CONFIG: 
      if byte == b'\n':
        if self.__konfig_line:
          self.__konfig_lines.append(b''.join(self.__konfig_line).decode('ascii'))
          self.__konfig_line = []
      else:
        self.__konfig_line.append(byte)

  def __processWaitForPromptStepping(self, byte):
    found = self.__string_finder.processByte(byte)

    if self.__processPromptState(found):
      return
    if self.__processNumber(byte, self.__string_finder):
      return

    if self.__substate == OutputParser.STATE_START:
      if OutputParser.STR_SPLIT in found:
        assert self.__state == OutputParser.STEPPING
        self.__number = 0
        self.__substate = OutputParser.STATE_NUMBER
        self.__substate_after_number = OutputParser.STATE_SPLIT_after_steps
      return
    elif self.__substate == OutputParser.STATE_SPLIT_after_steps:
      if self.__number >= 0:
        self.__step_number = self.__number
        self.__number = -1
        self.__branches = []
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
  while life.isRunning():
    a = stdout.read(1)
    if a == b'':
      continue
    stdOutParser.process(a)

#-------------------------------------
#    Communication initialization
#-------------------------------------

def communicate(process, log, end_state, handler, life, message_thread, error_handler):
  stdErrParser = StdErrParser(end_state, log, message_thread)
  stdOutParser = OutputParser(handler, log, message_thread)

  handler.setParsers([stdOutParser, stdErrParser])

  error_handler.runGuardedThread(
      target=lambda : communicateWithStdErr(process.stderr, life, stdErrParser),
      daemon=True)
  error_handler.runGuardedThread(
      target=lambda : communicateWithStdOut(process.stdout, life, stdOutParser),
      daemon=True)

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
    self.__focused = False
    self.__title = 'Title'

  def setCoords_UI(self, minX, minY, maxX, maxY):
    assertOnUIThread()
    self.__minX = minX
    self.__minY = minY
    self.__maxX = maxX
    self.__maxY = maxY

    available = self.availableY_UI()
    if self.__currentY >= available + self.__offsetY:
      self.__currentY = available + self.__offsetY - 1

    self.assertConsistent_UI()

  def setFocused_UI(self, focused):
    assertOnUIThread()
    self.__focused = focused

  def assertConsistent_UI(self):
    assertOnUIThread()
    assert self.__minX >= 0
    assert self.__minY >= 0
    assert self.__maxX > self.__minX
    assert self.__maxY > self.__minY
    assert self.availableY_UI() > 0
    assert self.availableX_UI() > 0

    assert self.__currentY >= 0
    assert (self.__currentY < len(self.__lines)) or (not self.__lines), "currentY=%d lines=%s" % (self.__currentY, self.__lines)
    assert self.__currentY >= self.__offsetY
    assert self.__currentY - self.__offsetY < self.availableY_UI()

  def up_UI(self):
    assertOnUIThread()
    self.assertConsistent_UI()
    if self.__currentY == 0:
      return
    if self.__currentY == self.__offsetY:
      self.__offsetY -= 1
    self.__currentY -= 1
    self.assertConsistent_UI()
    self.__callLineChangeListeners()

  def previousPage_UI(self):
    assertOnUIThread()
    self.assertConsistent_UI()
    if self.__currentY == 0:
      return
    try:
      if self.__currentY > self.__offsetY:
        self.__currentY = self.__offsetY
        return
      assert self.availableY_UI() > 2
      self.__currentY -= self.availableY_UI() - 2
      if self.__currentY < 0:
        self.__currentY = 0
      self.__offsetY = self.__currentY
    finally:
      self.assertConsistent_UI()
      self.__callLineChangeListeners()

  def down_UI(self):
    assertOnUIThread()
    self.assertConsistent_UI()
    if self.__currentY == len(self.__lines) - 1 or (not self.__lines):
      return
    self.__currentY += 1
    if self.__currentY == self.__offsetY + self.availableY_UI():
      self.__offsetY += 1
    self.assertConsistent_UI()
    self.__callLineChangeListeners()

  def nextPage_UI(self):
    assertOnUIThread()
    self.assertConsistent_UI()
    max_line = len(self.__lines) - 1
    if self.__currentY == max_line or (not self.__lines):
      return
    try:
      lines_but_one = self.availableY_UI() - 1
      assert lines_but_one > 1
      last_line = self.__offsetY + lines_but_one
      if self.__currentY < last_line:
        self.__currentY = last_line
        if self.__currentY > max_line:
          self.__currentY = max_line
        return
      self.__currentY += lines_but_one - 1
      if self.__currentY > max_line:
        self.__currentY = max_line
      if self.__currentY - lines_but_one > self.__offsetY:
        self.__offsetY = self.__currentY - lines_but_one
    finally:
      self.assertConsistent_UI()
      self.__callLineChangeListeners()

  def setTitle_UI(self, title):
    assertOnUIThread()
    self.__title = title

  def setDrawLines_UI(self, lines):
    assertOnUIThread()
    self.assertConsistent_UI()

    self.__lines = lines

    lines_len = len(lines)
    if self.__offsetY >= lines_len:
      if lines_len > 0:
        self.__offsetY = len(lines) - 1
      else:
        self.__offsetY = 0
    if self.__currentY >= len(lines):
      self.__currentY = len(lines) - 1
      if self.__currentY < 0:
        self.__currentY = 0
    self.clear_UI()
    for y in range(0, lines_len):
      self.print_UI(0, y, lines[y])

    self.assertConsistent_UI()

  def clear_UI(self):
    assertOnUIThread()
    if self.__focused:
      attr = curses.A_REVERSE
    else:
      attr = curses.A_NORMAL

    title = self.__title
    if len(title) > self.availableX_UI():
      assert self.availableX_UI() >= 3
      title = '%s...' % title[:self.availableX_UI() - 3]
    
    self.__window.addch(self.__minY, self.__minX, curses.ACS_ULCORNER, attr)
    self.__window.addch(self.__minY, self.__maxX, curses.ACS_URCORNER, attr)
    self.__window.addch(self.__maxY, self.__minX, curses.ACS_LLCORNER, attr)
    self.__window.addch(self.__maxY, self.__maxX, curses.ACS_LRCORNER, attr)

    assert len(title) <= self.availableX_UI()
    before_title_start = self.__minX + 1
    before_title = int((self.availableX_UI() - len(title)) / 2)
    title_start = before_title_start + before_title
    after_title_start = title_start + len(title)
    after_title = self.availableX_UI() - (after_title_start - before_title_start)
    self.__window.addstr(self.__minY, title_start, title, attr)
    self.__window.hline(self.__minY, before_title_start, curses.ACS_HLINE, before_title, attr)
    self.__window.hline(self.__minY, after_title_start, curses.ACS_HLINE, after_title, attr)
    self.__window.hline(self.__maxY, self.__minX + 1, curses.ACS_HLINE, self.availableX_UI(), attr)

    self.__window.vline(self.__minY + 1, self.__minX, curses.ACS_VLINE, self.availableY_UI(), attr)
    self.__window.vline(self.__minY + 1, self.__maxX, curses.ACS_VLINE, self.availableY_UI(), attr)

    # This is faster than clear()
    for i in range(self.__minY + 1, self.__maxY):
      for j in range(self.__minX + 1, self.__maxX):
        self.__window.addch(i, j, ' ')

  # uses 0-based coordinates.
  def print_UI(self, x, y, message):
    assertOnUIThread()
    self.assertConsistent_UI()

    if y == self.__currentY:
      attr = curses.A_REVERSE
    else:
      attr = curses.A_NORMAL

    x -= self.__offsetX
    y -= self.__offsetY

    if y < 0 or y > self.availableY_UI() - 1:
      return
    if x + len(message) < -1 or x > self.availableX_UI() - 1:
      return
    if x < 0:
      message = message[-x:]
      x = 0
    if x + len(message) > self.availableX_UI():
      message = message[:self.availableX_UI() - x]
    self.__window.addstr(y + self.__minY + 1, x + self.__minX + 1, message, attr)

  def availableX_UI(self):
    assertOnUIThread()
    return self.__maxX - self.__minX - 1

  def availableY_UI(self):
    assertOnUIThread()
    return self.__maxY - self.__minY - 1

  def addLineChangeListener_UI(self, listener):
    assertOnUIThread()
    self.__line_change_listeners.append(listener)

  def __callLineChangeListeners(self):
    for listener in self.__line_change_listeners:
      listener(self.__currentY)

class TreeWindow(Window):
  def __init__(self, stdscr, node_tree, ui_messages):
    super(TreeWindow, self).__init__(stdscr)
    self.__node_tree = node_tree
    self.__line_number_to_id = {}
    self.__node_change_listeners = []
    ui_messages.add(
      self.addLineChangeListener_UI,
      self.__onLineChange)
    ui_messages.add(self.setTitle_UI, 'Tree')

  def draw_UI(self, xMin, yMin, xMax, yMax):
    assertOnUIThread()
    self.setCoords_UI(xMin, yMin, xMax, yMax)
    nodes_with_ids = []
    self.__treeLines(['  '], self.__node_tree, nodes_with_ids)
    self.__line_number_to_id = {}
    for line_number in range(0, len(nodes_with_ids)):
      self.__line_number_to_id[line_number] = nodes_with_ids[line_number][0]
    lines = [line for (_, line) in nodes_with_ids]
    self.setDrawLines_UI(lines)

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

class SubTreeWindow(Window):
  def __init__(self, stdscr, node_tree, ui_message_thread):
    super(SubTreeWindow, self).__init__(stdscr)
    self.__node_tree = node_tree
    self.__current_node_tree = node_tree
    self.__line_number_to_id = {}
    self.__node_change_listeners = []
    ui_message_thread.add(
      self.addLineChangeListener_UI,
      self.__onLineChange)
    ui_message_thread.add(self.setTitle_UI, 'Subnodes')
    self.__ui_message_thread = ui_message_thread

  def draw_UI(self, xMin, yMin, xMax, yMax):
    assertOnUIThread()
    self.setCoords_UI(xMin, yMin, xMax, yMax)
    nodes_with_ids = []
    self.__treeLines(self.__current_node_tree, nodes_with_ids)
    self.__line_number_to_id = {}
    for line_number in range(0, len(nodes_with_ids)):
      self.__line_number_to_id[line_number] = nodes_with_ids[line_number][0]
    lines = [line for (_, line) in nodes_with_ids]
    self.setDrawLines_UI(lines)

  def setNode(self, node_id):
    self.__node_id = node_id
    self.__current_node_tree = self.__node_tree.findTree(node_id)
    self.__ui_message_thread.add(self.setTitle_UI, str(self.__node_tree.findNode(self.__node_id)))

  def addNodeChangeListener(self, listener):
    self.__node_change_listeners.append(listener)

  def __treeLines(self, tree, output):
    for node in tree.nodes():
      output.append((node.number(), str(node)))

  def __onLineChange(self, new_line):
    node_id = self.__line_number_to_id[new_line]
    for listener in self.__node_change_listeners:
      listener(node_id)

class KonfigWindow(Window):
  def __init__(self, stdscr, node_tree, ui_message_thread, message_thread, handler):
    super(KonfigWindow, self).__init__(stdscr)
    self.__node_tree = node_tree
    self.__node_id = node_tree.getId()
    self.__message_thread = message_thread
    self.__handler = handler
    self.__ui_message_thread = ui_message_thread
    self.__ui_message_thread.add(self.setTitle_UI, str(self.__node_tree.findNode(self.__node_id)))

  def draw_UI(self, xMin, yMin, xMax, yMax):
    assertOnUIThread()
    self.setCoords_UI(xMin, yMin, xMax, yMax)
    lines = []
    self.__printKonfig(
        self.__node_tree.findNode(self.__node_id),
        self.availableX_UI(),
        lines)
    self.setDrawLines_UI(lines)

  def setNode(self, node_id):
    self.__node_id = node_id
    if not self.__node_tree.findNode(self.__node_id).hasKonfig():
      self.__message_thread.add(
          self.__handler.requestKonfig,
          node_id
      )
    self.__ui_message_thread.add(self.setTitle_UI, str(self.__node_tree.findNode(self.__node_id)))

  def __printKonfig(self, node, max_line_length, output):
    konfig = node.getKonfig()
    indented = indent.split(konfig, max_line_length)
    indent.unparse(0, indented, output)

class WindowEvents:
  def __init__(self, window, display, ui_message_thread):
    self.__window = window
    self.__display = display
    self.__ui_message_thread = ui_message_thread

  def up_UI(self):
    assertOnUIThread()
    self.__window.up_UI()
    self.__display.update()

  def previousPage_UI(self):
    assertOnUIThread()
    self.__window.previousPage_UI()
    self.__display.update()

  def down_UI(self):
    assertOnUIThread()
    self.__window.down_UI()
    self.__display.update()

  def nextPage_UI(self):
    assertOnUIThread()
    self.__window.nextPage_UI()
    self.__display.update()

  def setFocused_UI(self, focused):
    assertOnUIThread()
    self.__window.setFocused_UI(focused)

class Display:
  TREE_MIN_COLS = 60
  SUBTREE_MIN_COLS = 10
  WINDOW_MIN_COLS = 20
  def __init__(self, stdscr, node_tree, ui_message_thread, message_thread, handler):
    self.__stdscr = stdscr
    curses.curs_set(False)
    self.__tree_window = TreeWindow(stdscr, node_tree, ui_message_thread)
    self.__tree_window_events = WindowEvents(self.__tree_window, self, ui_message_thread)
    self.__subtree_window = SubTreeWindow(stdscr, node_tree, ui_message_thread)
    self.__subtree_window_events = WindowEvents(self.__subtree_window, self, ui_message_thread)
    self.__konfig_window = KonfigWindow(stdscr, node_tree, ui_message_thread, message_thread, handler)
    self.__konfig_window_events = WindowEvents(self.__konfig_window, self, ui_message_thread)
    self.__current_window_index = 0
    self.__all_window_events = [
        self.__tree_window_events,
        self.__subtree_window_events,
        self.__konfig_window_events
      ]
    self.__ui_message_thread = ui_message_thread

  def currentWindow_UI(self):
    assertOnUIThread()
    return self.__all_window_events[self.__current_window_index]

  def getTreeNodeWindow(self):
    return self.__tree_window

  def getSubtreeNodeWindow(self):
    return self.__subtree_window

  def getKonfigWindow(self):
    return self.__konfig_window

  def update(self):
    self.__ui_message_thread.add(self.__update_UI)

  def repaint_UI(self):
    assertOnUIThread()
    self.__stdscr.clear()
    self.__update_UI()

  def __update_UI(self):
    assertOnUIThread()

    for w in self.__all_window_events:
      w.setFocused_UI(False)
    self.currentWindow_UI().setFocused_UI(True)

    lines, cols = self.__stdscr.getmaxyx()
    assert cols > Display.TREE_MIN_COLS + Display.WINDOW_MIN_COLS
    start_cols = 0
    end_cols = start_cols + Display.TREE_MIN_COLS
    self.__tree_window.draw_UI(start_cols, 0, end_cols, lines - 2)
    start_cols = end_cols + 1
    end_cols = start_cols + Display.SUBTREE_MIN_COLS
    self.__subtree_window.draw_UI(start_cols, 0, end_cols, lines - 2)
    start_cols = end_cols + 1
    end_cols = cols - 1
    self.__konfig_window.draw_UI(start_cols, 0, end_cols, lines - 2)
    self.__stdscr.addstr(lines - 1, 0, "F10-Quit  F9-Repaint")
    self.__stdscr.refresh()

  def tab_UI(self):
    assertOnUIThread()
    self.__current_window_index += 1
    if self.__current_window_index >= len(self.__all_window_events):
      self.__current_window_index = 0
    self.__update_UI()

  def backTab_UI(self):
    assertOnUIThread()
    self.__current_window_index -= 1
    if self.__current_window_index >= len(self.__all_window_events):
      self.__current_window_index = 0
    self.__update_UI()

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
    finally:
      self.__life.die()

def runProcessWatcher(life, error_handler, process):
  error_handler.runGuardedThread(
      target=ProcessWatcher(life, process).run,
      daemon=True)

class TreeChangeListener:
  def __init__(self, display):
    self.__display = display

  def onChange(self):
    self.__display.update()

#-------------------------------------
#           COMMUNICATION
#-------------------------------------

class KeyboardReader:
  def __init__(self, message_thread, ui_message_thread, life, connector, window):
    self.__message_thread = message_thread
    self.__ui_message_thread = ui_message_thread
    self.__connector = connector
    self.__window = window
    self.__life = life
  
  def maybeReadKey_UI(self):
    try:
      assertOnUIThread()
      c = self.__window.getch()
      if c == -1:
        time.sleep(0.1)
        return
      self.__message_thread.add(self.__connector.keyEvent, c)
    finally:
      self.__ui_message_thread.add(self.maybeReadKey_UI)

#-------------------------------------
#       Connecting everything
#-------------------------------------

class ConnectEverything:
  def __init__(self, life, windows, ui_message_thread):
    self.__life = life
    self.__windows = windows
    self.__ui_message_thread = ui_message_thread
    windows.getTreeNodeWindow().addNodeChangeListener(self.__onTreeNodeChange)
    windows.getSubtreeNodeWindow().addNodeChangeListener(self.__onSubtreeNodeChange)

  def keyEvent(self, c):
    if c == curses.KEY_F10:
      self.__life.die()
    if c == curses.KEY_F9:
      self.__ui_message_thread.add(self.__windows.repaint_UI)
    elif c == curses.KEY_UP:
      self.__ui_message_thread.add(lambda: self.__windows.currentWindow_UI().up_UI())
    elif c == curses.KEY_DOWN:
      self.__ui_message_thread.add(lambda: self.__windows.currentWindow_UI().down_UI())
    elif c == curses.KEY_PPAGE:
      self.__ui_message_thread.add(lambda: self.__windows.currentWindow_UI().previousPage_UI())
    elif c == curses.KEY_NPAGE:
      self.__ui_message_thread.add(lambda: self.__windows.currentWindow_UI().nextPage_UI())
    elif c == curses.ascii.TAB:
      self.__ui_message_thread.add(self.__windows.tab_UI)
    elif c == curses.KEY_BTAB:
      self.__ui_message_thread.add(self.__windows.backTab_UI)

  def __onTreeNodeChange(self, node_id):
    self.__windows.getSubtreeNodeWindow().setNode(node_id)
    self.__windows.getKonfigWindow().setNode(node_id)
    self.__windows.update()

  def __onSubtreeNodeChange(self, node_id):
    self.__windows.getKonfigWindow().setNode(node_id)
    self.__windows.update()

def main(argv, live, error_handler, stdscr):
  stdscr.nodelay(True)

  log = open('debug.log', 'wb')

  message_thread = messages.MessageThread(live, error_handler)
  live.setMessageThread(message_thread)

  ui_message_thread = messages.MessageThread(live, error_handler)
  global UI_THREAD
  UI_THREAD = ui_message_thread.getThread()

  p = subprocess.Popen(
      argv,
      bufsize=0,
      stdin=subprocess.PIPE,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE)

  runProcessWatcher(live, error_handler, p)

  end_state = EndState()
  handler = Handler(p.stdin, log, message_thread, live, end_state)

  d = Display(stdscr, handler.nodeTree(), ui_message_thread, message_thread, handler)
  d.update()

  handler.nodeTree().addChangeListener(TreeChangeListener(d))

  connector = ConnectEverything(live, d, ui_message_thread)

  keyboard_reader = KeyboardReader(
      message_thread, ui_message_thread, live, connector, stdscr)
  ui_message_thread.add(keyboard_reader.maybeReadKey_UI)

  try:
    communicate(p, log, end_state, handler, live, message_thread, error_handler)
    while live.isRunning():
      try:
        p.wait(1)
      except subprocess.TimeoutExpired:
        pass
      exit_code = p.poll()
      if exit_code is not None and exit_code != 0:
        debug.append('kore-repl exited with code %d.' % exit_code)
  finally:
    p.kill()

if __name__ == "__main__":
  try:
    live = Life()  # Live is life.
    error_handler = errors.ErrorHandler(live)
    curses.wrapper(lambda stdscr : main(sys.argv[1:], live, error_handler, stdscr))
  finally:
    print('***********************************')
    print('\n'.join(debug))
    print('\n'.join(error_handler.debugMessages()))
