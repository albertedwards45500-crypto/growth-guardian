"""Verify public frontend, SPA fallback, API, authentication and database reads."""

import argparse
import json
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origin")
    parser.add_argument("--demo-login", action="store_true", help="Also verify the existing shared demo account")
    args = parser.parse_args()
    origin = args.origin.rstrip("/")

    def request(path, payload=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(origin + path, headers=headers,
                                     data=json.dumps(payload).encode() if payload is not None else None)
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, response.read().decode()

    for path in ("/", "/login", "/advisor"):
        status, body = request(path)
        assert status == 200 and '<div id="app">' in body, f"Frontend failed: {path}"
        print(f"PASS frontend {path}")
    _, body = request("/health")
    assert json.loads(body)["status"] == "ok", "Health check failed"
    print("PASS backend health")
    _, body = request("/api/v1/users/me")
    assert json.loads(body)["code"] == 40100, "Authentication guard failed"
    print("PASS authentication guard")
    for path in ("/docs", "/openapi.json", "/static/test-runner.html"):
        try:
            request(path)
        except urllib.error.HTTPError as error:
            assert error.code == 404, f"Unexpected status for {path}: {error.code}"
        else:
            raise AssertionError(f"Debug page exposed: {path}")
    print("PASS debug pages hidden")
    if args.demo_login:
        _, body = request("/api/v1/auth/login", {"phone": "13800000000", "password": "123456"})
        login = json.loads(body)
        assert login["code"] == 0, "Demo login failed"
        token = login["data"]["access_token"]
        for path in ("/api/v1/users/me", "/api/v1/babies", "/api/v1/recipes"):
            _, body = request(path, token=token)
            assert json.loads(body)["code"] == 0, f"Database read failed: {path}"
        print("PASS demo login and database reads (no token printed)")


if __name__ == "__main__":
    main()
