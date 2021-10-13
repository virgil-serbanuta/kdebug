#!/usr/bin/env python3

import curses
import curses.ascii
import os
import subprocess
import sys
import tempfile
import threading

import errors
import graph
import messages
import output
import prooftree
import userinterface

debug = []
UI_THREAD = None
TEMP_DIR_NAME = None
LOG_FILE = '/mnt/data/tmp/debug.log'

def graphFileNoExtension():
  return os.path.join(TEMP_DIR_NAME, 'graph')

def graphFile():
  return "%s.svg" % graphFileNoExtension()

def assertOnUIThread():
  assert threading.current_thread().ident == UI_THREAD.ident

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
    self.__node_tree = prooftree.NodeTree(0, message_thread, userinterface.NodeUIData)
    self.__last_config_number = -1
    self.__next_node_state = prooftree.Node.NORMAL
    self.__life = life
    self.__end_state = end_state
    self.__ui_graph = graph.UIGraph()

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
    if self.__next_node_state != prooftree.Node.NORMAL:
      self.__node_tree.setNodeState(config_number, self.__next_node_state)
      self.__next_node_state = prooftree.Node.NORMAL

  def onBranches(self, steps, branches):
    self.__node_tree.addChildren(self.__last_config_number, branches)
    for c in branches:
      self.__nodes_seen.add(c)
    self.__unexpanded_nodes += branches
    self.__unknown_konfigs.append(self.__last_config_number)
    self.__unknown_konfigs += branches

  def onProofEnd(self, steps):
    if self.__end_state.isStuck():
      self.__next_node_state = prooftree.Node.STUCK
    elif self.__end_state.isFailedEnd():
      self.__next_node_state = prooftree.Node.PROOF_END_FAILED
    elif self.__end_state.isError():
      self.__next_node_state = prooftree.Node.ERROR
    else:
      self.__next_node_state = prooftree.Node.PROOF_END

  def onKonfig(self, node_id, konfig_lines):
    self.__node_tree.findNode(node_id).setKonfig(konfig_lines)

  def onGraph(self):
    self.__ui_graph.setGraph(graph.parseGraph(graphFile()))

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

  def graph(self):
    return self.__ui_graph

  def __restartIfWaitingAtPrompt(self):
    if self.__state == Handler.PROMPT_IDLE:
      self.onAtPrompt(self.__last_config_number)

  def __parsersPrepareForStep(self):
    for p in self.__parsers:
      p.prepareForStep()

  def __parsersPrepareForKonfig(self):
    for p in self.__parsers:
      p.prepareForKonfig()

  def __parsersPrepareForGraph(self):
    for p in self.__parsers:
      p.prepareForGraph()

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
      self.__pending_commands.append(self.__graph)

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

  def __graph(self):
    self.__parsersPrepareForGraph()
    self.__sendCommand(bytes('graph expanded %s svg\n' % graphFileNoExtension(), 'ascii'))

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
#    Output processing
#-------------------------------------

def communicateWithParser(stderr, life, parser):
  while life.isRunning():
    a = stderr.read(1)
    if a == b'':
      continue
    parser.process(a)

def communicate(process, log, end_state, handler, life, message_thread, error_handler):
  stdErrParser = output.StdErrParser(end_state, log, message_thread)
  stdOutParser = output.OutputParser(handler, log, message_thread)

  handler.setParsers([stdOutParser, stdErrParser])

  error_handler.runGuardedThread(
      target=lambda : communicateWithParser(process.stderr, life, stdErrParser),
      daemon=True)
  error_handler.runGuardedThread(
      target=lambda : communicateWithParser(process.stdout, life, stdOutParser),
      daemon=True)

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
    elif c == curses.KEY_HOME:
      self.__ui_message_thread.add(lambda: self.__windows.currentWindow_UI().home_UI())
    elif c == curses.KEY_END:
      self.__ui_message_thread.add(lambda: self.__windows.currentWindow_UI().end_UI())
    elif c == ord(' '):
      self.__ui_message_thread.add(lambda: self.__windows.currentWindow_UI().space_UI())
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

  log = open(LOG_FILE, 'wb')

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

  d = userinterface.Display(
      stdscr,
      handler.nodeTree(),
      handler.graph(),
      ui_message_thread,
      message_thread,
      handler,
      assertOnUIThread)
  d.update()

  handler.nodeTree().getChangeListeners().add(d.update)
  handler.graph().getChangeListeners().add(d.update)

  connector = ConnectEverything(live, d, ui_message_thread)

  keyboard_reader = userinterface.KeyboardReader(
      message_thread, ui_message_thread, connector, stdscr, assertOnUIThread)
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
    with tempfile.TemporaryDirectory() as tmp_dir_name:
      TEMP_DIR_NAME = tmp_dir_name
      live = Life()  # Live is life.
      error_handler = errors.ErrorHandler(live)
      curses.wrapper(lambda stdscr : main(sys.argv[1:], live, error_handler, stdscr))
  finally:
    print('***********************************')
    print('\n'.join(debug))
    print('\n'.join(error_handler.debugMessages()))
    print('Log file: %s' % LOG_FILE)
