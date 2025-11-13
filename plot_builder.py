# plot_builder.py

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon

import config


def create_plot_figure(outline_vertices, weld_points_data):
    """
    DXFの輪郭と、新しい点ベースの溶着経路をプロットする。
    """
    fig, ax = plt.subplots(figsize=(10, 8))

    # 1. DXFの輪郭を描画
    if outline_vertices is not None and len(outline_vertices) > 0:
        outline = np.array(outline_vertices)
        ax.plot(outline[:, 0], outline[:, 1], 'b-', label='DXF Outline', linewidth=1.0)
        # ポリゴンとして薄く塗りつぶし
        poly = Polygon(outline, closed=True, facecolor='blue', alpha=0.1)
        ax.add_patch(poly)

    # 2. 溶着点を散布図として描画
    if weld_points_data:
        points = np.array([[p['x'], p['y']] for p in weld_points_data])
        scatter = ax.scatter(points[:, 0], points[:, 1], c='red', s=25, label='Weld Points', zorder=5)
    else:
        # データがない場合もscatterオブジェクトを空で作成
        scatter = ax.scatter([], [], c='red', s=25, label='Weld Points', zorder=5)


    ax.set_aspect('equal', adjustable='box')
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_title("DXF Outline and Generated Weld Path")
    ax.legend()
    ax.grid(True, linestyle='--', alpha=0.6)

    # Matplotlibのインタラクティブな編集で使うデータをfigureオブジェクトに格納
    fig._weld_data = weld_points_data
    fig._weld_artists = {'scatter': scatter}
    fig._helpers = {'outline_vertices': outline_vertices} # is_point_insideのような補助機能で使う可能性

    return fig