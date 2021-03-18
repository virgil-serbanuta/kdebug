import konfig

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

