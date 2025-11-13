# dxf_parser.py
"""
DXFファイルを解析し、バラバラの図形をつなぎ合わせて、
1本の連続した輪郭線を構成する「頂点のリスト」を抽出することに専念します。
"""
import ezdxf
import math
from ezdxf.math import global_bspline_interpolation

def find_connected_path(segments, tolerance=1e-6):
    if not segments: return [], False
    path = [segments[0][0], segments[0][1]]
    remaining_segments = segments[1:]
    while remaining_segments:
        last_point = path[-1]
        found_next = False
        for i, seg in enumerate(remaining_segments):
            p1, p2 = seg[0], seg[1]
            if math.isclose(p1[0], last_point[0], abs_tol=tolerance) and math.isclose(p1[1], last_point[1], abs_tol=tolerance):
                path.append(p2); remaining_segments.pop(i); found_next = True; break
            elif math.isclose(p2[0], last_point[0], abs_tol=tolerance) and math.isclose(p2[1], last_point[1], abs_tol=tolerance):
                path.append(p1); remaining_segments.pop(i); found_next = True; break
        if not found_next: break
    first_point, last_point = path[0], path[-1]
    is_closed = math.isclose(first_point[0], last_point[0], abs_tol=tolerance) and math.isclose(first_point[1], last_point[1], abs_tol=tolerance)
    if is_closed:
        path.pop()
        print(f"連続した閉じたパスを再構築しました。頂点数: {len(path)}")
    else:
        print(f"連続した開いたパスを再構築しました。頂点数: {len(path)}")
    return path, is_closed

def get_all_entities_as_segments(filepath, curve_segments):
    try:
        doc = ezdxf.readfile(filepath); msp = doc.modelspace()
    except (IOError, ezdxf.DXFStructureError) as e:
        print(f"エラー: ファイル '{filepath}' の読み込みに失敗しました - {e}"); return None
    all_segments = []; query = 'LINE LWPOLYLINE POLYLINE ARC SPLINE'
    entities = msp.query(query)
    if not entities:
        print("エラー: DXFファイル内にサポートされている図形エンティティが見つかりません。"); return None
    print(f"ファイルから {len(entities)} 個の図形エンティティを検出しました。")
    for e in entities:
        if e.dxftype() == 'LINE':
            start, end = e.dxf.start, e.dxf.end; all_segments.append([(start.x, start.y), (end.x, end.y)])
        elif e.dxftype() in ('LWPOLYLINE', 'POLYLINE'):
            points = [(p[0], p[1]) for p in e.points()]
            for i in range(len(points) - 1): all_segments.append([points[i], points[i+1]])
            if e.is_closed: all_segments.append([points[-1], points[0]])
        elif e.dxftype() == 'ARC':
            arc_points = list(e.flattening(distance=e.radius / curve_segments))
            for i in range(len(arc_points) - 1): all_segments.append([(arc_points[i].x, arc_points[i].y), (arc_points[i+1].x, arc_points[i+1].y)])
        elif e.dxftype() == 'SPLINE':
            if hasattr(e, 'fit_points') and e.fit_points:
                from ezdxf.math import BSpline
                spline = BSpline.through_points(e.fit_points, degree=e.dxf.degree)
                points = spline.approximate(segments=curve_segments * len(e.fit_points))
            else:
                points = e.approximate(segments=curve_segments * e.dxf.n_control_points)
            spline_points = list(points)
            for i in range(len(spline_points) - 1): all_segments.append([(spline_points[i].x, spline_points[i].y), (spline_points[i+1].x, spline_points[i+1].y)])
    print(f"すべての図形を {len(all_segments)} 個の線分セグメントに分解しました。")
    return all_segments