import curses
import indent
import time

import messages

#-------------------------------------
#           Display
#-------------------------------------

class Window:
  def __init__(self, window, assertOnUIThread):
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
    self._assertOnUIThread = assertOnUIThread

  def setCoords_UI(self, minX, minY, maxX, maxY):
    self._assertOnUIThread()
    self.__minX = minX
    self.__minY = minY
    self.__maxX = maxX
    self.__maxY = maxY

    available = self.availableY_UI()
    if self.__currentY >= available + self.__offsetY:
      self.__currentY = available + self.__offsetY - 1

    self.assertConsistent_UI()

  def setFocused_UI(self, focused):
    self._assertOnUIThread()
    self.__focused = focused

  def assertConsistent_UI(self):
    self._assertOnUIThread()
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
    self._assertOnUIThread()
    self.assertConsistent_UI()
    if self.__currentY == 0:
      return
    if self.__currentY == self.__offsetY:
      self.__offsetY -= 1
    self.__currentY -= 1
    self.assertConsistent_UI()
    self.__callLineChangeListeners()

  def previousPage_UI(self):
    self._assertOnUIThread()
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

  def home_UI(self):
    self._assertOnUIThread()
    self.assertConsistent_UI()
    self.__currentY = 0
    self.__offsetY = 0
    self.assertConsistent_UI()
    self.__callLineChangeListeners()

  def down_UI(self):
    self._assertOnUIThread()
    self.assertConsistent_UI()
    if self.__currentY == len(self.__lines) - 1 or (not self.__lines):
      return
    self.__currentY += 1
    if self.__currentY == self.__offsetY + self.availableY_UI():
      self.__offsetY += 1
    self.assertConsistent_UI()
    self.__callLineChangeListeners()
  
  def space_UI(self):
    self._assertOnUIThread()
    pass

  def nextPage_UI(self):
    self._assertOnUIThread()
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

  def end_UI(self):
    self._assertOnUIThread()
    self.assertConsistent_UI()
    try:
      self.__currentY = len(self.__lines) - 1
      if self.__currentY < 0:
        self.__currentY = 0
        self.__offsetY = 0
        return
      self.__offsetY = self.__currentY - (self.availableY_UI() - 1)
      if self.__offsetY < 0:
        self.__offsetY = 0
    finally:
      self.assertConsistent_UI()
      self.__callLineChangeListeners()

  def setTitle_UI(self, title):
    self._assertOnUIThread()
    self.__title = title

  def setDrawLines_UI(self, lines):
    self._assertOnUIThread()
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
    self._assertOnUIThread()
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
    self._assertOnUIThread()
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
    self._assertOnUIThread()
    return self.__maxX - self.__minX - 1

  def availableY_UI(self):
    self._assertOnUIThread()
    return self.__maxY - self.__minY - 1

  def addLineChangeListener_UI(self, listener):
    self._assertOnUIThread()
    self.__line_change_listeners.append(listener)

  def __callLineChangeListeners(self):
    for listener in self.__line_change_listeners:
      listener(self.__currentY)

class TreeWindow(Window):
  def __init__(self, stdscr, node_tree, graph, ui_messages, assertOnUIThread):
    super(TreeWindow, self).__init__(stdscr, assertOnUIThread)
    self.__node_tree = node_tree
    self.__graph = graph
    self.__line_number_to_id = {}
    self.__node_change_listeners = []
    self.__last_line = 0
    ui_messages.add(
      self.addLineChangeListener_UI,
      self.__onLineChange)
    ui_messages.add(self.setTitle_UI, 'Tree')

  def space_UI(self):
    node_id = self.__line_number_to_id[self.__last_line]
    self.__node_tree.findNode(node_id).getUIData().toggleCollapsed()

  def draw_UI(self, xMin, yMin, xMax, yMax):
    self._assertOnUIThread()
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
    collapsed = tree.startNode().getUIData().isCollapsed()
    display = []
    if indent:
      display = [l for l in indent[:-1]]
    if collapsed:
      display.append('*- ')
    else:
      display.append('+- ')

    if tree.startNode().number() == tree.endNode().number():
      display.append(str(tree.startNode()))
    else:
      display.append(str(tree.startNode()))
      display.append('-')
      display.append(str(tree.endNode()))

    edgeName = self.__graph.incomingEdge(tree.startNode().number())
    if (edgeName):
      display.append('  (')
      display.append(edgeName)
      display.append(')')

    output.append((tree.getId(), ''.join(display)))

    nextIndent = [l for l in indent]
    if tree.children() and not collapsed:
      nextIndent.append('| ')
      for c in tree.children()[:-1]:
        self.__treeLines(nextIndent, c, output)
      nextIndent[-1] = '  '
      self.__treeLines(nextIndent, tree.children()[-1], output)

  def __onLineChange(self, new_line):
    self.__last_line = new_line
    node_id = self.__line_number_to_id[new_line]
    for listener in self.__node_change_listeners:
      listener(node_id)

