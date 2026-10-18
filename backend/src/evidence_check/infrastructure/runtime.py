"""Local runtime keys/session authentication. Secrets never enter logs."""
import hashlib
import hmac
import os
from pathlib import Path
import secrets
from cryptography.fernet import Fernet
from evidence_check.contracts.errors import EvidenceCheckError


def _retained_secret(path: Path,generate):
    if path.exists():return path.read_bytes().strip()
    value=generate()
    try:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as file:file.write(value+b'\n')
    except FileExistsError:return path.read_bytes().strip()
    return value


class Runtime:
    def __init__(self,directory: Path):
        directory.mkdir(parents=True,exist_ok=True,mode=0o700);directory.chmod(0o700)
        self.directory=directory
        self.key=os.environ.get('EVIDENCE_DATA_KEY','').encode() or _retained_secret(directory/'data.key',Fernet.generate_key)
        self.password=os.environ.get('EVIDENCE_ACCESS_PASSWORD','').encode() or _retained_secret(directory/'access-password',lambda:secrets.token_urlsafe().encode())
        self.signing=_retained_secret(directory/'session.key',lambda:secrets.token_bytes(32).hex().encode())
        self.owner=hashlib.sha256(self.signing).hexdigest()
        sentinel=directory/'key-check'
        cipher=Fernet(self.key)
        try:
            if sentinel.exists():cipher.decrypt(sentinel.read_bytes())
            else:
                fd=os.open(sentinel,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                with os.fdopen(fd,'wb') as file:file.write(cipher.encrypt(secrets.token_bytes(32)))
        except Exception as error:
            raise EvidenceCheckError('runtime_key_invalid','The runtime key does not match retained data.') from error

    def login(self,password,now,hours):
        if not hmac.compare_digest(password.encode(),self.password):return None
        payload=str(int(now+hours*3600))
        signature=hmac.new(self.signing,payload.encode(),hashlib.sha256).hexdigest()
        return payload+'.'+signature

    def authenticate(self,token,now):
        try:
            expires,signature=token.split('.')
            expected=hmac.new(self.signing,expires.encode(),hashlib.sha256).hexdigest()
            return hmac.compare_digest(signature,expected) and int(expires)>now
        except (ValueError,AttributeError):return False
