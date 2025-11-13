#20250906 DXFtoCSV.py
#dxfファイルをcsvに変換する
#csvに線分以外のものがあるとエラー

import ezdxf
import math
import matplotlib.pyplot as plt
import csv  # ★ CSVライブラリをインポート

# --------------------------------------------------------------------------
# ユーザー設定パラメータ
# --------------------------------------------------------------------------
# 解析するDXFファイルのパス
DXF_FILE_PATH = 'your_shape.dxf'

# 溶着ヘッドの寸法 (mm)
HEAD_WIDTH = 40.0
HEAD_HEIGHT = 3.0

# 溶着の重ね代 (mm)
OVERLAP = 1.0

# 円弧やスプラインを線分に変換する際の分割数
CURVE_SEGMENTS = 20


# --------------------------------------------------------------------------

def is_point_on_segment(point, p1, p2, tolerance=1e-9):
    """点が線分 p1-p2 の上に乗っているかを判定する"""
    px, py = point
    x1, y1 = p1
    x2, y2 = p2

    # 点が線分のバウンディングボックス内にあるかチェック
    on_bbox = (min(x1, x2) - tolerance <= px <= max(x1, x2) + tolerance and
               min(y1, y2) - tolerance <= py <= max(y1, y2) + tolerance)
    if not on_bbox:
        return False

    # 3点が同一直線上にあるかチェック (クロス積を利用)
    cross_product = (py - y1) * (x2 - x1) - (px - x1) * (y2 - y1)

    return abs(cross_product) < tolerance


def is_point_inside_polygon(point, polygon_vertices):
    """
    点がポリゴンの内側にあるかを判定する。
    【改訂】最初に輪郭線上にあるかをチェックし、線上にある場合は「外側」と判定する。
    """
    # ステップ1: ポイントが輪郭のいずれかの線分上に存在するかチェック
    for i in range(len(polygon_vertices)):
        p1 = polygon_vertices[i]
        p2 = polygon_vertices[(i + 1) % len(polygon_vertices)]
        if is_point_on_segment(point, p1, p2):
            return False  # 線上にある場合は「外側」とする

    # ステップ2: 線上にない場合のみ、レイキャスト法で内外判定
    x, y = point
    n = len(polygon_vertices)
    inside = False
    p1x, p1y = polygon_vertices[0]
    for i in range(n + 1):
        p2x, p2y = polygon_vertices[i % n]
        if y > min(p1y, p2y) and y <= max(p1y, p2y) and x <= max(p1x, p2x):
            if p1y != p2y:
                xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
            if p1x == p2x or x <= xinters:
                inside = not inside
        p1x, p1y = p2x, p2y
    return inside


# --- 以下のコードは変更ありません ---

def get_weld_endpoints(center_x, center_y, angle_deg, width):
    angle_rad = math.radians(angle_deg)
    dx = (width / 2) * math.cos(angle_rad)
    dy = (width / 2) * math.sin(angle_rad)
    end1 = (center_x + dx, center_y + dy)
    end2 = (center_x - dx, center_y - dy)
    return end1, end2


def get_rectangle_corners(center_x, center_y, angle_deg, width, height):
    angle_rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
    w2, h2 = width / 2, height / 2
    corners_relative = [(-w2, -h2), (w2, -h2), (w2, h2), (-w2, h2)]
    rotated_corners = []
    for x_rel, y_rel in corners_relative:
        x_rot = x_rel * cos_a - y_rel * sin_a
        y_rot = x_rel * sin_a + y_rel * cos_a
        rotated_corners.append((x_rot + center_x, y_rot + center_y))
    return rotated_corners


