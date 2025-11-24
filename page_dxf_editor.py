# page_dxf_editor.py

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import numpy as np
import datetime

import matplotlib

matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import config
import presets  # プリセットファイルをインポート
from dxf_parser import get_all_entities_as_segments, find_connected_path
from path_generator import generate_path_as_points
from plot_builder import create_plot_figure
from csv_handler import save_path_to_csv


class PageDxfEditor(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.dxf_path = ""
        self.current_fig = None
        self._active_canvas = None
        self._mpl_cids = []

        # --- 上部フレーム ---
        top_frame = tk.Frame(self, pady=10)
        top_frame.pack(fill='x')

        # ファイル選択
        self.select_btn = tk.Button(top_frame, text="DXFファイルを選択", command=self.select_file)
        self.select_btn.pack(side='left', padx=8)
        self.file_label = tk.Label(top_frame, text="ファイルが選択されていません", anchor='w')
        self.file_label.pack(side='left', fill='x', expand=True)

        # 溶着制御ページへのボタン
        self.goto_preview_btn = tk.Button(top_frame, text="次へ: 溶着点プレビュー >>",command=self.go_to_preview, bg="lightblue")
        self.goto_preview_btn.pack(side='right', padx=10)
        self.save_btn = tk.Button(top_frame, text="編集結果をCSV保存", command=self.save_weld_points, state='disabled')
        self.save_btn.pack(side='right', padx=6)

        # --- 設定フレーム ---
        settings_frame = tk.Frame(self)
        settings_frame.pack(fill='x', padx=5)

        # プリセット選択UI
        preset_frame = ttk.LabelFrame(settings_frame, text="① 材質・設定プリセットを選択")
        preset_frame.pack(side='left', fill='x', pady=5, padx=5, expand=True)

        self.preset_var = tk.StringVar()
        preset_combo = ttk.Combobox(preset_frame, textvariable=self.preset_var, state='readonly', width=30)
        preset_combo.pack(side='left', padx=10, pady=10)

        preset_names = list(presets.WELDING_PRESETS.keys())
        preset_combo['values'] = preset_names

        # configにデフォルト名が存在するか確認
        if hasattr(config, 'DEFAULT_PRESET_NAME') and config.DEFAULT_PRESET_NAME in preset_names:
            self.preset_var.set(config.DEFAULT_PRESET_NAME)
        else:
            self.preset_var.set(preset_names[0])  # 存在しない場合は最初のものを選択

        # 共有データに初期値を設定
        self.controller.shared_data['preset_name'] = self.preset_var.get()
        preset_combo.bind('<<ComboboxSelected>>', self.on_preset_selected)

        # 経路生成ボタン
        self.run_btn = tk.Button(settings_frame, text="② DXFから経路生成", command=self.run_process, state='disabled',
                                 height=2)
        self.run_btn.pack(side='left', padx=10, pady=10)

        # --- プロット表示フレーム ---
        self.plot_frame = tk.Frame(self)
        self.plot_frame.pack(fill='both', expand=True, padx=10, pady=10)
        self.canvas_widget = None

    def on_preset_selected(self, event=None):
        """プリセットが選択されたら、共有データに名前を保存する"""
        self.controller.shared_data['preset_name'] = self.preset_var.get()
        print(f"プリセット「{self.preset_var.get()}」が選択されました。")

    def select_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("DXF files", "*.dxf")])
        if filepath:
            self.dxf_path = filepath
            self.file_label.config(text=os.path.basename(filepath))
            self.run_btn.config(state='normal')
            self._clear_previous_plot()

    def run_process(self):
        if not self.dxf_path: return
        self._clear_previous_plot()

        try:
            self.file_label.config(text=f"{os.path.basename(self.dxf_path)} を処理中...")
            self.update_idletasks()
            segments = get_all_entities_as_segments(self.dxf_path, config.CURVE_SEGMENTS)
            if not segments:
                messagebox.showwarning("解析エラー", "DXFファイルから有効な図形が見つかりませんでした。");
                return
            vertices, is_closed = find_connected_path(segments)
            if not vertices:
                messagebox.showwarning("解析エラー", "図形を連続した輪郭として再構築できませんでした。");
                return

            # 選択されているプリセットを取得して経路生成関数に渡す
            selected_preset_name = self.controller.shared_data['preset_name']
            active_preset = presets.WELDING_PRESETS[selected_preset_name]
            path_data = generate_path_as_points(vertices, is_closed, active_preset)

            if not path_data:
                messagebox.showerror("経路生成エラー", "DXFファイルから有効な溶着点を1つも生成できませんでした。")
                self.file_label.config(text=os.path.basename(self.dxf_path));
                return

            fig = create_plot_figure(vertices, path_data)
            if fig:
                fig._timestamp = datetime.datetime.now()
                self.current_fig = fig
                self.display_plot(fig)
                self.save_btn.config(state='normal')
            else:
                messagebox.showinfo("情報", "グラフの生成に失敗しました。")
            self.file_label.config(text=os.path.basename(self.dxf_path))
        except Exception as e:
            messagebox.showerror("エラー", f"処理中にエラーが発生しました:\n{e}")
            self.file_label.config(text=os.path.basename(self.dxf_path))

    def _clear_previous_plot(self):
        if self._active_canvas and self._mpl_cids:
            for cid in self._mpl_cids:
                try:
                    self._active_canvas.mpl_disconnect(cid)
                except:
                    pass
        if self.canvas_widget: self.canvas_widget.destroy()
        self.canvas_widget = None;
        self._active_canvas = None;
        self._mpl_cids = [];
        self.current_fig = None
        self.save_btn.config(state='disabled')

    def go_to_welding_page(self):
        if self.current_fig and hasattr(self.current_fig, '_weld_data'):
            self.controller.shared_data['weld_points'] = self.current_fig._weld_data
        # プリセット名はすでに共有データにあるので、そのままページを切り替える
        self.controller.show_page("PageWeldingControl")

    def save_weld_points(self):
        if not self.current_fig or not hasattr(self.current_fig, '_weld_data'):
            messagebox.showwarning("警告", "保存するデータがありません。");
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not path: return

        data_to_save = []
        for d in self.current_fig._weld_data:
            new_row = {'x': f"{d['x']:.4f}", 'y': f"{d['y']:.4f}"}
            data_to_save.append(new_row)

        timestamp_to_save = self.current_fig._timestamp
        if save_path_to_csv(path, data_to_save, timestamp_to_save):
            messagebox.showinfo("保存完了", f"溶接点データを '{os.path.basename(path)}' に保存しました。")
        else:
            messagebox.showerror("保存失敗", "CSVファイルの書き込みに失敗しました。")

    def display_plot(self, fig):
        canvas = FigureCanvasTkAgg(fig, master=self.plot_frame)
        self.canvas_widget = canvas.get_tk_widget();
        self.canvas_widget.pack(fill='both', expand=True)
        canvas.draw();
        self._active_canvas = canvas;
        ax = fig.axes[0]

        state = {'selected_index': None, 'dragging': False, 'drag_offset': (0, 0)}
        weld_data = fig._weld_data
        scatter = fig._weld_artists['scatter']

        def find_nearest_index(event, threshold_px=10):
            if event.inaxes != ax: return None
            offsets = scatter.get_offsets()
            if len(offsets) == 0: return None
            dist_sq = np.sum((ax.transData.transform(offsets) - (event.x, event.y)) ** 2, axis=1)
            idx = np.argmin(dist_sq)
            return int(idx) if dist_sq[idx] < threshold_px ** 2 else None

        def update_scatter_positions():
            pts = np.array([[d['x'], d['y']] for d in weld_data]) if weld_data else np.empty((0, 2))
            scatter.set_offsets(pts)
            canvas.draw_idle()
            fig._timestamp = datetime.datetime.now()

        def on_button_press(event):
            if event.inaxes != ax: return
            idx = find_nearest_index(event)
            if event.button == 1:
                if idx is not None:
                    state['selected_index'] = idx
                    state['dragging'] = True
                    cx, cy = weld_data[idx]['x'], weld_data[idx]['y']
                    state['drag_offset'] = (cx - event.xdata, cy - event.ydata)
                else:
                    state['selected_index'] = None
            elif event.button == 3:
                if idx is not None:
                    if messagebox.askyesno("削除確認", f"{idx + 1}番目の溶着点を削除しますか？"):
                        weld_data.pop(idx)
                        update_scatter_positions()
                else:
                    new_point = {'x': event.xdata, 'y': event.ydata}
                    weld_data.append(new_point)
                    update_scatter_positions()

        def on_motion(event):
            if not state['dragging'] or state['selected_index'] is None or event.inaxes != ax: return
            idx = state['selected_index']
            weld_data[idx]['x'] = event.xdata + state['drag_offset'][0]
            weld_data[idx]['y'] = event.ydata + state['drag_offset'][1]
            update_scatter_positions()

        def on_button_release(event):
            state['dragging'] = False

        self._mpl_cids = [
            canvas.mpl_connect('button_press_event', on_button_press),
            canvas.mpl_connect('motion_notify_event', on_motion),
            canvas.mpl_connect('button_release_event', on_button_release),
        ]

    def go_to_preview(self):
        """編集完了、データを保存してプレビュー画面へ"""
        if self.current_fig and hasattr(self.current_fig, '_weld_data'):
            # 1. 溶着点データを共有メモリに保存
            self.controller.shared_data['weld_points'] = self.current_fig._weld_data
            print(f"データ保存: {len(self.current_fig._weld_data)} 点")

            # 2. 選択中のプリセット名も保存
            self.controller.shared_data['preset_name'] = self.preset_var.get()

            # 3. 次のページへ移動
            self.controller.show_page("PagePathPreview")
        else:
            messagebox.showwarning("警告", "経路データが生成されていません。\nDXFを読み込んで経路生成を行ってください。")