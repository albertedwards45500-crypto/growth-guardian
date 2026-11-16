"""Generate fresh production credentials on the deployment host, once."""

import argparse
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origin", help="Public URL, e.g. http://203.0.113.10")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / ".env")
    args = parser.parse_args()
    parsed = urlsplit(args.origin)
    if (parsed.scheme != "http" or not parsed.hostname
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            or parsed.username or parsed.password or "\n" in args.origin or "\r" in args.origin):
        parser.error("origin must be an http origin without credentials, path, query or fragment; TLS needs a separate reverse proxy")
    if args.output.exists():
        parser.error(f"Refusing to overwrite existing configuration: {args.output}")
    body = "\n".join([
        f"PUBLIC_ORIGIN={args.origin.rstrip('/')}",
        "HTTP_BIND=0.0.0.0",
        f"HTTP_PORT={parsed.port or 80}",
        f"MYSQL_PASSWORD={secrets.token_hex(24)}",
        f"MYSQL_ROOT_PASSWORD={secrets.token_hex(32)}",
        f"SECRET_KEY={secrets.token_hex(48)}",
        "",
    ])
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(body)
    print(f"Created {args.output}; credentials were not printed. Keep this file backed up privately.")


if __name__ == "__main__":
    main()