class SubTreeWindow(Window):
  def __init__(self, stdscr, node_tree, graph, ui_message_thread, assertOnUIThread):
    super(SubTreeWindow, self).__init__(stdscr, assertOnUIThread)
    self.__node_tree = node_tree
    self.__graph = graph
    self.__current_node_tree = node_tree
    self.__line_number_to_id = {}
    self.__node_change_listeners = []
    ui_message_thread.add(
      self.addLineChangeListener_UI,
      self.__onLineChange)
    ui_message_thread.add(self.setTitle_UI, 'Subnodes')
    self.__ui_message_thread = ui_message_thread

  def draw_UI(self, xMin, yMin, xMax, yMax):
    self._assertOnUIThread()
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
      display = [str(node)]
      edgeName = self.__graph.incomingEdge(node.number())
      if (edgeName):
        display.append('  (')
        display.append(edgeName)
        display.append(')')
      output.append((node.number(), ''.join(display)))

  def __onLineChange(self, new_line):
    node_id = self.__line_number_to_id[new_line]
    for listener in self.__node_change_listeners:
      listener(node_id)

class KonfigWindow(Window):
  def __init__(self, stdscr, node_tree, ui_message_thread, message_thread, handler, assertOnUIThread):
    super(KonfigWindow, self).__init__(stdscr, assertOnUIThread)
    self.__node_tree = node_tree
    self.__node_id = node_tree.getId()
    self.__message_thread = message_thread
    self.__handler = handler
    self.__ui_message_thread = ui_message_thread
    self.__ui_message_thread.add(self.setTitle_UI, str(self.__node_tree.findNode(self.__node_id)))

  def draw_UI(self, xMin, yMin, xMax, yMax):
    self._assertOnUIThread()
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
  def __init__(self, window, display, assertOnUIThread):
    self.__window = window
    self.__display = display
    self.__assertOnUIThread = assertOnUIThread

  def up_UI(self):
    self.__assertOnUIThread()
    self.__window.up_UI()
    self.__display.update()

  def previousPage_UI(self):
    self.__assertOnUIThread()
    self.__window.previousPage_UI()
    self.__display.update()

  def home_UI(self):
    self.__assertOnUIThread()
    self.__window.home_UI()
    self.__display.update()

  def down_UI(self):
    self.__assertOnUIThread()
    self.__window.down_UI()
    self.__display.update()

  def nextPage_UI(self):
    self.__assertOnUIThread()
    self.__window.nextPage_UI()
    self.__display.update()

  def end_UI(self):
    self.__assertOnUIThread()
    self.__window.end_UI()
    self.__display.update()

  def space_UI(self):
    self.__assertOnUIThread()
    self.__window.space_UI()
    self.__display.update()

  def setFocused_UI(self, focused):
    self.__assertOnUIThread()
    self.__window.setFocused_UI(focused)

class Display:
  TREE_MIN_COLS = 60
  SUBTREE_MIN_COLS = 30
  WINDOW_MIN_COLS = 20
  def __init__(self, stdscr, node_tree, graph, ui_message_thread, message_thread, handler, assertOnUIThread):
    self.__stdscr = stdscr
    curses.curs_set(False)
    self.__tree_window = TreeWindow(stdscr, node_tree, graph, ui_message_thread, assertOnUIThread)
    self.__tree_window_events = WindowEvents(self.__tree_window, self, assertOnUIThread)
    self.__subtree_window = SubTreeWindow(stdscr, node_tree, graph, ui_message_thread, assertOnUIThread)
    self.__subtree_window_events = WindowEvents(self.__subtree_window, self, assertOnUIThread)
    self.__konfig_window = KonfigWindow(stdscr, node_tree, ui_message_thread, message_thread, handler, assertOnUIThread)
    self.__konfig_window_events = WindowEvents(self.__konfig_window, self, assertOnUIThread)
    self.__current_window_index = 0
    self.__all_window_events = [
        self.__tree_window_events,
        self.__subtree_window_events,
        self.__konfig_window_events
      ]
    self.__ui_message_thread = ui_message_thread
    self.__assertOnUIThread = assertOnUIThread

  def currentWindow_UI(self):
    self.__assertOnUIThread()
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
    self.__assertOnUIThread()
    self.__stdscr.clear()
    self.__update_UI()

  def __update_UI(self):
    self.__assertOnUIThread()

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
    self.__assertOnUIThread()
    self.__current_window_index += 1
    if self.__current_window_index >= len(self.__all_window_events):
      self.__current_window_index = 0
    self.__update_UI()

  def backTab_UI(self):
    self.__assertOnUIThread()
    self.__current_window_index -= 1
    if self.__current_window_index >= len(self.__all_window_events):
      self.__current_window_index = 0
    self.__update_UI()

#-------------------------------------
#           COMMUNICATION
#-------------------------------------

class KeyboardReader:
  def __init__(self, message_thread, ui_message_thread, connector, window, assertOnUIThread):
    self.__message_thread = message_thread
    self.__ui_message_thread = ui_message_thread
    self.__connector = connector
    self.__window = window
    self.__assertOnUIThread = assertOnUIThread
  
  def maybeReadKey_UI(self):
    try:
      self.__assertOnUIThread()
      c = self.__window.getch()
      if c == -1:
        time.sleep(0.1)
        return
      self.__message_thread.add(self.__connector.keyEvent, c)
    finally:
      self.__ui_message_thread.add(self.maybeReadKey_UI)

class NodeUIData:
  def __init__(self):
    self.__collapsed = False
    self.__change_listeners = messages.Listeners()

  def getChangeListeners(self):
    return self.__change_listeners

  def toggleCollapsed(self):
    self.__collapsed = not self.__collapsed
    self.__change_listeners.notify()

  def isCollapsed(self):
    return self.__collapsed
