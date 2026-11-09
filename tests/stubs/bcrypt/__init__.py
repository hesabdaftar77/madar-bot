import hashlib
def gensalt(): return b"salt"
def hashpw(p,s): return b"H"+hashlib.sha256(p).hexdigest().encode()
def checkpw(p,h): return hashpw(p,b"")==h
