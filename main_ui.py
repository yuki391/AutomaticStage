#UIを表示させるメインのコード
#DXFtoCSV.pyが必要

import tkinter as tk
from tkinter import filedialog, messagebox
import os
import csv
import numpy as np
from matplotlib.patches import Polygon, Rectangle, Circle


import matplotlib
matplotlib.use('TkAgg')  # <-- 必ず backend 指定を先に

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
# DXF処理の main をインポート
from DXFtoCSV_func import main as create_plot_from_dxf

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DXF to CSV Converter & Plotter (Interactive)")
        self.geometry("1000x800")

        self.dxf_path = ""
        self.current_fig = None
        self._active_canvas = None
        self._mpl_cids = []

        # --- ウィジェット ---
        top_frame = tk.Frame(self, pady=10)
        top_frame.pack(fill='x')

        self.select_btn = tk.Button(top_frame, text="DXFファイルを選択", command=self.select_file)
        self.select_btn.pack(side='left', padx=8)

        self.file_label = tk.Label(top_frame, text="ファイルが選択されていません", anchor='w')
        self.file_label.pack(side='left', fill='x', expand=True)

        self.run_btn = tk.Button(top_frame, text="実行", command=self.run_process, state='disabled')
        self.run_btn.pack(side='left', padx=6)

        self.save_btn = tk.Button(top_frame, text="保存 (CSV)", command=self.save_weld_points, state='disabled')
        self.save_btn.pack(side='left', padx=6)

        help_label = tk.Label(top_frame, text="（左クリック選択→ドラッグで移動、スクロールで回転、右クリックで削除、ダブル左クリックで追加）")
        help_label.pack(side='left', padx=8)

        # グラフ描画用フレーム
        self.plot_frame = tk.Frame(self)
        self.plot_frame.pack(fill='both', expand=True, padx=10, pady=10)
        self.canvas_widget = None

    def select_file(self):
        filepath = filedialog.askopenfilename(
            title="DXFファイルを選択してください",
            filetypes=[("DXF files", "*.dxf")]
        )
        if filepath:
            self.dxf_path = filepath
            self.file_label.config(text=os.path.basename(filepath))
            self.run_btn.config(state='normal')
            # 以前のグラフを消す（イベントも切断）
            self._clear_previous_plot()

    def _clear_previous_plot(self):
        # 以前の canvas があればイベント切断して削除
        try:
            if self._active_canvas and self._mpl_cids:
                for cid in self._mpl_cids:
                    try:
                        self._active_canvas.mpl_disconnect(cid)
                    except Exception:
                        pass
            if self.canvas_widget:
                self.canvas_widget.destroy()
                self.canvas_widget = None
            self._active_canvas = None
            self._mpl_cids = []
            self.current_fig = None
            self.save_btn.config(state='disabled')
        except Exception as e:
            print("前のプロット削除時に例外:", e)

    def run_process(self):
        if not self.dxf_path:
            messagebox.showwarning("警告", "DXFファイルが選択されていません。")
            return
        try:
            # 以前のグラフがあれば削除（イベントの切断も行う）
            self._clear_previous_plot()

            print("DXF処理とグラフ生成を開始します...")
            fig = create_plot_from_dxf(self.dxf_path)
            print("処理が完了しました。")

            if fig:
                self.current_fig = fig
                self.display_plot(fig)
                self.save_btn.config(state='normal')
            else:
                messagebox.showinfo("情報", "処理対象の図形が見つからなかったか、処理が正常に完了しませんでした。")
        except Exception as e:
            messagebox.showerror("エラー", f"処理中にエラーが発生しました:\n{e}")

    def display_plot(self, fig):
        """Figure を Tkinter に埋め込み、インタラクションを設定する"""
        canvas = FigureCanvasTkAgg(fig, master=self.plot_frame)
        self.canvas_widget = canvas.get_tk_widget()
        self.canvas_widget.pack(fill='both', expand=True)
        canvas.draw()
        self._active_canvas = canvas
        ax = fig.axes[0]

        # 状態保持
        state = {
            'selected_index': None,
            'dragging': False,
            'drag_offset': (0.0, 0.0)
        }

        # 便利な参照
        weld_data = fig._weld_data
        artists = fig._weld_artists
        helpers = fig._helpers
        scatter = artists['scatter']
        rects = artists['rects']
        e1_markers = artists['e1_markers']
        e2_markers = artists['e2_markers']

        def get_pixel_positions(offsets):
            """data座標配列をピクセル座標配列に変換"""
            return ax.transData.transform(offsets)

        def find_nearest_index(event, threshold_px=8):
            """マウスイベントの位置に近い溶接点のインデックスを返す（なければ None）"""
            if event.inaxes != ax:
                return None
            if scatter is None:
                return None
            offsets = scatter.get_offsets()
            if len(offsets) == 0:
                return None
            # event.x, event.y はピクセル座標
            disp = get_pixel_positions(offsets)
            dx = disp[:, 0] - event.x
            dy = disp[:, 1] - event.y
            dists = np.hypot(dx, dy)
            idx = int(np.argmin(dists))
            if dists[idx] <= threshold_px:
                return idx
            return None

        def update_scatter_positions():
            """scatter の位置を weld_data から更新"""
            pts = np.array([list(h['center']) for h in weld_data]) if weld_data else np.empty((0, 2))
            scatter.set_offsets(pts)

        def on_button_press(event):
            # 左ボタンなら選択＆ドラッグ開始 or ダブルクリックで追加
            if event.inaxes != ax:
                return

            # ダブルクリック（追加）
            if getattr(event, 'dblclick', False) and event.button == 1:
                # 追加：デフォルト角度 0
                cx, cy = event.xdata, event.ydata
                angle = 0.0
                corners = fig.compute_corners((cx, cy), angle)
                end1, end2 = helpers['get_weld_endpoints'](cx, cy, angle, helpers['HEAD_WIDTH'])
                e1_in = helpers['is_point_inside_polygon'](end1, helpers['outline_vertices'])
                e2_in = helpers['is_point_inside_polygon'](end2, helpers['outline_vertices'])
                new_head = {'center': (cx, cy), 'angle_deg': angle, 'corners': corners, 'end1': end1, 'end2': end2, 'e1_inside': e1_in, 'e2_inside': e2_in}
                weld_data.append(new_head)

                # パッチ・マーカー作成
                patch_color = 'orange' if (e1_in or e2_in) else 'green'
                patch = Polygon(corners, closed=True, facecolor=patch_color, edgecolor='black', linewidth=0.5, alpha=0.6, zorder=2)
                ax.add_patch(patch)
                rects.append(patch)

                if e1_in:
                    m1 = ax.scatter(end1[0], end1[1], c='red', s=20, marker='x', zorder=5)
                else:
                    m1 = None
                if e2_in:
                    m2 = ax.scatter(end2[0], end2[1], c='red', s=20, marker='x', zorder=5)
                else:
                    m2 = None
                e1_markers.append(m1)
                e2_markers.append(m2)

                update_scatter_positions()
                canvas.draw_idle()
                return

            # 通常クリック：近い点を探して選択
            if event.button == 1:
                idx = find_nearest_index(event)
                if idx is not None:
                    state['selected_index'] = idx
                    state['dragging'] = True
                    # マウス座標と中心点とのオフセットを記録（data座標系）
                    cx, cy = weld_data[idx]['center']
                    state['drag_offset'] = (cx - event.xdata, cy - event.ydata)
                else:
                    state['selected_index'] = None
                    state['dragging'] = False

            # 右クリックで削除
            elif event.button == 3:
                idx = find_nearest_index(event)
                if idx is not None:
                    # データ削除
                    weld_data.pop(idx)
                    # パッチ削除
                    patch = rects.pop(idx)
                    try:
                        patch.remove()
                    except Exception:
                        pass
                    # endpoint マーカー削除
                    m1 = e1_markers.pop(idx)
                    m2 = e2_markers.pop(idx)
                    if m1 is not None:
                        try:
                            m1.remove()
                        except Exception:
                            pass
                    if m2 is not None:
                        try:
                            m2.remove()
                        except Exception:
                            pass
                    update_scatter_positions()
                    canvas.draw_idle()

        def on_motion(event):
            if not state['dragging'] or state['selected_index'] is None:
                return
            if event.inaxes != ax:
                return
            idx = state['selected_index']
            # 新しい中心
            new_cx = event.xdata + state['drag_offset'][0]
            new_cy = event.ydata + state['drag_offset'][1]
            weld_data[idx]['center'] = (new_cx, new_cy)
            # 角度はそのまま
            ang = weld_data[idx]['angle_deg']
            # 再計算
            new_corners = fig.compute_corners((new_cx, new_cy), ang)
            weld_data[idx]['corners'] = new_corners
            weld_data[idx]['end1'], weld_data[idx]['end2'] = helpers['get_weld_endpoints'](new_cx, new_cy, ang, helpers['HEAD_WIDTH'])
            e1_in = helpers['is_point_inside_polygon'](weld_data[idx]['end1'], helpers['outline_vertices'])
            e2_in = helpers['is_point_inside_polygon'](weld_data[idx]['end2'], helpers['outline_vertices'])
            weld_data[idx]['e1_inside'] = e1_in
            weld_data[idx]['e2_inside'] = e2_in

            # patch 更新
            rect = rects[idx]
            rect.set_xy(new_corners)
            rect.set_facecolor('orange' if (e1_in or e2_in) else 'green')

            # endpoint マーカーの更新（作成/削除/位置）
            if e1_in:
                if e1_markers[idx] is None:
                    e1_markers[idx] = ax.scatter(weld_data[idx]['end1'][0], weld_data[idx]['end1'][1], c='red', s=20, marker='x', zorder=5)
                else:
                    # scatter の位置を更新するには removeして再作成が最も確実
                    e1_markers[idx].remove()
                    e1_markers[idx] = ax.scatter(weld_data[idx]['end1'][0], weld_data[idx]['end1'][1], c='red', s=20, marker='x', zorder=5)
            else:
                if e1_markers[idx] is not None:
                    try:
                        e1_markers[idx].remove()
                    except Exception:
                        pass
                    e1_markers[idx] = None

            if e2_in:
                if e2_markers[idx] is None:
                    e2_markers[idx] = ax.scatter(weld_data[idx]['end2'][0], weld_data[idx]['end2'][1], c='red', s=20, marker='x', zorder=5)
                else:
                    e2_markers[idx].remove()
                    e2_markers[idx] = ax.scatter(weld_data[idx]['end2'][0], weld_data[idx]['end2'][1], c='red', s=20, marker='x', zorder=5)
            else:
                if e2_markers[idx] is not None:
                    try:
                        e2_markers[idx].remove()
                    except Exception:
                        pass
                    e2_markers[idx] = None

            # scatter の位置更新
            update_scatter_positions()
            canvas.draw_idle()

        def on_button_release(event):
            if state['dragging']:
                state['dragging'] = False
                state['selected_index'] = None
                canvas.draw_idle()

        def on_scroll(event):
            # スクロールで回転（選択中の点があれば）
            if event.inaxes != ax:
                return
            idx = state['selected_index']
            # もしドラッグ中でなければ、先に近傍の点を選択してから回転する（ホバー選択はやらない）
            if idx is None:
                idx = find_nearest_index(event)
                if idx is None:
                    return
            # delta 角度
            # Matplotlib の ScrollEvent では event.button が 'up'/'down' のことが多い
            if getattr(event, 'button', None) in ('up', 'down'):
                delta = 5.0 if event.button == 'up' else -5.0
            elif hasattr(event, 'step'):
                delta = 5.0 * event.step
            else:
                # フォールバック
                delta = 5.0 if event.step >= 0 else -5.0

            weld_data[idx]['angle_deg'] = (weld_data[idx]['angle_deg'] + delta) % 360.0
            cx, cy = weld_data[idx]['center']
            ang = weld_data[idx]['angle_deg']
            new_corners = fig.compute_corners((cx, cy), ang)
            weld_data[idx]['corners'] = new_corners
            weld_data[idx]['end1'], weld_data[idx]['end2'] = helpers['get_weld_endpoints'](cx, cy, ang, helpers['HEAD_WIDTH'])
            e1_in = helpers['is_point_inside_polygon'](weld_data[idx]['end1'], helpers['outline_vertices'])
            e2_in = helpers['is_point_inside_polygon'](weld_data[idx]['end2'], helpers['outline_vertices'])
            weld_data[idx]['e1_inside'] = e1_in
            weld_data[idx]['e2_inside'] = e2_in

            # patch update
            rect = rects[idx]
            rect.set_xy(new_corners)
            rect.set_facecolor('orange' if (e1_in or e2_in) else 'green')

            # endpoint marker 更新（remove/create）
            if e1_in:
                if e1_markers[idx] is None:
                    e1_markers[idx] = ax.scatter(weld_data[idx]['end1'][0], weld_data[idx]['end1'][1], c='red', s=20, marker='x', zorder=5)
                else:
                    e1_markers[idx].remove()
                    e1_markers[idx] = ax.scatter(weld_data[idx]['end1'][0], weld_data[idx]['end1'][1], c='red', s=20, marker='x', zorder=5)
            else:
                if e1_markers[idx] is not None:
                    try:
                        e1_markers[idx].remove()
                    except Exception:
                        pass
                    e1_markers[idx] = None

            if e2_in:
                if e2_markers[idx] is None:
                    e2_markers[idx] = ax.scatter(weld_data[idx]['end2'][0], weld_data[idx]['end2'][1], c='red', s=20, marker='x', zorder=5)
                else:
                    e2_markers[idx].remove()
                    e2_markers[idx] = ax.scatter(weld_data[idx]['end2'][0], weld_data[idx]['end2'][1], c='red', s=20, marker='x', zorder=5)
            else:
                if e2_markers[idx] is not None:
                    try:
                        e2_markers[idx].remove()
                    except Exception:
                        pass
                    e2_markers[idx] = None

            update_scatter_positions()
            canvas.draw_idle()

        # イベント接続 (以前のは消している想定)
        cid1 = canvas.mpl_connect('button_press_event', on_button_press)
        cid2 = canvas.mpl_connect('motion_notify_event', on_motion)
        cid3 = canvas.mpl_connect('button_release_event', on_button_release)
        cid4 = canvas.mpl_connect('scroll_event', on_scroll)
        self._mpl_cids = [cid1, cid2, cid3, cid4]

        # 最終的に canvas を描画
        canvas.draw()

    def save_weld_points(self):
        """現在の溶接点データを CSV として保存"""
        if self.current_fig is None:
            messagebox.showwarning("警告", "保存するデータがありません。")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="weld_points.csv",
            title="保存先を選択"
        )
        if not path:
            return
        try:
            with open(path, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['center_x', 'center_y', 'angle_deg']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for head in self.current_fig._weld_data:
                    writer.writerow({
                        'center_x': f"{head['center'][0]:.4f}",
                        'center_y': f"{head['center'][1]:.4f}",
                        'angle_deg': f"{head['angle_deg']:.4f}"
                    })
            messagebox.showinfo("保存完了", f"溶接点データを '{path}' に保存しました。")
        except IOError as e:
            messagebox.showerror("エラー", f"CSVファイルの書き込みに失敗しました:\n{e}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
