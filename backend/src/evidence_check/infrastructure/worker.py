"""One durable worker per data directory; effects injected as a callback."""
import logging
import threading
import time
from filelock import FileLock, Timeout
from evidence_check.contracts.errors import EvidenceCheckError

_LOG=logging.getLogger(__name__)


class Worker:
    def __init__(self,store,execute):
        self.store=store;self.execute=execute;self.stop_event=threading.Event()
        self.lock=None;self.thread=None

    def start(self):
        self.lock=FileLock(self.store.path.parent/'worker.lock',timeout=0,thread_local=False)
        try:self.lock.acquire()
        except Timeout as error:
            self.lock=None
            raise EvidenceCheckError('worker_already_running','Only one worker may use this data directory.') from error
        except OSError as error:
            self.lock=None
            _LOG.error('worker_lock_failed')
            raise EvidenceCheckError('worker_lock_failed','Cannot acquire the worker lock.') from error
        try:
            self.store.recover()
            self.thread=threading.Thread(target=self.run,name='evidence-worker',daemon=True);self.thread.start()
        except Exception:
            self.lock.release();self.lock=None
            raise

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
            try:self.lock.release()
            except OSError as error:
                _LOG.error('worker_unlock_failed')
                raise EvidenceCheckError('worker_unlock_failed','Cannot release the worker lock.') from error
            self.lock=None
