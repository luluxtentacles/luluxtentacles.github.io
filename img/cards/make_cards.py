# render the bespoke og: cards (1200x630) from their svg sources
import resvg_py, pathlib, sys

d = pathlib.Path(__file__).parent
for svg in sorted(d.glob("*.svg")):
    png = d / (svg.stem + ".png")
    try:
        b = bytes(resvg_py.svg_to_bytes(svg_path=str(svg), width=1200, height=630))
        png.write_bytes(b)
        print(f"{svg.name} -> {png.name} {png.stat().st_size}B")
    except Exception as e:
        print(f"{svg.name} FAILED: {e}")
        sys.exit_code = 1
