import hashlib
import io
import os
import unittest
from unittest.mock import patch
from app import upload_storage as store

A = "00000000-0000-4000-8000-000000000001"
B = "00000000-0000-4000-8000-000000000002"
UPLOAD = "00000000-0000-4000-8000-000000000003"
DATA = b"Synthetic research source; no customer content."
ENV = {"NODE_ENV":"production", "PORTFOLIO_STORAGE_MODE":"s3", "PORTFOLIO_STORAGE_BUCKET":"portfolio-test-bucket"}


class FakeS3:
    def __init__(self): self.calls = []; self.data = None; self.corrupt = False; self.version = "version-1"
    def put_object(self, **args):
        self.calls.append(("put", args)); self.data = args
        return {"VersionId": self.version}
    def get_object(self, **args):
        self.calls.append(("get", args))
        return {"VersionId":self.version, "ContentLength":len(DATA), "ContentType":"text/plain",
                "Metadata":{"sha256":hashlib.sha256(DATA).hexdigest()},
                "Body":io.BytesIO(b"X" * len(DATA) if self.corrupt else DATA)}
    def close(self): pass


class StorageContract(unittest.TestCase):
    def test_real_contract_exact_version_readback_and_owner_prefix(self):
        fake = FakeS3()
        with patch.dict(os.environ, ENV, clear=True), patch.object(store,"_client",return_value=fake):
            ref = store.persist_upload(A, UPLOAD, "research.txt", DATA, "text/plain")
            self.assertEqual(store.hydrate_upload(A, ref), DATA)
        self.assertEqual([x[0] for x in fake.calls], ["put","get","get"])
        self.assertEqual(fake.calls[0][1]["ServerSideEncryption"], "AES256")
        self.assertEqual(fake.calls[1][1], {"Bucket":"portfolio-test-bucket", "Key":ref["key"], "VersionId":"version-1"})
        self.assertTrue(ref["key"].startswith(f"private/users/{A}/uploads/{UPLOAD}/"))
        self.assertNotIn("research.txt", ref["key"])

    def test_foreign_owner_and_tampered_reference_denied_before_io(self):
        fake = FakeS3()
        with patch.dict(os.environ, ENV, clear=True), patch.object(store,"_client",return_value=fake) as client:
            ref = store.persist_upload(A, UPLOAD, "research.txt", DATA, "text/plain")
            client.reset_mock()
            for owner, change in [(B,{}),(A,{"key":ref["key"]+"/other"}),(A,{"version_id":"null"}), (A,{"bytes":True}),(A,{"filename":"../secret"})]:
                with self.subTest(change=change), self.assertRaises(store.StorageError):
                    store.hydrate_upload(owner, {**ref,**change})
            client.assert_not_called()

    def test_failed_hash_or_unversioned_bucket_never_returns_ref(self):
        for bad in ("hash", "version"):
            fake = FakeS3()
            if bad == "hash": fake.corrupt = True
            else: fake.version = "null"
            with patch.dict(os.environ, ENV, clear=True), patch.object(store,"_client",return_value=fake):
                with self.assertRaises(store.StorageError): store.persist_upload(A, UPLOAD, "research.txt", DATA, "text/plain")

    def test_production_fixture_missing_bucket_and_absent_credentials_fail_closed(self):
        for env in ({"NODE_ENV":"production", "PORTFOLIO_STORAGE_MODE":"fixture"}, {}, {"PORTFOLIO_STORAGE_BUCKET":"portfolio-test-bucket"}):
            with patch.dict(os.environ, env, clear=True), self.assertRaises(store.StorageError):
                store.persist_upload(A, UPLOAD, "research.txt", DATA, "text/plain")

    def test_explicit_local_fixture_still_enforces_owner(self):
        with patch.dict(os.environ,{"PORTFOLIO_STORAGE_MODE":"fixture"},clear=True):
            ref = store.persist_upload(A, UPLOAD, "research.txt", DATA, "text/plain")
            self.assertEqual(store.hydrate_upload(A,ref), DATA)
            with self.assertRaises(store.StorageError): store.hydrate_upload(B,ref)

    def test_size_name_ids_and_safe_errors(self):
        fake = FakeS3()
        with patch.dict(os.environ, ENV, clear=True), patch.object(store,"_client",return_value=fake) as client:
            for args in [("invalid",UPLOAD,"x.txt",DATA,"text/plain"),(A,UPLOAD,"a/b",DATA,"text/plain"),(A,UPLOAD,"x.txt",b"","text/plain"),(A,UPLOAD,"x.txt",DATA,"text/plain\r\nSecret:value")]:
                with self.assertRaises(store.StorageError): store.persist_upload(*args)
            client.assert_not_called()
        with patch.dict(os.environ, ENV, clear=True), patch.object(store,"_client",side_effect=RuntimeError("sensitive")):
            with self.assertRaisesRegex(store.StorageError,"^upload_persistence_failed$"):
                store.persist_upload(A,UPLOAD,"x.txt",DATA,"text/plain")


if __name__ == "__main__": unittest.main()
