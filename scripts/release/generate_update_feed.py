from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate DeepGen update feed JSON")
    parser.add_argument("--version", required=True)
    parser.add_argument("--download-url", required=True)
    parser.add_argument("--channel", default="test")
    parser.add_argument("--notes", default="Internal beta update")
    parser.add_argument("--output", default="releases/test/appcast.json")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "channel": args.channel,
        "latest": {
            "version": args.version,
            "download_url": args.download_url,
            "notes": args.notes,
        },
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote update feed: {output_path}")


if __name__ == "__main__":
    main()
