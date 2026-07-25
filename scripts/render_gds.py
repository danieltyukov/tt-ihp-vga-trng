# KLayout batch script: render a GDS to PNG, optionally zoomed to a box.
#
# klayout -b does not pass positional argv to the script, so parameters arrive as
# -rd name=value and land here as plain globals. Called by scripts/harden.sh:
#
#   klayout -b -rm scripts/render_gds.py -rd gds=... -rd out=... -rd w=... -rd h=...
#   klayout -b -rm scripts/render_gds.py -rd gds=... -rd out=... -rd w=... -rd h=... \
#           -rd box=70,100,95,125
#
# box is x1,y1,x2,y2 in micrometres. Without it the view is zoom_fit, the whole
# die. A full die view of a routed tile is close to unreadable on its own, because
# every metal layer overlaps at that scale, so the useful figure is a pair: the
# full die for the outline, pin frame and power rails, and a zoomed box where
# individual sg13g2 cells and the routing between them are distinguishable.

import pya

lv = pya.LayoutView()
lv.load_layout(gds, 0)  # noqa: F821  from -rd gds=
lv.max_hier()

try:
    spec = box  # noqa: F821  from -rd box=
except NameError:
    spec = None

if spec:
    x1, y1, x2, y2 = (float(v) for v in str(spec).split(","))
    lv.zoom_box(pya.DBox(x1, y1, x2, y2))
    where = "box %g,%g to %g,%g um" % (x1, y1, x2, y2)
else:
    lv.zoom_fit()
    where = "full die"

lv.save_image(out, int(w), int(h))  # noqa: F821  from -rd out= -rd w= -rd h=
print("wrote %s at %sx%s, %s" % (out, w, h, where))  # noqa: F821
