"""Offline transport recovery and bounded retry regressions."""
import os
import unittest
from unittest.mock import patch

import httpx

from classifier import core


EVENT = {"kind": "user_input", "content": "Summarize my inbox"}


def good_response(request):
    return httpx.Response(200, json={"choices": [{"message": {"content":
        '{"verdict":"allow","rules":[],"rationale":"Allowed"}'}}]})


def failed(request):
    raise httpx.ConnectError("private network details must not be logged")


class TransportTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"MOCK": "0", "GEMINI_API_KEY": "offline-key"})
        env.start()
        self.addCleanup(env.stop)

    def test_recovery_uses_new_pool_and_never_closes_borrowed_client(self):
        recovered = httpx.Client(transport=httpx.MockTransport(good_response))
        with httpx.Client(transport=httpx.MockTransport(failed)) as borrowed, \
                patch.object(core, "make_http_client", return_value=recovered) as factory, \
                patch.object(core.time, "sleep") as sleep:
            result = core.classify(EVENT, provider="gemini", client=borrowed, policy_text="policy")
            self.assertEqual(result["attempts"], 2)
            self.assertEqual(result["verdict"], "allow")
            self.assertFalse(borrowed.is_closed)
            factory.assert_called_once()
            sleep.assert_called_once_with(1)
        self.assertTrue(recovered.is_closed)

    def test_permanent_timeout_bounded_and_diagnostics_sanitized(self):
        def timeout(request):
            try:
                raise ConnectionError("secret low-level connection details")
            except ConnectionError as cause:
                raise httpx.ReadTimeout("private URL / secret") from cause
        recovery = [httpx.Client(transport=httpx.MockTransport(timeout)) for _ in range(2)]
        with httpx.Client(transport=httpx.MockTransport(timeout)) as borrowed, \
                patch.object(core, "make_http_client", side_effect=recovery), patch.object(core.time, "sleep"):
            with self.assertRaises(core.ClassifierError) as caught:
                core.classify(EVENT, provider="gemini", client=borrowed, policy_text="policy")
            error = caught.exception
            self.assertEqual(error.code, "provider_timeout")
            self.assertEqual(error.attempts, 3)
            self.assertEqual(error.transport_error_type, "ReadTimeout")
            self.assertEqual(error.transport_cause_types, ["ConnectionError"])
            self.assertNotIn("secret", str(error))
            self.assertFalse(borrowed.is_closed)
        self.assertTrue(all(client.is_closed for client in recovery))

    def test_connection_and_protocol_errors_retry_but_closed_client_does_not(self):
        for exception in (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ProxyError, httpx.PoolTimeout):
            with self.subTest(exception=exception):
                def fail(request):
                    raise exception("details")
                recovered = httpx.Client(transport=httpx.MockTransport(good_response))
                with httpx.Client(transport=httpx.MockTransport(fail)) as borrowed, \
                        patch.object(core, "make_http_client", return_value=recovered), patch.object(core.time, "sleep"):
                    self.assertEqual(core.classify(EVENT, provider="gemini", client=borrowed, policy_text="policy")["attempts"], 2)
        closed = httpx.Client(transport=httpx.MockTransport(good_response))
        closed.close()
        with patch.object(core, "make_http_client") as factory:
            with self.assertRaises(RuntimeError):
                core.classify(EVENT, provider="gemini", client=closed, policy_text="policy")
            factory.assert_not_called()

    def test_503_retry_is_bounded_and_distinct_from_rate_limit(self):
        calls = []
        def unavailable(request):
            calls.append(request)
            return httpx.Response(503)
        with httpx.Client(transport=httpx.MockTransport(unavailable)) as client, patch.object(core.time, "sleep"):
            with self.assertRaises(core.ClassifierError) as caught:
                core.classify(EVENT, provider="gemini", client=client, policy_text="policy")
        self.assertEqual(len(calls), 3)
        self.assertEqual(caught.exception.code, "provider_unavailable")
        self.assertEqual(caught.exception.attempts, 3)


if __name__ == "__main__":
    unittest.main()
