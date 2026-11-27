"""Read protected role-specific credentials; no environment fallback.

Caller is the protected executor, not a worker. Role keys must be issued
and revoked independently by HAA. This module does not provision them.
"""
from __future__ import annotations
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import build_opener, ProxyHandler, HTTPRedirectHandler
from scripts.haa.client import (RequesterConfig,ExecutorConfig,
    HaaRequesterClient,HaaExecutorClient,HaaClientError)
from scripts.haa.protected_host import read_private_file


class CredentialError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise HaaClientError("HAA_REDIRECT_DENIED")


def _read(path,uid,keys):
    try:
        def unique(items):
            out={}
            for k,v in items:
                if k in out:
                    raise ValueError("duplicate")
                out[k]=v
            return out
        result=json.loads(read_private_file(path,owner_uid=uid),object_pairs_hook=unique)
    except (OSError,ValueError,RuntimeError):
        raise CredentialError("PROTECTED_ROLE_CONFIGURATION_UNAVAILABLE") from None
    if (not isinstance(result,dict) or set(result)!=keys
            or any(not isinstance(v,str) or not v or v!=v.strip()
                   or any(ord(c)<32 for c in v) for v in result.values())):
        raise CredentialError("INVALID_PROTECTED_ROLE_CONFIGURATION")
    return result


def load_clients(*, state:Path, executor_uid:int):
    directory=state/"credentials"
    req=_read(directory/"requester.json",executor_uid,
              {"base_url","api_key","approver_principal_id","executor_audience"})
    exe=_read(directory/"executor.json",executor_uid,
              {"base_url","api_key","executor_audience"})
    if (req["base_url"]!=exe["base_url"]
            or req["executor_audience"]!=exe["executor_audience"]
            or req["api_key"]==exe["api_key"]):
        raise CredentialError("ROLE_CONFIGURATION_MISMATCH")
    try:
        url=urlsplit(req["base_url"])
        valid=(url.hostname and url.port is not None and not url.username
               and not url.password and url.path in ("","/")
               and not url.query and not url.fragment
               and (url.scheme=="https" or
                   (url.scheme=="http" and url.hostname in {"127.0.0.1","::1"})))
    except ValueError:
        valid=False
    if not valid:
        raise CredentialError("UNAPPROVED_HAA_ENDPOINT")
    # No environment proxy or redirect may forward role keys elsewhere.
    opener=build_opener(ProxyHandler({}),NoRedirect()).open
    return (HaaRequesterClient(RequesterConfig(**req),opener=opener),
            HaaExecutorClient(ExecutorConfig(**exe),opener=opener))
