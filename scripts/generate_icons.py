#!/usr/bin/env python3
"""Package the supplied fox into app icons without replacing the original asset."""
import json
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parents[1]
output = root / "native/Coral/Assets.xcassets/AppIcon.appiconset"
output.mkdir(parents=True, exist_ok=True)
source = Image.open(root / "assets/mascot.png").convert("RGB")
square = Image.new("RGB", (1024, 1024), "#FFF7EB")
source.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
square.paste(source, ((1024 - source.width) // 2, (1024 - source.height) // 2))
entries = [{"idiom": "universal", "platform": "ios", "size": "1024x1024", "filename": "icon-1024.png"}]
square.save(output / "icon-1024.png")
for size in [16, 32, 128, 256, 512]:
    for scale in [1, 2]:
        pixels = size * scale
        name = f"mac-{size}@{scale}x.png"
        square.resize((pixels, pixels), Image.Resampling.LANCZOS).save(output / name)
        entries.append({"idiom": "mac", "size": f"{size}x{size}", "scale": f"{scale}x", "filename": name})
(output / "Contents.json").write_text(json.dumps({"images": entries, "info": {"author": "xcode", "version": 1}}, indent=2))
print(output)