def run_diagnostics_and_plot(vertices, is_closed):
    if not vertices or len(vertices) < 2:
        print("頂点データが不足しているため、処理を中断しました。")
        return

    all_head_data = []
    step_distance = HEAD_WIDTH - OVERLAP
    num_segments = len(vertices) if is_closed else len(vertices) - 1

    for i in range(num_segments):
        p1, p2 = vertices[i], vertices[(i + 1) % len(vertices)]
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        segment_length = math.sqrt(dx ** 2 + dy ** 2)
        if segment_length < 1e-6: continue

        num_welds = math.ceil(segment_length / step_distance) if step_distance > 0 else 1
        if num_welds == 0: num_welds = 1
        actual_step = segment_length / num_welds
        angle_deg = math.degrees(math.atan2(dy, dx))

        for j in range(num_welds):
            dist = actual_step * (j + 0.5)
            center_x = p1[0] + (dx / segment_length) * dist
            center_y = p1[1] + (dy / segment_length) * dist

            # --- ステップ1: 初期位置での内外判定 ---
            end1, end2 = get_weld_endpoints(center_x, center_y, angle_deg, HEAD_WIDTH)
            e1_inside = is_point_inside_polygon(end1, vertices)
            e2_inside = is_point_inside_polygon(end2, vertices)

            # --- ステップ2: 内側にある場合、外に出るまで繰り返し位置を補正 ---
            if e1_inside or e2_inside:
                shift_step = 0.5
                angle_rad = math.radians(angle_deg)
                dx_shift_base = shift_step * math.cos(angle_rad)
                dy_shift_base = shift_step * math.sin(angle_rad)

                if e2_inside:
                    dx_shift = dx_shift_base
                    dy_shift = dy_shift_base
                else:
                    dx_shift = -dx_shift_base
                    dy_shift = -dy_shift_base

                max_iterations = 200
                iteration_count = 0

                while (e1_inside or e2_inside) and iteration_count < max_iterations:
                    center_x += dx_shift
                    center_y += dy_shift

                    end1, end2 = get_weld_endpoints(center_x, center_y, angle_deg, HEAD_WIDTH)
                    e1_inside = is_point_inside_polygon(end1, vertices)
                    e2_inside = is_point_inside_polygon(end2, vertices)

                    iteration_count += 1

                if iteration_count >= max_iterations:
                    print(
                        f"警告: ヘッド位置の自動調整が最大試行回数({max_iterations}回)に達しました。@ center({center_x:.1f}, {center_y:.1f})")

            head_corners = get_rectangle_corners(center_x, center_y, angle_deg, HEAD_WIDTH, HEAD_HEIGHT)

            all_head_data.append({
                'center': (center_x, center_y), 'angle_deg': angle_deg, 'corners': head_corners,
                'end1': end1, 'end2': end2, 'e1_inside': e1_inside, 'e2_inside': e2_inside,
            })

    fig, ax = plt.subplots(figsize=(12, 10))
    ax.set_aspect('equal', adjustable='box')
    ax.set_title('Welding Head Placement Diagnostics (With Iterative Correction)')
    ax.set_xlabel('X coordinate (mm)'), ax.set_ylabel('Y coordinate (mm)')
    ax.grid(True, linestyle='--', alpha=0.6)

    poly_x = [v[0] for v in vertices] + [vertices[0][0]]
    poly_y = [v[1] for v in vertices] + [vertices[0][1]]
    ax.plot(poly_x, poly_y, 'k-', label='DXF Outline', linewidth=1.5, zorder=1)

    for head in all_head_data:
        corners_x = [c[0] for c in head['corners']] + [head['corners'][0][0]]
        corners_y = [c[1] for c in head['corners']] + [head['corners'][0][1]]

        ax.scatter(head['center'][0], head['center'][1], c='red', s=10, zorder=4)

        head_color = 'green'
        if head['e1_inside'] or head['e2_inside']:
            head_color = 'orange'
            ax.plot(corners_x, corners_y, color=head_color, linestyle='-', linewidth=0.8, alpha=0.7, zorder=2)
        else:
            ax.plot(corners_x, corners_y, color=head_color, linestyle='-', linewidth=0.5, alpha=0.5, zorder=2)

        if head['e1_inside']:
            ax.scatter(head['end1'][0], head['end1'][1], c='red', s=20, marker='x', zorder=5)
        else:
            ax.scatter(head['end1'][0], head['end1'][1], c='blue', s=10, marker='o', alpha=0.7, zorder=3)

        if head['e2_inside']:
            ax.scatter(head['end2'][0], head['end2'][1], c='red', s=20, marker='x', zorder=5)
        else:
            ax.scatter(head['end2'][0], head['end2'][1], c='blue', s=10, marker='o', alpha=0.7, zorder=3)

    from matplotlib.lines import Line2D
    custom_lines = [
        Line2D([0], [0], color='k', lw=1.5, label='DXF Outline'),
        Line2D([0], [0], color='orange', lw=0.8, label='Head (Endpoint Inside)'),
        Line2D([0], [0], color='green', lw=0.5, label='Head (All Endpoints Outside)'),
        Line2D([0], [0], marker='.', color='red', markersize=8, linestyle='None', label='Weld Center'),
        Line2D([0], [0], marker='x', color='red', markersize=10, linestyle='None', label='Endpoint (INSIDE!)'),
        Line2D([0], [0], marker='o', color='blue', markersize=8, linestyle='None', label='Endpoint (Outside)'),
    ]
    ax.legend(handles=custom_lines, loc='center left', bbox_to_anchor=(1, 0.5))
    fig.tight_layout()

    # ----------------------------------------------------
    # ▼▼▼ CSV出力ブロック START ▼▼▼
    # ----------------------------------------------------
    csv_file_path = 'weld_points.csv'
    try:
        with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['center_x', 'center_y', 'angle_deg']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()

            for head in all_head_data:
                writer.writerow({
                    'center_x': f"{head['center'][0]:.4f}",
                    'center_y': f"{head['center'][1]:.4f}",
                    'angle_deg': f"{head['angle_deg']:.4f}"
                })
        print(f"溶着ヘッドの座標と角度を '{csv_file_path}' に保存しました。")
    except IOError as e:
        print(f"エラー: CSVファイル '{csv_file_path}' の書き込みに失敗しました - {e}")
    # ----------------------------------------------------
    # ▲▲▲ CSV出力ブロック END ▲▲▲
    # ----------------------------------------------------

    plt.show()


