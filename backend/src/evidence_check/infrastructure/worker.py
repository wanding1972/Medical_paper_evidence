"""One durable worker per data directory; effects injected as a callback."""
import fcntl
import logging
import threading
import time
from evidence_check.contracts.errors import EvidenceCheckError

_LOG=logging.getLogger(__name__)


class Worker:
    def __init__(self,store,execute):
        self.store=store;self.execute=execute;self.stop_event=threading.Event()
        self.lock=None;self.thread=None

    def start(self):
        self.lock=(self.store.path.parent/'worker.lock').open('a')
        try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as error:
            self.lock.close();self.lock=None
            raise EvidenceCheckError('worker_already_running','Only one worker may use this data directory.') from error
        self.store.recover()
        self.thread=threading.Thread(target=self.run,name='evidence-worker',daemon=True);self.thread.start()

    def run(self):
        next_cleanup=0
        while not self.stop_event.is_set():
            try:
                now=time.time()
                if now>=next_cleanup:
                    self.store.expire(now);next_cleanup=now+self.store.policy.lifecycle.cleanup_seconds
                item=self.store.acquire(now)
                if item is None:
                    self.stop_event.wait(self.store.policy.lifecycle.poll_seconds);continue
                task_id,payload=item
                try:self.store.finish(task_id,self.execute(payload))
                except EvidenceCheckError as error:
                    _LOG.warning('task_step_failed code=%s',error.code)
                    if not self.stop_event.is_set():self.store.fail(task_id,error.code,getattr(error,'diagnostics',None))
                except Exception:
                    _LOG.error('task_internal_error');self.store.fail(task_id,'task_internal_error')
            except EvidenceCheckError:
                _LOG.error('worker_storage_or_cleanup_failed')
                self.stop_event.wait(self.store.policy.lifecycle.cleanup_seconds)

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join()
        if self.lock:
            fcntl.flock(self.lock,fcntl.LOCK_UN);self.lock.close();self.lock=None
