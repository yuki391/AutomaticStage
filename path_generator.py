# path_generator.py
# DXF輪郭を一定ピッチの溶着点リストに変換するモジュール
# 【変更点】角検出で追加点を入れる処理を廃止しました。
#           角補正（角点を追加する機能）はもう行いません。
#           それ以外の挙動は従来どおりです。

import numpy as np
import config  # configはCURVE_SEGMENTSで使用する可能性があるため残す


def is_point_inside_polygon(point, polygon_vertices):
    """
    点がポリゴンの内側にあるかどうかを判定する (レイキャスティング法)。
    ※この関数は現在直接は使われていませんが残してあります。
    """
    x, y = point
    n = len(polygon_vertices)
    inside = False
    p1x, p1y = polygon_vertices[0]
    for i in range(n + 1):
        p2x, p2y = polygon_vertices[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def generate_path_as_points(vertices, is_closed, preset):
    """
    DXFの輪郭線を、プリセットで指定された一定間隔の点の集まりとして変換する。
    【変更】角（コーナー）検出による追加点の挿入処理を廃止しました。
    戻り値: [{'x': float, 'y': float}, ...]
    """
    path_points = []
    if len(vertices) < 2:
        return path_points

    path_vertices = np.array(vertices)

    # ステップ1：プリセットからピッチを取得し、輪郭に沿って点を生成
    pitch = preset['weld_pitch']  # preset から取得
    if pitch <= 0:
        print(f"エラー: プリセットの 'weld_pitch' は0より大きい値でなければなりません。")
        return []

    accumulated_distance = 0.0
    path_points.append({'x': float(path_vertices[0, 0]), 'y': float(path_vertices[0, 1])})

    loop_vertices = np.vstack([path_vertices, path_vertices[0]]) if is_closed else path_vertices

    for i in range(len(loop_vertices) - 1):
        start_point = loop_vertices[i]
        end_point = loop_vertices[i + 1]

        segment_vector = end_point - start_point
        segment_length = np.linalg.norm(segment_vector)

        if segment_length < 1e-6:
            continue

        segment_direction = segment_vector / segment_length

        dist_at_segment_start = accumulated_distance
        next_weld_dist = (np.floor(dist_at_segment_start / pitch) + 1) * pitch

        while next_weld_dist < dist_at_segment_start + segment_length:
            dist_within_segment = next_weld_dist - dist_at_segment_start
            new_point_coord = start_point + dist_within_segment * segment_direction
            path_points.append({'x': float(new_point_coord[0]), 'y': float(new_point_coord[1])})
            next_weld_dist += pitch

        accumulated_distance += segment_length

    # 角検出・追加は廃止したため、ここでは何も追加しない
    return path_points