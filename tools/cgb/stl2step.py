"""Faceted STEP from a closed STL: one planar face per triangle, sewn into a solid."""
import sys
from OCP.StlAPI import StlAPI_Reader
from OCP.TopoDS import TopoDS_Shape, TopoDS
from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid
from OCP.ShapeFix import ShapeFix_Solid
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.TopAbs import TopAbs_SHELL
from OCP.TopExp import TopExp_Explorer

src, dst = sys.argv[1], sys.argv[2]
mesh = TopoDS_Shape()
StlAPI_Reader().Read(mesh, src)
sew = BRepBuilderAPI_Sewing(1e-4); sew.Add(mesh); sew.Perform()
ex = TopExp_Explorer(sew.SewedShape(), TopAbs_SHELL)
mk = BRepBuilderAPI_MakeSolid()
while ex.More():
    mk.Add(TopoDS.Shell(ex.Current())); ex.Next()
fix = ShapeFix_Solid(mk.Solid()); fix.Perform()
u = ShapeUpgrade_UnifySameDomain(fix.Solid(), True, True, True); u.Build()  # merge coplanar triangles
w = STEPControl_Writer(); w.Transfer(u.Shape(), STEPControl_AsIs)
sys.exit(0 if w.Write(dst) == 1 else 1)
