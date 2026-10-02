"""Installation-bound, compare-and-swap ownership journal in Object Storage."""
import json
import re

import oci

from .oci_clients import client

OBJECT = "zpr-visibility/ownership.json"


def validate_installation(value):
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,39}", value or ""):
        raise ValueError("installation ID must be 3-40 lowercase letters, digits or hyphens")
    return value


class Ownership:
    def __init__(self, session, bucket, installation, compartment):
        validate_installation(installation)
        self.os = client(session, "object_storage.ObjectStorageClient")
        self.ns = self.os.get_namespace().data
        self.bucket = bucket
        self.target = {"installation": installation, "tenancy": session.tenancy_id,
                       "region": session.region, "compartment": compartment}
        owned_bucket = self.os.get_bucket(self.ns, bucket).data
        if owned_bucket.compartment_id != compartment:
            raise ValueError("state bucket compartment mismatch")
        if (owned_bucket.freeform_tags or {}).get("zpr-installation") != installation:
            raise ValueError("state bucket ownership tag mismatch")
        self.etag = None
        try:
            response = self.os.get_object(self.ns, bucket, OBJECT)
            self.data = json.loads(response.data.content)
            self.etag = response.headers["etag"]
        except oci.exceptions.ServiceError as exc:
            if exc.status != 404 or exc.code != "ObjectNotFound":
                raise
            self.data = {"version": 1, "target": self.target, "resources": {}}
        if self.data.get("version") != 1 or self.data.get("target") != self.target:
            raise ValueError("ownership journal target mismatch")

    @property
    def installation(self):
        return self.target["installation"]

    def save(self):
        kwargs = {"if_match": self.etag} if self.etag else {"if_none_match": "*"}
        response = self.os.put_object(self.ns, self.bucket, OBJECT,
            json.dumps(self.data, sort_keys=True).encode(), content_type="application/json", **kwargs)
        self.etag = response.headers["etag"]

    def record(self, kind, name, identity, *, created, revision=None):
        key = f"{kind}:{name}"
        previous = self.data["resources"].get(key)
        if previous and previous["identity"] not in (None, identity):
            raise ValueError("owned resource identity changed")
        self.data["resources"][key] = {"kind": kind, "name": name,
            "identity": identity, "created": previous["created"] if previous else created,
            "revision": revision, "deleted": False}
        self.save()

    def get(self, kind, name):
        return self.data["resources"].get(f"{kind}:{name}")
