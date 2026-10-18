"""Encrypted durable single-user task repository. No application imports."""
from contextlib import contextmanager
import json
import logging
from pathlib import Path
import sqlite3
import uuid
from cryptography.fernet import Fernet, InvalidToken
from evidence_check.contracts.errors import EvidenceCheckError
from evidence_check.contracts.product_policy import ProductPolicy

_LOG=logging.getLogger(__name__)


class TaskStore:
    def __init__(self,directory: Path,key: bytes,policy: ProductPolicy):
        directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        directory.chmod(0o700)
        self.path=directory/'tasks.sqlite3';self.cipher=Fernet(key);self.policy=policy
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, owner TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, payload BLOB NOT NULL, result BLOB, error TEXT)')
            db.execute('CREATE INDEX IF NOT EXISTS tasks_expiry ON tasks(expires)')
            columns={row[1] for row in db.execute('PRAGMA table_info(tasks)')}
            if 'diagnostics' not in columns:db.execute('ALTER TABLE tasks ADD COLUMN diagnostics BLOB')
        self.path.chmod(0o600)

    @contextmanager
    def connection(self):
        db=None
        try:
            db=sqlite3.connect(self.path,timeout=10)
            db.row_factory=sqlite3.Row
            db.execute('PRAGMA secure_delete=ON')
            with db:yield db
        except sqlite3.Error as error:
            _LOG.error('storage_failed')
            raise EvidenceCheckError('storage_failed','Task storage operation failed.') from error
        finally:
            if db is not None:db.close()

    def _encode(self,value):return self.cipher.encrypt(json.dumps(value,ensure_ascii=False).encode())

    def _decode(self,value):
        try:return json.loads(self.cipher.decrypt(value))
        except (InvalidToken,ValueError) as error:
            _LOG.error('storage_integrity_failed')
            raise EvidenceCheckError('storage_integrity_failed','Stored task could not be authenticated or decrypted.') from error

    def create(self,owner,payload,now):
        task_id=uuid.uuid4().hex
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            count=db.execute('SELECT COUNT(*) FROM tasks WHERE owner=? AND expires>?',(owner,now)).fetchone()[0]
            if count>=self.policy.limits.max_tasks:raise EvidenceCheckError('task_limit','Delete completed tasks before submitting more.')
            db.execute('INSERT INTO tasks(id,owner,status,created,expires,payload) VALUES(?,?,?,?,?,?)',
                (task_id,owner,self.policy.lifecycle.queued,now,now+self.policy.lifecycle.retention_hours*3600,self._encode(payload)))
        return task_id

    def list(self,owner,now):
        with self.connection() as db:
            rows=db.execute('SELECT id,status,created,expires,error FROM tasks WHERE owner=? AND expires>? ORDER BY created DESC',(owner,now)).fetchall()
        return [dict(row) for row in rows]

    def get(self,task_id,owner,now,with_payload=False):
        with self.connection() as db:
            row=db.execute('SELECT * FROM tasks WHERE id=? AND owner=? AND expires>?',(task_id,owner,now)).fetchone()
        if row is None:return None
        data={key:row[key] for key in ('id','status','created','expires','error')}
        data['result']=self._decode(row['result']) if row['result'] else None
        if with_payload:data['payload']=self._decode(row['payload'])
        return data

    def acquire(self,now):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM tasks WHERE status=? AND expires>? ORDER BY created LIMIT 1',(self.policy.lifecycle.queued,now)).fetchone()
            if row is None:return None
            db.execute('UPDATE tasks SET status=?,attempts=attempts+1 WHERE id=?',(self.policy.lifecycle.running,row['id']))
        return row['id'],self._decode(row['payload'])

    def finish(self,task_id,result):
        with self.connection() as db:
            db.execute('UPDATE tasks SET status=?,result=? WHERE id=? AND status=?',
                (self.policy.lifecycle.done,self._encode(result),task_id,self.policy.lifecycle.running))

    def fail(self,task_id,code,diagnostics=None):
        with self.connection() as db:
            db.execute('UPDATE tasks SET status=?,error=?,diagnostics=? WHERE id=? AND status=?',
                (self.policy.lifecycle.failed,code,self._encode(diagnostics or {}),task_id,self.policy.lifecycle.running))

    def recover(self):
        with self.connection() as db:
            db.execute('UPDATE tasks SET status=? WHERE status=? AND attempts<?',
                (self.policy.lifecycle.queued,self.policy.lifecycle.running,self.policy.lifecycle.retry_limit))
            db.execute('UPDATE tasks SET status=?,error=? WHERE status=?',
                (self.policy.lifecycle.failed,'restart_retry_exhausted',self.policy.lifecycle.running))

    def expire(self,now):
        with self.connection() as db:count=db.execute('DELETE FROM tasks WHERE expires<=?',(now,)).rowcount
        if count:_LOG.info('expired_tasks_deleted count=%s',count)
        return count

    def delete(self,task_id,owner):
        with self.connection() as db:return db.execute('DELETE FROM tasks WHERE id=? AND owner=?',(task_id,owner)).rowcount>0
