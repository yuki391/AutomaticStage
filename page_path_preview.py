import tkinter as tk
from tkinter import ttk
import matplotlib

matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


class PagePathPreview(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # --- ヘッダー ---
        top_frame = tk.Frame(self, pady=10)
        top_frame.pack(fill='x')
        tk.Label(top_frame, text="Step 3: 溶着経路の最終確認", font=("Arial", 14, "bold")).pack(side='left', padx=10)

        # --- ナビゲーションボタン ---
        btn_frame = tk.Frame(self, pady=10)
        btn_frame.pack(side='bottom', fill='x')

        tk.Button(btn_frame, text="<< 戻る (DXF編集)",
                  command=lambda: controller.show_page("PageDxfEditor")).pack(side='left', padx=20)

        tk.Button(btn_frame, text="次へ: 実行画面へ >>", bg="orange", font=("Arial", 12, "bold"),
                  command=lambda: controller.show_page("PageExecution")).pack(side='right', padx=20)

        # --- グラフ表示エリア ---
        self.plot_frame = tk.Frame(self)
        self.plot_frame.pack(fill='both', expand=True, padx=10, pady=5)

        self.canvas = None

    def on_page_show(self):
        """ページが表示されたときにデータを読み込んで描画"""
        self.draw_preview()

    def draw_preview(self):
        # 既存のキャンバスがあれば削除（リセット）
        if self.canvas:
            self.canvas.get_tk_widget().destroy()

        # 共有データから点リストを取得
        points = self.controller.shared_data.get('weld_points', [])

        # グラフ作成
        fig = Figure(figsize=(6, 6), dpi=100)
        ax = fig.add_subplot(111)
        ax.set_title(f"Path Preview: {len(points)} points")
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")
        ax.grid(True, linestyle='--', alpha=0.6)
        ax.set_aspect('equal')

        if points:
            # 座標データの抽出
            x_vals = [float(p['x']) for p in points]
            y_vals = [float(p['y']) for p in points]

            # 経路（薄い青線）
            ax.plot(x_vals, y_vals, 'b-', alpha=0.3, label='Path Order')
            # 溶着点（赤丸）
            ax.scatter(x_vals, y_vals, c='red', s=30, zorder=5, label='Weld Points')

            # 開始点（緑丸で強調）
            ax.plot(x_vals[0], y_vals[0], 'go', markersize=10, label="Start")

            # 終了点（×印）
            ax.plot(x_vals[-1], y_vals[-1], 'rx', markersize=10, label="End")

            ax.legend()
        else:
            ax.text(0.5, 0.5, "No Data", ha='center', va='center')

        # Canvasを配置
        self.canvas = FigureCanvasTkAgg(fig, master=self.plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill='both', expand=True)