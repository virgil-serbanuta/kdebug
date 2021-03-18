import threading
import traceback

class ErrorHandler:
  def __init__(self, life):
    self.__life = life
    self.__debug = []
    self.__mutex = threading.Lock()

  def runAndDie(self, callback, *args, **kwrds):
    try:
      callback(*args, **kwrds)
    except Exception as e:
      self.__mutex.acquire()
      try:
        self.__debug.append(''.join(traceback.TracebackException.from_exception(e).format(chain=True)))
      finally:
        self.__mutex.release()
      raise
    finally:
      self.__life.die()

  def debugMessages(self):
      self.__mutex.acquire()
      try:
        return list(self.__debug)
      finally:
        self.__mutex.release()

  def runGuardedThread(self, group=None, target=None, name=None, args=(), kwargs={}, *, daemon=None):
    def guardedTarget(*args, **kwrds):
      self.runAndDie(target, *args, **kwrds)
    thread = threading.Thread(
        group=group,
        target=guardedTarget,
        name=name,
        args=args,
        kwargs=kwargs,
        daemon=daemon)
    thread.start()
    return thread

