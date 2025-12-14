# plot_builder.py
import matplotlib.pyplot as plt
import numpy as np


def create_plot_figure(all_paths_vertices, weld_points_data):
    """
    DXFの輪郭(複数パス対応)と、溶着点をプロットする。
    """
    fig, ax = plt.subplots(figsize=(10, 8))

    # --- 縮尺計算用 ---
    all_x = []
    all_y = []

    # パスの座標収集
    if all_paths_vertices:
        # 単一パスか複数パスか判定して統一
        paths = all_paths_vertices if isinstance(all_paths_vertices[0][0], (list, tuple, np.ndarray)) else [
            all_paths_vertices]

        for path in paths:
            p_arr = np.array(path)
            if len(p_arr) > 0:
                all_x.extend(p_arr[:, 0])
                all_y.extend(p_arr[:, 1])
                # 線を描画
                ax.plot(p_arr[:, 0], p_arr[:, 1], 'b-', linewidth=1.0, alpha=0.7)

    # 点の座標収集
    if weld_points_data:
        px = [p['x'] for p in weld_points_data]
        py = [p['y'] for p in weld_points_data]
        all_x.extend(px)
        all_y.extend(py)

    # スケール調整
    if all_x and all_y:
        span_x = max(all_x) - min(all_x)
        span_y = max(all_y) - min(all_y)
        span = max(span_x, span_y)
        s_size = 2000.0 / span if span > 0 else 20.0
        s_size = max(1.0, min(s_size, 50.0))
    else:
        s_size = 20.0

    # 溶着点を描画
    if weld_points_data:
        pts = np.array([[p['x'], p['y']] for p in weld_points_data])
        scatter = ax.scatter(pts[:, 0], pts[:, 1], c='red', s=s_size, label='Weld Points', zorder=5)
    else:
        scatter = ax.scatter([], [], c='red', s=s_size, label='Weld Points', zorder=5)

    ax.set_aspect('equal', adjustable='box')
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_title("Generated Path")
    ax.grid(True, linestyle='--', alpha=0.6)

    # 凡例設定 (枠外に配置)
    from matplotlib.lines import Line2D
    custom_lines = [Line2D([0], [0], color='b', lw=1),
                    Line2D([0], [0], marker='o', color='w', markerfacecolor='r', markersize=8)]

    # bbox_to_anchor でグラフエリアの外(右上のさらに右)に配置
    ax.legend(custom_lines, ['Outline', 'Weld Points'],
              bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)

    # レイアウト調整（凡例が見切れないように左側と下側を空ける）
    fig.subplots_adjust(right=0.8)

    # インタラクティブ編集用データ格納
    fig._weld_data = weld_points_data
    fig._weld_artists = {'scatter': scatter}

    return fig