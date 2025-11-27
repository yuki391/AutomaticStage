import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import matplotlib

matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import ui_components
from page_welding_control_logic import WeldingControlLogic
import presets
import config
from procedures import run_preview


# Logicクラスがボタン設定を変更しようとした際のエラー回避用ダミー
class DummyWidget:
    def config(self, **kwargs):
        pass


class PageMergedPreviewExecution(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # --- ハードウェア参照 ---
        self.motion = self.controller.hardware['motion']
        self.dio = self.controller.hardware['dio']
        self.welder = self.controller.hardware['welder']
        self.sensors = self.controller.hardware['sensors']

        # ロジッククラス用の変数初期化
        self.is_moving = False
        self.step_entries = {}
        self.jog_buttons = []
        self.stop_event = threading.Event()

        # ロジッククラス互換用ダミー
        self.homing_button = DummyWidget()
        self.z_origin_btn = DummyWidget()

        # ロジッククラスの初期化 (JOG操作などで利用)
        self.logic = WeldingControlLogic(self)

        # =================================================================
        # グリッドレイアウトの設定 (3行 x 2列)
        # =================================================================
        self.columnconfigure(0, weight=1)  # 左列
        self.columnconfigure(1, weight=1)  # 右列

        self.rowconfigure(0, weight=0)  # 上段 (設定・原点調整) 固定高さ
        self.rowconfigure(1, weight=1)  # 中段 (グラフ) 伸縮
        self.rowconfigure(2, weight=0)  # 下段 (ログ・Z軸・実行) 固定高さ

        # =================================================================
        # 上段 (Row 0)
        # =================================================================

        # --- 左上: 設定情報 ---
        info_frame = ttk.LabelFrame(self, text="設定情報")
        info_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        tk.Button(info_frame, text="<< DXF編集に戻る",
                  command=lambda: controller.show_page("PageDxfEditor"),
                  bg="#e0e0e0").pack(anchor='nw', padx=5, pady=2)

        self.lbl_preset = tk.Label(info_frame, text="プリセット: ---", font=("Arial", 11, "bold"), fg="blue")
        self.lbl_preset.pack(anchor='w', padx=10, pady=2)
        self.lbl_points = tk.Label(info_frame, text="点数: 0", font=("Arial", 11))
        self.lbl_points.pack(anchor='w', padx=10, pady=2)

        # --- 右上 & 中央上: 原点位置の調整 (XYのみ) ---
        jog_frame = ttk.LabelFrame(self, text="溶着エリアの移動 (XYデータシフト)")
        jog_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

        jog_inner = tk.Frame(jog_frame)
        jog_inner.pack(fill='both', expand=True, padx=5, pady=5)

        # 1. XY操作 (Z軸は下へ移動しました)
        xy_panel = tk.LabelFrame(jog_inner, text="XY軸(水平)")
        xy_panel.pack(side='left', fill='y', padx=5)

        self._create_mini_jog(xy_panel, "x", "X軸")
        self._create_mini_jog(xy_panel, "y", "Y軸")

        step_f = tk.Frame(xy_panel)
        step_f.pack(pady=5)
        tk.Label(step_f, text="Step:").pack(side='left')
        self.step_entries['x'] = tk.Entry(step_f, width=5, justify='center')
        self.step_entries['x'].insert(0, "1.0")
        self.step_entries['x'].pack(side='left')
        self.step_entries['y'] = self.step_entries['x']

        # 2. データシフトボタン
        shift_frame = tk.Frame(jog_inner)
        shift_frame.pack(side='left', fill='both', expand=True, padx=10)

        tk.Label(shift_frame, text="現在位置の分だけ\n全点を移動させます", font=("Arial", 9)).pack(pady=2)

        tk.Button(shift_frame, text="データ位置シフト\n(現在値を加算)", bg="orange",
                  font=("Arial", 10, "bold"),
                  command=self.shift_data_by_current_pos).pack(fill='both', expand=True, pady=5)

        # =================================================================
        # 中段 (Row 1) - Preview
        # =================================================================
        self.plot_frame = tk.Frame(self, bg="white", relief="sunken", bd=1)
        self.plot_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        self.canvas = None

        # =================================================================
        # 下段 (Row 2) - 3カラム構成に変更
        # =================================================================
        bottom_container = tk.Frame(self)
        bottom_container.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)

        # 下段のカラム設定 (左:可変, 中:固定, 右:固定)
        bottom_container.columnconfigure(0, weight=1)
        bottom_container.columnconfigure(1, weight=0)
        bottom_container.columnconfigure(2, weight=0)

        # --- 左下: ログ ---
        log_frame = ttk.LabelFrame(bottom_container, text="ログ")
        log_frame.grid(row=0, column=0, sticky="nsew", padx=5)

        self.log_text = tk.Text(log_frame, height=6, state='disabled', bg='black', fg='lightgray', font=("Courier", 9))
        self.log_text.pack(fill='both', expand=True, padx=5, pady=5)

        # --- 真ん中下: Z軸コントロール (ここへ移動) ---
        z_frame = ttk.LabelFrame(bottom_container, text="Z軸(高さ)")
        z_frame.grid(row=0, column=1, sticky="nsew", padx=5)

        # Z軸操作パネル
        z_inner = tk.Frame(z_frame)
        z_inner.pack(padx=5, pady=5)

        # 上下ボタンとステップ入力
        btn_frame = tk.Frame(z_inner)
        btn_frame.pack(pady=2)
        tk.Button(btn_frame, text="UP ▲", command=lambda: self.logic.move_axis('z', -1)).pack(side='left', padx=2)
        self.step_entries['z'] = tk.Entry(btn_frame, width=5, justify='center')
        self.step_entries['z'].insert(0, "5.0")
        self.step_entries['z'].pack(side='left', padx=2)
        tk.Button(btn_frame, text="DOWN ▼", command=lambda: self.logic.move_axis('z', 1)).pack(side='left', padx=2)

        # パルス移動
        pulse_frame = tk.Frame(z_inner)
        pulse_frame.pack(pady=5)
        tk.Label(pulse_frame, text="Pulse:").pack(side='left')
        self.step_entries['z_pulse'] = tk.Entry(pulse_frame, width=6)
        self.step_entries['z_pulse'].insert(0, str(getattr(config, 'SAFE_Z_PULSE', 2100)))
        self.step_entries['z_pulse'].pack(side='left', padx=2)
        tk.Button(pulse_frame, text="Go", command=self.logic.run_set_z_pulse, width=3).pack(side='left')

        # --- 右下: 実行操作 ---
        exec_frame = ttk.LabelFrame(bottom_container, text="実行操作")
        exec_frame.grid(row=0, column=2, sticky="nsew", padx=5)

        # 実行ボタン群
        btn_area = tk.Frame(exec_frame)
        btn_area.pack(fill='x', pady=5, padx=5)

        tk.Button(btn_area, text="動作プレビュー\n(溶着なし)",
                  command=self.run_dry_run_preview).pack(side='left', fill='both', expand=True, padx=5)

        self.start_btn = tk.Button(btn_area, text="★ 溶着開始 ★", bg="red", fg="white", font=("Arial", 12, "bold"),
                                   height=2, command=self.start_real_welding)
        self.start_btn.pack(side='left', fill='both', expand=True, padx=5)

        # 安全装置
        safe_area = tk.Frame(exec_frame)
        safe_area.pack(fill='x', pady=5, padx=5)

        self.stop_btn = tk.Button(safe_area, text="緊急停止", bg="red", fg="white", font=("Arial", 9, "bold"),
                                  command=self.on_emergency_stop)
        self.stop_btn.pack(side='left', fill='x', expand=True, padx=2)

        self.recover_btn = tk.Button(safe_area, text="復帰", command=self.on_recovery, state='disabled')
        self.recover_btn.pack(side='left', fill='x', expand=True, padx=2)

        self.status_label = tk.Label(safe_area, text="待機中", anchor='w')
        self.status_label.pack(side='left', padx=5)

        # 初期化
        self.active_preset = {}
        self._init_preset()

    def _init_preset(self):
        default_name = getattr(config, 'DEFAULT_PRESET_NAME', None)
        if default_name and default_name in presets.WELDING_PRESETS:
            self.active_preset = presets.WELDING_PRESETS[default_name]
        elif len(presets.WELDING_PRESETS) > 0:
            self.active_preset = presets.WELDING_PRESETS[list(presets.WELDING_PRESETS.keys())[0]]

    def on_page_show(self):
        p_name = self.controller.shared_data.get('preset_name', 'Unknown')
        points = self.controller.shared_data.get('weld_points', [])

        self.lbl_preset.config(text=f"プリセット: {p_name}")
        self.lbl_points.config(text=f"点数: {len(points)} 点")

        if p_name in presets.WELDING_PRESETS:
            self.active_preset = presets.WELDING_PRESETS[p_name]

        self.draw_preview(points)

    def draw_preview(self, points):
        if self.canvas:
            self.canvas.get_tk_widget().destroy()

        fig = Figure(figsize=(8, 3), dpi=100)
        ax = fig.add_subplot(111)

        ax.set_title("Weld Path Preview (Machine Area)")
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")
        ax.grid(True, linestyle='--', alpha=0.6)
        ax.set_aspect('equal')

        # マシンスペックに合わせて表示範囲を固定
        max_x = getattr(config, 'MACHINE_MAX_X_MM', 700.0)
        max_y = getattr(config, 'MACHINE_MAX_Y_MM', 500.0)
        ax.set_xlim(0, max_x)
        ax.set_ylim(0, max_y)

        # 表示範囲が広いため、点を小さくして「線に見える」のを防ぐ
        span = max(max_x, max_y)
        s_size = 2000.0 / span if span > 0 else 20.0
        s_size = max(1.0, min(s_size, 50.0))

        if points:
            x_vals = [float(p['x']) for p in points]
            y_vals = [float(p['y']) for p in points]

            ax.plot(x_vals, y_vals, 'b-', alpha=0.3, label='Path Order')
            # ★ Weld Points のサイズ設定はここの s=15 です
            ax.scatter(x_vals, y_vals, c='red', s=15, zorder=5, label='Weld Points')
            ax.plot(x_vals[0], y_vals[0], 'go', markersize=8, label="Start")
            ax.plot(x_vals[-1], y_vals[-1], 'rx', markersize=8, label="End")

            ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left', borderaxespad=0)
            fig.subplots_adjust(left=0.1, right=0.85, top=0.9, bottom=0.2)
        else:
            ax.text(max_x / 2, max_y / 2, "No Data Loaded", ha='center', va='center')

        self.canvas = FigureCanvasTkAgg(fig, master=self.plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill='both', expand=True)

    def _create_mini_jog(self, parent, axis, label):
        f = tk.Frame(parent)
        f.pack(pady=2)
        tk.Label(f, text=label, width=4, anchor='e').pack(side='left')
        btn_minus = tk.Button(f, text="<", command=lambda: self.logic.move_axis(axis, -1), width=3)
        btn_minus.pack(side='left', padx=2)
        self.jog_buttons.append(btn_minus)
        btn_plus = tk.Button(f, text=">", command=lambda: self.logic.move_axis(axis, 1), width=3)
        btn_plus.pack(side='left', padx=2)
        self.jog_buttons.append(btn_plus)

    # --- アクション ---
    def shift_data_by_current_pos(self):
        """
        現在の機械座標 (X, Y) を取得し、
        全ての溶着点データの座標にその値を加算してデータを更新する。
        """
        if not self.motion:
            messagebox.showerror("エラー", "モーションシステムが接続されていません。")
            return

        # 現在位置を取得
        dx = self.motion.current_pos.get('x', 0.0)
        dy = self.motion.current_pos.get('y', 0.0)

        if dx == 0 and dy == 0:
            self.add_log("現在位置が(0,0)のため、シフトを行いませんでした。")
            return

        if not messagebox.askyesno("確認",
                                   f"現在のデータ全てを\n X: +{dx:.2f} mm\n Y: +{dy:.2f} mm\nシフトしますか？\n(グラフが移動します)"):
            return

        # データを更新
        points = self.controller.shared_data.get('weld_points', [])
        new_points = []
        for p in points:
            new_points.append({
                'x': float(p['x']) + dx,
                'y': float(p['y']) + dy
            })

        # 共有データを書き換え
        self.controller.shared_data['weld_points'] = new_points

        self.add_log(f"データをシフトしました: X+{dx:.2f}, Y+{dy:.2f}")

        # グラフを再描画
        self.draw_preview(new_points)

    def start_real_welding(self):
        """溶着実行 (原点設定スキップ版)"""
        if not self.motion:
            messagebox.showerror("エラー", "モーションシステム未接続")
            return

        points = self.controller.shared_data.get('weld_points', [])
        if not points:
            messagebox.showwarning("警告", "溶着データがありません。")
            return

        if not messagebox.askyesno("最終確認",
                                   "溶着を開始します。\nエリアシフトは済んでいますか？\n\n「はい」を押すと直ちに移動を開始します。"):
            return

        self.stop_event.clear()
        # 独自のスレッドで実行
        t = threading.Thread(target=self._welding_flow_absolute_thread, args=(points,))
        t.daemon = True
        t.start()

    def _welding_flow_absolute_thread(self, points):
        """
        データが既に機械座標系（絶対座標）になっている前提で実行するフロー
        """
        try:
            self.add_log("--- 溶着プロセス開始 (絶対座標モード) ---")

            # プレビューチェック (範囲外なら停止)
            work_origin = (0.0, 0.0)
            if not run_preview(self.motion, points, work_origin, self.active_preset):
                self.add_log("プレビューチェックでエラー検出。停止します。")
                return

            if self.stop_event.is_set():
                self.add_log("中断されました。")
                return

            self.add_log(f"--- 溶着ジョブ実行 ({len(points)}点) ---")

            # 安全高さへ移動
            self.motion.move_z_abs_pulse(config.SAFE_Z_PULSE)

            for i, p in enumerate(points):
                if self.stop_event.is_set():
                    self.add_log("中断されました。")
                    break

                target_x = float(p['x'])
                target_y = float(p['y'])

                self.add_log(f"({i + 1}/{len(points)}) 移動: X={target_x:.2f}, Y={target_y:.2f}")

                # XY移動
                self.motion.move_xy_abs(target_x, target_y, self.active_preset)

                # 初回のみ少し待機
                if i == 0:
                    time.sleep(1)

                # 溶着動作
                self.motion.execute_welding_press(self.welder, self.active_preset)

            # 完了後
            self.add_log("--- 溶着ジョブ完了 ---")
            self.motion.return_to_origin()

        except Exception as e:
            self.add_log(f"エラー発生: {e}")
            messagebox.showerror("実行時エラー", str(e))

    # --- プレビュー ---
    def run_dry_run_preview(self):
        self.add_log("動作プレビューは未実装です（範囲チェックのみ実行されます）")
        points = self.controller.shared_data.get('weld_points', [])
        run_preview(self.motion, points, (0, 0), self.active_preset)

    # --- 必須メソッド ---
    def on_emergency_stop(self):
        self.stop_event.set()
        self.logic.on_emergency_stop()

    def on_recovery(self):
        self.stop_event.clear()
        self.logic.on_recovery()

    def add_log(self, msg):
        if hasattr(self, 'log_text') and self.log_text.winfo_exists():
            self.log_text.config(state='normal')
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state='disabled')
        else:
            print(msg)