# path_generator.py
import numpy as np
import config


def _generate_points_for_single_loop(vertices, preset):
    """1つの閉じた（または開いた）パスに対して点を生成する"""
    path_points = []
    if len(vertices) < 2:
        return path_points

    path_vertices = np.array(vertices)
    pitch = preset['weld_pitch']

    # 始点を追加
    path_points.append({'x': float(path_vertices[0, 0]), 'y': float(path_vertices[0, 1])})

    accumulated_distance = 0.0

    for i in range(len(path_vertices) - 1):
        start_point = path_vertices[i]
        end_point = path_vertices[i + 1]

        segment_vector = end_point - start_point
        segment_length = np.linalg.norm(segment_vector)

        if segment_length < 1e-6:
            continue

        segment_direction = segment_vector / segment_length
        dist_at_segment_start = accumulated_distance

        # このセグメント内でピッチごとの点を計算
        next_weld_dist = (np.floor(dist_at_segment_start / pitch) + 1) * pitch

        while next_weld_dist < dist_at_segment_start + segment_length:
            dist_within_segment = next_weld_dist - dist_at_segment_start
            new_point_coord = start_point + dist_within_segment * segment_direction
            path_points.append({'x': float(new_point_coord[0]), 'y': float(new_point_coord[1])})
            next_weld_dist += pitch

        accumulated_distance += segment_length

    return path_points


def generate_path_as_points(all_paths_vertices, preset):
    """
    複数のパス（頂点リストのリスト）を受け取り、すべての溶着点を生成して
    1つのリストに結合して返す。
    """
    if not all_paths_vertices:
        return []

    combined_points = []

    # 受け取った vertices が「リストのリスト(複数パス)」か「ただのリスト(単一パス)」か判定して統一
    # dxf_parser修正後は リストのリスト [[v1,v2...], [v3,v4...]] で来る想定
    if isinstance(all_paths_vertices[0][0], (float, int)):
        # 旧形式対策（万が一単一リストが来た場合）
        all_paths_list = [all_paths_vertices]
    else:
        all_paths_list = all_paths_vertices

    for i, vertices in enumerate(all_paths_list):
        points = _generate_points_for_single_loop(vertices, preset)
        combined_points.extend(points)
        # ※ここでパスとパスの間の「空走移動」は自動的に発生します。
        # 機械制御側(PageMerged)で、距離が離れている場合は自動的に
        # 一旦停止・Z退避するように修正済み（dist > 5.0mm の判定）なので、
        # ここでは単純に座標リストを繋げるだけでOKです。

    return combined_points