# dxf_parser.py
import ezdxf
import math
import numpy as np


def _are_points_close(p1, p2, tol=1e-4):
    return math.isclose(p1[0], p2[0], abs_tol=tol) and math.isclose(p1[1], p2[1], abs_tol=tol)


def _remove_duplicate_segments(segments, tol=1e-4):
    """
    重複した線分を削除する。
    """
    unique_segments = []
    seen = []

    for seg in segments:
        p1, p2 = seg[0], seg[1]

        # 長さがほぼゼロのゴミ線分は除去
        if _are_points_close(p1, p2, tol):
            continue

        # 座標を正規化して比較（始点と終点をソート）
        sorted_seg = sorted([p1, p2], key=lambda p: (p[0], p[1]))

        # 既存リストに似たものがあるかチェック
        is_duplicate = False
        for s_seen in seen:
            if _are_points_close(sorted_seg[0], s_seen[0], tol) and \
                    _are_points_close(sorted_seg[1], s_seen[1], tol):
                is_duplicate = True
                break

        if not is_duplicate:
            seen.append(sorted_seg)
            unique_segments.append(seg)

    print(f"重複削除: {len(segments)} -> {len(unique_segments)} 本")
    return unique_segments


def find_all_connected_paths(segments, tolerance=1e-3):
    """
    バラバラの線分リストから、接続された複数のパス（頂点リストのリスト）を生成する。
    """
    # 1. 重複削除
    clean_segments = _remove_duplicate_segments(segments, tolerance)

    paths = []
    pool = clean_segments.copy()  # 未処理の線分プール

    while pool:
        # 新しいパスを開始
        current_path_segments = [pool.pop(0)]

        # --- 前方への探索 ---
        while True:
            last_pt = current_path_segments[-1][1]
            found_next = None

            for i, seg in enumerate(pool):
                p1, p2 = seg[0], seg[1]
                if _are_points_close(last_pt, p1, tolerance):
                    found_next = (i, p2, False)  # そのまま接続
                    break
                elif _are_points_close(last_pt, p2, tolerance):
                    found_next = (i, p1, True)  # 反転して接続
                    break

            if found_next:
                idx, next_pt, flip = found_next
                seg = pool.pop(idx)
                if flip:
                    current_path_segments.append((seg[1], seg[0]))  # 反転
                else:
                    current_path_segments.append(seg)
            else:
                break  # 行き止まり、または閉じた

        # --- 後方への探索 (閉じていない場合) ---
        first_pt = current_path_segments[0][0]
        end_pt = current_path_segments[-1][1]

        if not _are_points_close(first_pt, end_pt, tolerance):
            while True:
                first_pt = current_path_segments[0][0]
                found_prev = None

                for i, seg in enumerate(pool):
                    p1, p2 = seg[0], seg[1]
                    if _are_points_close(first_pt, p2, tolerance):
                        found_prev = (i, p1, False)  # そのまま接続 (p1->p2) -> p2が今の始点
                        break
                    elif _are_points_close(first_pt, p1, tolerance):
                        found_prev = (i, p2, True)  # 反転して接続 (p2->p1) -> p1が今の始点
                        break

                if found_prev:
                    idx, prev_start, flip = found_prev
                    seg = pool.pop(idx)
                    if flip:
                        current_path_segments.insert(0, (seg[1], seg[0]))
                    else:
                        current_path_segments.insert(0, seg)
                else:
                    break

        # 線分リストを頂点リストに変換
        if not current_path_segments:
            continue

        vertices = [current_path_segments[0][0]]
        for seg in current_path_segments:
            vertices.append(seg[1])

        paths.append(vertices)

    print(f"解析完了: {len(paths)} 個の独立したパスを検出しました。")
    return paths


def get_all_entities_as_segments(filepath, curve_segments):
    """
    DXFから全エンティティを読み込み、線分化して返す
    """
    try:
        doc = ezdxf.readfile(filepath)
        msp = doc.modelspace()
    except Exception as e:
        print(f"DXF Read Error: {e}")
        return []

    all_segments = []
    # ★ CIRCLE を追加
    entities = msp.query('LINE LWPOLYLINE POLYLINE ARC SPLINE CIRCLE')

    for e in entities:
        if e.dxftype() == 'LINE':
            all_segments.append([(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)])

        elif e.dxftype() in ('LWPOLYLINE', 'POLYLINE'):
            pts = list(e.points())
            points_xy = [(p[0], p[1]) for p in pts]
            for i in range(len(points_xy) - 1):
                all_segments.append([points_xy[i], points_xy[i + 1]])
            if e.is_closed:
                all_segments.append([points_xy[-1], points_xy[0]])

        elif e.dxftype() == 'ARC':
            try:
                for p1, p2 in e.flattening(distance=e.radius / curve_segments):
                    all_segments.append([(p1.x, p1.y), (p2.x, p2.y)])
            except:
                pass

        elif e.dxftype() == 'SPLINE':
            try:
                points = list(e.flattening(distance=1.0))
                for i in range(len(points) - 1):
                    all_segments.append([(points[i].x, points[i].y), (points[i + 1].x, points[i + 1].y)])
            except:
                pass

        # ★ CIRCLE対応を追加
        elif e.dxftype() == 'CIRCLE':
            center = e.dxf.center
            radius = e.dxf.radius
            # 分割数: 設定値を使うが、円として荒くなりすぎないよう最低36分割(10度ごと)は確保
            n = max(36, int(curve_segments * 2)) if curve_segments else 36

            circle_pts = []
            for i in range(n):
                angle = 2 * math.pi * i / n
                px = center.x + radius * math.cos(angle)
                py = center.y + radius * math.sin(angle)
                circle_pts.append((px, py))

            # 線分化（閉じる）
            for i in range(n):
                p1 = circle_pts[i]
                p2 = circle_pts[(i + 1) % n]
                all_segments.append([p1, p2])

    return all_segments