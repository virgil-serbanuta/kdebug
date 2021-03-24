import threading

#-------------------------------------
#           COMMUNICATION
#-------------------------------------

class MessageThread:
  def __init__(self, life, error_handler):
    self.__messages = []
    self.__life = life

    self.__block = threading.Event()
    self.__mutex = threading.Lock()
    self.__thread = error_handler.runGuardedThread(target=self.__run, daemon=True)

  def add(self, message, *args, **kwrds):
    self.__mutex.acquire()
    try:
      self.__messages.append((message, args, kwrds))
      self.__block.set()
    finally:
      self.__mutex.release()

  def getThread(self):
    return self.__thread

  # TODO: This should be rewritten for the UI thread
  def die(self):
    # Assumes this is called from life.die()
    self.__block.set()

  def __run(self):
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

class Listeners:
  def __init__(self):
    self.__listeners = []

  def add(self, listener, *args, **kwrds):
    self.__listeners.append((listener, args, kwrds))

  def notify(self):
    for (listener, args, kwrds) in self.__listeners:
      listener(*args, **kwrds)
