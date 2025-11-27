# plot_builder.py

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon  # ★このインポートが必要です

import config


def create_plot_figure(outline_vertices, weld_points_data):
    """
    DXFの輪郭と、新しい点ベースの溶着経路をプロットする。
    """
    fig, ax = plt.subplots(figsize=(10, 8))

    # ▼▼▼ 追加: 点のサイズ(s_size)の計算 ▼▼▼
    span = 100.0
    if outline_vertices is not None and len(outline_vertices) > 0:
        outline = np.array(outline_vertices)
        if len(outline) > 0:
            x_range = outline[:, 0].max() - outline[:, 0].min()
            y_range = outline[:, 1].max() - outline[:, 1].min()
            span = max(x_range, y_range)
    elif weld_points_data:
        # 輪郭がない場合は点データから計算
        pts = np.array([[p['x'], p['y']] for p in weld_points_data])
        if len(pts) > 0:
            x_range = pts[:, 0].max() - pts[:, 0].min()
            y_range = pts[:, 1].max() - pts[:, 1].min()
            span = max(x_range, y_range)

    # 範囲が広い(=縮尺小)ときは点を小さく、狭い(=拡大)ときは大きく
    # 係数2000は調整可能です
    if span > 0:
        s_size = 2000.0 / span
    else:
        s_size = 20.0

    # サイズが大きすぎたり小さすぎたりしないように制限
    s_size = max(1.0, min(s_size, 50.0))
    # ▲▲▲ 追加ここまで ▲▲▲

    # 1. DXFの輪郭を描画
    if outline_vertices is not None and len(outline_vertices) > 0:
        outline = np.array(outline_vertices)
        ax.plot(outline[:, 0], outline[:, 1], 'b-', label='DXF Outline', linewidth=1.0)

        # ★ここで poly を定義して追加 (エラーの原因はおそらくここが抜けていたため)
        poly = Polygon(outline, closed=True, facecolor='blue', alpha=0.1)
        ax.add_patch(poly)

    # 2. 溶着点を散布図として描画 (サイズ s を動的に設定)
    if weld_points_data:
        points = np.array([[p['x'], p['y']] for p in weld_points_data])
        # s=s_size を指定
        scatter = ax.scatter(points[:, 0], points[:, 1], c='red', s=s_size, label='Weld Points', zorder=5)
    else:
        # データがない場合もscatterオブジェクトを空で作成
        scatter = ax.scatter([], [], c='red', s=s_size, label='Weld Points', zorder=5)

    ax.set_aspect('equal', adjustable='box')
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_title("DXF Outline and Generated Weld Path")

    # 凡例を外に出す
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)
    ax.grid(True, linestyle='--', alpha=0.6)

    fig.tight_layout()

    # Matplotlibのインタラクティブな編集で使うデータをfigureオブジェクトに格納
    fig._weld_data = weld_points_data
    fig._weld_artists = {'scatter': scatter}
    fig._helpers = {'outline_vertices': outline_vertices}

    return fig