def main():
    all_segments = get_all_entities_as_segments(DXF_FILE_PATH, CURVE_SEGMENTS)
    if all_segments:
        vertices, is_closed = find_connected_path(all_segments)
        if vertices:
            run_diagnostics_and_plot(vertices, is_closed)


def find_connected_path(segments, tolerance=1e-6):
    if not segments: return [], False
    path = [segments[0][0], segments[0][1]];
    remaining_segments = segments[1:]
    while remaining_segments:
        last_point = path[-1];
        found_next = False
        for i, seg in enumerate(remaining_segments):
            p1, p2 = seg[0], seg[1]
            if math.isclose(p1[0], last_point[0], abs_tol=tolerance) and math.isclose(p1[1], last_point[1],
                                                                                      abs_tol=tolerance):
                path.append(p2);
                remaining_segments.pop(i);
                found_next = True;
                break
            elif math.isclose(p2[0], last_point[0], abs_tol=tolerance) and math.isclose(p2[1], last_point[1],
                                                                                        abs_tol=tolerance):
                path.append(p1);
                remaining_segments.pop(i);
                found_next = True;
                break
        if not found_next: break
    first_point, last_point = path[0], path[-1]
    is_closed = math.isclose(first_point[0], last_point[0], abs_tol=tolerance) and math.isclose(first_point[1],
                                                                                                last_point[1],
                                                                                                abs_tol=tolerance)
    if is_closed:
        path.pop();
        print(f"連続した閉じたパスを再構築しました。頂点数: {len(path)}")
    else:
        print(f"連続した開いたパスを再構築しました。頂点数: {len(path)}")
    return path, is_closed


def get_all_entities_as_segments(filepath, curve_segments):
    try:
        doc = ezdxf.readfile(filepath);
        msp = doc.modelspace()
    except (IOError, ezdxf.DXFStructureError) as e:
        print(f"エラー: ファイル '{filepath}' の読み込みに失敗しました - {e}");
        return None
    all_segments = [];
    query = 'LINE LWPOLYLINE POLYLINE ARC SPLINE'
    entities = msp.query(query)
    if not entities: print(f"エラー: DXFファイル内にサポートされている図形エンティティが見つかりません。"); return None
    print(f"ファイルから {len(entities)} 個の図形エンティティを検出しました。")
    for e in entities:
        if e.dxftype() == 'LINE':
            start, end = e.dxf.start, e.dxf.end;
            all_segments.append([(start.x, start.y), (end.x, end.y)])
        elif e.dxftype() in ('LWPOLYLINE', 'POLYLINE'):
            points = [(p[0], p[1]) for p in e.points()];
            for i in range(len(points) - 1): all_segments.append([points[i], points[i + 1]])
            if e.is_closed: all_segments.append([points[-1], points[0]])
        elif e.dxftype() == 'ARC':
            arc_points = list(e.flattening(distance=e.radius / curve_segments));
            for i in range(len(arc_points) - 1): all_segments.append(
                [(arc_points[i].x, arc_points[i].y), (arc_points[i + 1].x, arc_points[i + 1].y)])
        elif e.dxftype() == 'SPLINE':
            if hasattr(e, 'fit_points') and e.fit_points:
                from ezdxf.math import BSpline
                spline = BSpline.through_points(e.fit_points, degree=e.dxf.degree)
                points = spline.approximate(segments=curve_segments * len(e.fit_points))
            else:
                points = e.approximate(segments=curve_segments * e.dxf.n_control_points)
            spline_points = list(points)
            for i in range(len(spline_points) - 1): all_segments.append(
                [(spline_points[i].x, spline_points[i].y), (spline_points[i + 1].x, spline_points[i + 1].y)])
    print(f"すべての図形を {len(all_segments)} 個の線分セグメントに分解しました。")
    return all_segments


if __name__ == "__main__":
    main()