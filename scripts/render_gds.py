# KLayout batch script: render a GDS to PNG.
#
# klayout -b does not pass positional argv to the script, so parameters arrive as
# -rd name=value, which become plain globals here. Called by scripts/harden.sh:
#
#   klayout -b -rm scripts/render_gds.py -rd gds=... -rd out=... -rd w=... -rd h=...

import pya

lv = pya.LayoutView()
lv.load_layout(gds, 0)  # noqa: F821  gds comes from -rd
lv.max_hier()
lv.zoom_fit()
lv.save_image(out, int(w), int(h))  # noqa: F821  out, w, h come from -rd
print("wrote %s at %sx%s" % (out, w, h))  # noqa: F821
