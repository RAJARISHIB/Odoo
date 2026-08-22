"""Shared test helpers - see apps/users/tests.py for the security suite.

These hit real URLs through Django's test client rather than calling service
functions directly, so a test exercises the same middleware / decorator /
controller stack a real request does - the thing actually being verified is
"does the HTTP endpoint enforce this", not "does the Python function".
"""
import json

from django.test import Client, SimpleTestCase


class ApiTestCase(SimpleTestCase):
    """Base class for endpoint-level tests.

    Safety: `apps/users/tests.py` refuses to run unless `MONGO_DB_NAME` is
    clearly a disposable test database - these tests create and delete real
    documents and must never touch a database with real data in it.
    """

    def setUp(self):
        super().setUp()
        self.client = Client()

    def post_json(self, path, data=None, **extra):
        return self.client.post(
            path, data=json.dumps(data or {}), content_type="application/json", **extra
        )

    def get_json(self, path, **extra):
        return self.client.get(path, **extra)

    def patch_json(self, path, data=None, **extra):
        return self.client.patch(
            path, data=json.dumps(data or {}), content_type="application/json", **extra
        )

    def put_json(self, path, data=None, **extra):
        return self.client.put(
            path, data=json.dumps(data or {}), content_type="application/json", **extra
        )

    def delete_json(self, path, **extra):
        return self.client.delete(path, **extra)

    @staticmethod
    def auth_header(access_token: str) -> dict:
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(access_token)}

    @staticmethod
    def body(response) -> dict:
        return json.loads(response.content.decode("utf-8"))
