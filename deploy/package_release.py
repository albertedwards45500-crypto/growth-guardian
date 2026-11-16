"""Create a minimal Linux release archive without local credentials or user data."""

from pathlib import Path
import tarfile


ROOT = Path(__file__).resolve().parents[1]


def main():
    if not (ROOT / "frontend/dist/index.html").is_file():
        raise SystemExit("Run npm run build in frontend first")
    output = ROOT / "output/deploy/growth-guardian-release.tar.gz"
    output.parent.mkdir(parents=True, exist_ok=True)
    includes = [
        "docker-compose.yml", "backend/Dockerfile", "backend/.dockerignore",
        "backend/requirements.txt", "backend/alembic.ini", "backend/app",
        "backend/migrations", "frontend/Dockerfile", "frontend/.dockerignore",
        "frontend/nginx.conf", "frontend/dist", "deploy",
    ]
    paths = set()
    for relative in includes:
        source = ROOT / relative
        paths.update(source.rglob("*") if source.is_dir() else [source])
    count = 0
    with tarfile.open(output, "w:gz") as archive:
        for source in sorted(paths):
            if not source.is_file():
                continue
            relative = source.relative_to(ROOT)
            if (source.is_symlink() or "__pycache__" in relative.parts
                    or source.suffix in {".pyc", ".pyo"}
                    or (source.name.startswith(".env") and source.name != ".env.example")):
                continue
            info = archive.gettarinfo(str(source), arcname=relative.as_posix())
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o755 if source.suffix == ".sh" else 0o644
            with source.open("rb") as stream:
                archive.addfile(info, stream)
            count += 1
    print(f"Created {output}: {count} files, {output.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
