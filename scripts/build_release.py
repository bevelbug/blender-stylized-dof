"""Build the Blender installer from this repository with Python 3.11+."""
import argparse
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import tomllib


def main():
    root = Path(__file__).resolve().parents[1]
    package = root / "stylized_depth_of_field"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", default="blender", help="Blender executable or full path")
    parser.add_argument("--output-dir", type=Path, default=root / "dist")
    args = parser.parse_args()
    blender = shutil.which(args.blender)
    if blender is None:
        parser.error("Blender was not found. Pass its executable path with --blender.")
    manifest = tomllib.loads((package / "blender_manifest.toml").read_text(encoding="utf-8"))
    output = args.output_dir.resolve() / f"Stylized_Depth_of_Field_v{manifest['version']}.zip"
    if output.exists():
        parser.error(f"{output} already exists. Choose a fresh output directory.")
    output.parent.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(prefix="sdof-build-", dir=output.parent) as temporary:
        staging = Path(temporary) / package.name
        shutil.copytree(package, staging, ignore=shutil.ignore_patterns(
            "tests", "__pycache__", "*.pyc", "*.pyo", "*.blend[0-9]*"
        ))
        for filename in ("README.md", "GUIDE.md", "CHANGELOG.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
            shutil.copy2(root / filename, staging / filename)
        (staging / "docs").mkdir()
        for filename in ("validation.md", "test-results.json"):
            shutil.copy2(root / "docs" / filename, staging / "docs" / filename)
        prefix = [blender, "--background", "--factory-startup", "--command", "extension"]
        subprocess.run([*prefix, "build", "--source-dir", str(staging),
                        "--output-filepath", str(output)], check=True)
        subprocess.run([*prefix, "validate", str(output)], check=True)
    print(output)


if __name__ == "__main__":
    main()
