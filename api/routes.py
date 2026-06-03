from pathlib import Path


def list_files(output_dir: str) -> list[dict[str, int | str]]:
    root = Path(output_dir).resolve()
    if not root.exists():
        return []

    files: list[dict[str, int | str]] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files.append(
                {
                    "path": str(Path("output") / path.relative_to(root)).replace("\\", "/"),
                    "size": path.stat().st_size,
                }
            )
    return files


def resolve_output_file(requested_path: str, output_dir: str) -> Path:
    root = Path(output_dir).resolve()
    raw_path = Path(requested_path)
    if raw_path.parts and raw_path.parts[0] == "output":
        raw_path = Path(*raw_path.parts[1:]) if len(raw_path.parts) > 1 else Path()

    candidate = (root / raw_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise PermissionError("Requested path is outside the output directory")
    if not candidate.is_file():
        raise FileNotFoundError(f"File not found: {requested_path}")
    return candidate
