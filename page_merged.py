import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import copy
import traceback
import math  # ★追加: 距離計算に使用
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


# 複数のボタンをまとめて操作するためのラッパークラス
class ButtonGroup:
    def __init__(self, *buttons):
        self.buttons = buttons

    def config(self, **kwargs):
        for btn in self.buttons:
            try:
                btn.config(**kwargs)
            except:
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
        self.jog_buttons = []  # ロック対象のボタンリスト

        # 実行制御用イベント
        self.stop_event = threading.Event()
        # ★追加: 一時停止用イベント (set=実行中, clear=一時停止中)
        self.pause_event = threading.Event()
        self.pause_event.set()  # 初期状態は「実行許可」

        self.base_points = None

        # ロジッククラス互換用ダミー
        self.homing_button = DummyWidget()
        self.z_origin_btn = DummyWidget()

        # ロジッククラスの初期化
        self.logic = WeldingControlLogic(self)

        # =================================================================
        # グリッドレイアウトの設定 (3行 x 2列)
        # =================================================================
        self.columnconfigure(0, weight=1)  # 左列
        self.columnconfigure(1, weight=1)  # 右列

        self.rowconfigure(0, weight=0)  # 上段 (設定・原点調整) 固定高さ
        self.rowconfigure(1, weight=1)  # 中段 (グラフ) 伸縮
        self.rowconfigure(2, weight=0)  # 下段 (ログ・Z軸・一時停止・実行) 固定高さ

        # =================================================================
        # 上段 (Row 0)
        # =================================================================

        # --- 左上: 設定情報 ---
        top_left_container = tk.Frame(self)
        top_left_container.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        tk.Button(top_left_container, text="<< DXF編集に戻る",
                  command=lambda: controller.show_page("PageDxfEditor"),
                  bg="#e0e0e0").pack(anchor='w', pady=(0, 5))

        info_frame = ttk.LabelFrame(top_left_container, text="設定情報")
        info_frame.pack(fill='both', expand=True)

        self.lbl_preset = tk.Label(info_frame, text="プリセット: ---", font=("Arial", 11, "bold"), fg="blue")
        self.lbl_preset.pack(anchor='w', padx=10, pady=2)
        self.lbl_points = tk.Label(info_frame, text="点数: 0", font=("Arial", 11))
        self.lbl_points.pack(anchor='w', padx=10, pady=2)

        # --- 右上 & 中央上: 原点位置の調整 (XYのみ) ---
        jog_frame = ttk.LabelFrame(self, text="溶着エリアの移動 (データシフト)")
        jog_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

        self.btn_homing_top = tk.Button(jog_frame, text="XY原点復帰 (ロック解除)", bg="orange",
                                        font=("Arial", 10, "bold"),
                                        command=self.logic.run_homing_sequence)
        self.btn_homing_top.pack(fill='x', padx=20, pady=(5, 10))

        jog_inner = tk.Frame(jog_frame)
        jog_inner.pack(fill='both', expand=True, padx=5, pady=5)

        # 1. XY操作
        xy_panel = tk.LabelFrame(jog_inner, text="XY軸(水平)")
        xy_panel.pack(side='left', fill='y', padx=5)

        self._create_mini_jog(xy_panel, "x", "X軸")
        self._create_mini_jog(xy_panel, "y", "Y軸")

        step_f = tk.Frame(xy_panel)
        step_f.pack(pady=5)
        tk.Label(step_f, text="移動距離(mm):").pack(side='left')
        self.step_entries['x'] = tk.Entry(step_f, width=5, justify='center')
        self.step_entries['x'].insert(0, "1.0")
        self.step_entries['x'].pack(side='left')
        self.step_entries['y'] = self.step_entries['x']

        # 2. データ操作ボタン群
        ops_frame = tk.Frame(jog_inner)
        ops_frame.pack(side='left', fill='both', expand=True, padx=10)

        # シフトボタン
        f_shift = tk.Frame(ops_frame)
        f_shift.pack(side='left', fill='both', expand=True, padx=2)
        tk.Label(f_shift, text="現在位置を加算", font=("Arial", 8)).pack()
        btn_shift = tk.Button(f_shift, text="位置シフト", bg="lightblue", font=("Arial", 10, "bold"),
                              command=self.shift_data_by_current_pos)
        btn_shift.pack(fill='both', expand=True, pady=2)
        self.jog_buttons.append(btn_shift)

        # XY入れ替えボタン
        f_swap = tk.Frame(ops_frame)
        f_swap.pack(side='left', fill='both', expand=True, padx=2)
        tk.Label(f_swap, text="XY座標入替", font=("Arial", 8)).pack()
        btn_swap = tk.Button(f_swap, text="XY入替", bg="lightblue", font=("Arial", 10, "bold"),
                             command=self.swap_xy_coordinates)
        btn_swap.pack(fill='both', expand=True, pady=2)
        self.jog_buttons.append(btn_swap)

        # =================================================================
        # 中段 (Row 1) - Preview
        # =================================================================
        self.plot_frame = tk.Frame(self, bg="white", relief="sunken", bd=1)
        self.plot_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        self.canvas = None

        # =================================================================
        # 下段 (Row 2) - 4カラム構成に変更 (ログ | Z軸 | 一時停止 | 実行)
        # =================================================================
        bottom_container = tk.Frame(self)
        bottom_container.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)

        bottom_container.columnconfigure(0, weight=1)  # ログ (伸縮)
        bottom_container.columnconfigure(1, weight=0)  # Z軸
        bottom_container.columnconfigure(2, weight=0)  # ★追加: 一時停止
        bottom_container.columnconfigure(3, weight=0)  # 実行

        # --- 左下: ログ ---
        log_frame = ttk.LabelFrame(bottom_container, text="ログ")
        log_frame.grid(row=0, column=0, sticky="nsew", padx=5)

        self.log_text = tk.Text(log_frame, height=6, state='disabled', bg='black', fg='lightgray', font=("Courier", 9))
        self.log_text.pack(fill='both', expand=True, padx=5, pady=5)

        # --- 真ん中1: Z軸コントロール ---
        z_frame = ttk.LabelFrame(bottom_container, text="Z軸(高さ)")
        z_frame.grid(row=0, column=1, sticky="nsew", padx=5)

        z_inner = tk.Frame(z_frame)
        z_inner.pack(padx=5, pady=5)

        btn_frame = tk.Frame(z_inner)
        btn_frame.pack(pady=2)
        btn_z_up = tk.Button(btn_frame, text="UP ▲", command=lambda: self.logic.move_axis('z', -1))
        btn_z_up.pack(side='left', padx=2)
        self.jog_buttons.append(btn_z_up)

        self.step_entries['z'] = tk.Entry(btn_frame, width=5, justify='center')
        self.step_entries['z'].insert(0, "5.0")
        self.step_entries['z'].pack(side='left', padx=2)

        btn_z_down = tk.Button(btn_frame, text="DOWN ▼", command=lambda: self.logic.move_axis('z', 1))
        btn_z_down.pack(side='left', padx=2)
        self.jog_buttons.append(btn_z_down)

        pulse_frame = tk.Frame(z_inner)
        pulse_frame.pack(pady=5)
        tk.Label(pulse_frame, text="Pulse:").pack(side='left')
        self.step_entries['z_pulse'] = tk.Entry(pulse_frame, width=6)
        self.step_entries['z_pulse'].insert(0, str(getattr(config, 'SAFE_Z_PULSE', 2100)))
        self.step_entries['z_pulse'].pack(side='left', padx=2)
        btn_z_go = tk.Button(pulse_frame, text="Go", command=self.logic.run_set_z_pulse, width=3)
        btn_z_go.pack(side='left')
        self.jog_buttons.append(btn_z_go)

        # --- ★追加: 一時停止・再開エリア ---
        pause_frame = ttk.LabelFrame(bottom_container, text="一時停止/再開")
        pause_frame.grid(row=0, column=2, sticky="nsew", padx=5)

        # アイコン的に分かりやすい色分け
        tk.Button(pause_frame, text="一時停止\n(Pause)", bg="yellow", width=10, height=2,
                  command=self.pause_job).pack(pady=5, padx=10, fill='x')

        tk.Button(pause_frame, text="再開\n(Resume)", bg="#90ee90", width=10, height=2,
                  command=self.resume_job).pack(pady=5, padx=10, fill='x')

        # --- 右下: 実行操作 ---
        exec_frame = ttk.LabelFrame(bottom_container, text="実行操作")
        exec_frame.grid(row=0, column=3, sticky="nsew", padx=5)

        self.btn_homing_bottom = tk.Button(exec_frame, text="XY原点復帰 (ロック解除)", bg="orange",
                                           font=("Arial", 10, "bold"),
                                           command=self.logic.run_homing_sequence)
        self.btn_homing_bottom.pack(fill='x', padx=10, pady=(5, 5))

        btn_area = tk.Frame(exec_frame)
        btn_area.pack(fill='x', pady=5, padx=5)

        btn_preview = tk.Button(btn_area, text="動作プレビュー\n(溶着なし)",
                                command=self.run_dry_run_preview)
        btn_preview.pack(side='left', fill='both', expand=True, padx=5)
        self.jog_buttons.append(btn_preview)

        self.start_btn = tk.Button(btn_area, text="★ 溶着開始 ★", bg="red", fg="white", font=("Arial", 12, "bold"),
                                   height=2, command=self.start_real_welding)
        self.start_btn.pack(side='left', fill='both', expand=True, padx=5)
        self.jog_buttons.append(self.start_btn)

        safe_area = tk.Frame(exec_frame)
        safe_area.pack(fill='x', pady=5, padx=5)

        self.stop_btn = tk.Button(safe_area, text="緊急停止", bg="red", fg="white", font=("Arial", 9, "bold"),
                                  command=self.on_emergency_stop)
        self.stop_btn.pack(side='left', fill='x', expand=True, padx=2)

        self.recover_btn = tk.Button(safe_area, text="復帰", command=self.on_recovery, state='disabled')
        self.recover_btn.pack(side='left', fill='x', expand=True, padx=2)

        self.status_label = tk.Label(safe_area, text="待機中", anchor='w')
        self.status_label.pack(side='left', padx=5)

        self.homing_button = ButtonGroup(self.btn_homing_top, self.btn_homing_bottom)

        self.active_preset = {}
        self._init_preset()
        self.update_lock_state()

    def update_lock_state(self):
        if self.motion and self.motion.is_homed:
            state = 'normal'
        else:
            state = 'disabled'
        for b in self.jog_buttons:
            try:
                b.config(state=state)
            except:
                pass

    def _init_preset(self):
        default_name = getattr(config, 'DEFAULT_PRESET_NAME', None)
        if default_name and default_name in presets.WELDING_PRESETS:
            self.active_preset = presets.WELDING_PRESETS[default_name]
        elif len(presets.WELDING_PRESETS) > 0:
            self.active_preset = presets.WELDING_PRESETS[list(presets.WELDING_PRESETS.keys())[0]]

    def on_page_show(self):
        if self.motion:
            self.motion.log = self.add_log
        p_name = self.controller.shared_data.get('preset_name', 'Unknown')
        points = self.controller.shared_data.get('weld_points', [])
        is_shifted = self.controller.shared_data.get('is_shifted', False)
        if not is_shifted or self.base_points is None:
            self.base_points = copy.deepcopy(points)
            self.controller.shared_data['is_shifted'] = False

        self.lbl_preset.config(text=f"プリセット: {p_name}")
        self.lbl_points.config(text=f"点数: {len(points)} 点")

        if p_name in presets.WELDING_PRESETS:
            self.active_preset = presets.WELDING_PRESETS[p_name]

        self.draw_preview(points)
        self.update_lock_state()

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

        max_x = getattr(config, 'MACHINE_MAX_X_MM', 700.0)
        max_y = getattr(config, 'MACHINE_MAX_Y_MM', 500.0)
        ax.set_xlim(0, max_x)
        ax.set_ylim(0, max_y)

        span = max(max_x, max_y)
        if span > 0:
            s_size = 2000.0 / span
        else:
            s_size = 20.0
        s_size = max(1.0, min(s_size, 50.0))

        if points:
            x_vals = [float(p['x']) for p in points]
            y_vals = [float(p['y']) for p in points]

            ax.plot(x_vals, y_vals, 'b-', alpha=0.3, label='Path Order')
            ax.scatter(x_vals, y_vals, c='red', s=s_size, zorder=5, label='Weld Points')
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

    def shift_data_by_current_pos(self):
        if not self.motion:
            messagebox.showerror("エラー", "モーションシステムが接続されていません。")
            return

        if self.base_points is None:
            self.base_points = copy.deepcopy(self.controller.shared_data.get('weld_points', []))

        dx = self.motion.current_pos.get('x', 0.0)
        dy = self.motion.current_pos.get('y', 0.0)

        if dx == 0 and dy == 0:
            msg = "現在位置が原点(0, 0)です。\nデータを初期位置（オフセットなし）に戻しますか？"
        else:
            msg = f"現在のデータ位置を\n X: +{dx:.2f} mm\n Y: +{dy:.2f} mm\nの位置に合わせますか？\n(基準データ + 現在値 で再設定します)"

        if not messagebox.askyesno("確認", msg):
            return

        new_points = []
        for p in self.base_points:
            new_points.append({
                'x': float(p['x']) + dx,
                'y': float(p['y']) + dy
            })

        self.controller.shared_data['weld_points'] = new_points
        self.controller.shared_data['is_shifted'] = True

        if dx == 0 and dy == 0:
            self.add_log("データを初期位置に戻しました。")
        else:
            self.add_log(f"データを位置合わせしました: Base + (X{dx:.2f}, Y{dy:.2f})")

        self.draw_preview(new_points)

    def swap_xy_coordinates(self):
        points = self.controller.shared_data.get('weld_points', [])
        if not points:
            return

        if not messagebox.askyesno("確認", "全ての点のX座標とY座標を入れ替えますか？\n(グラフが更新されます)"):
            return

        new_points = []
        for p in points:
            new_points.append({
                'x': float(p['y']),
                'y': float(p['x'])
            })

        self.controller.shared_data['weld_points'] = new_points

        if hasattr(self, 'base_points') and self.base_points:
            base_new = []
            for p in self.base_points:
                base_new.append({'x': float(p['y']), 'y': float(p['x'])})
            self.base_points = base_new

        self.add_log("XY座標を入れ替えました。")
        self.draw_preview(new_points)

    # =======================================================
    # ★追加: 一時停止・再開メソッド
    # =======================================================
    def pause_job(self):
        """一時停止ボタンが押されたとき"""
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.add_log("--- 一時停止要求 ---")
            self.add_log("現在の溶着サイクル終了後に停止します...")
            self.status_label.config(text="一時停止中 (待機)", fg="orange")
        else:
            self.add_log("既に一時停止中です。")

    def resume_job(self):
        """再開ボタンが押されたとき"""
        if not self.pause_event.is_set():
            self.pause_event.set()
            self.add_log("--- 再開 ---")
            self.status_label.config(text="実行中", fg="black")
        else:
            self.add_log("停止していません。")

    def start_real_welding(self):
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
        self.pause_event.set()  # 開始時は必ず実行許可状態にする
        self.status_label.config(text="実行中", fg="black")

        t = threading.Thread(target=self._welding_flow_absolute_thread, args=(points,))
        t.daemon = True
        t.start()

    def _welding_flow_absolute_thread(self, points):
        try:
            self.add_log("--- 溶着プロセス開始 (絶対座標モード) ---")

            work_origin = (0.0, 0.0)
            if not run_preview(self.motion, points, work_origin, self.active_preset):
                self.add_log("プレビューチェックでエラー検出。停止します。")
                return

            if self.stop_event.is_set():
                self.add_log("中断されました。")
                return

            self.add_log(f"--- 溶着ジョブ実行 ({len(points)}点) ---")

            self.motion.move_z_abs_pulse(config.SAFE_Z_PULSE)

            # 現在位置を初期化（距離計算用）
            current_x = self.motion.current_pos.get('x', 0.0)
            current_y = self.motion.current_pos.get('y', 0.0)

            for i, p in enumerate(points):
                # ★追加: 一時停止チェック（ループの頭で確認）
                if not self.pause_event.is_set():
                    self.add_log(f"[{i + 1}/{len(points)}] 一時停止中... (Z軸退避済み)")
                    # 待機ループ (緊急停止も監視)
                    while not self.pause_event.is_set():
                        if self.stop_event.is_set():
                            self.add_log("一時停止中に緊急停止されました。")
                            return
                        time.sleep(0.1)
                    self.add_log(f"[{i + 1}/{len(points)}] 処理を再開します。")

                if self.stop_event.is_set():
                    self.add_log("中断されました。緊急停止します。")
                    return

                target_x = float(p['x'])
                target_y = float(p['y'])

                # ★距離によるモード判定
                dist = math.hypot(target_x - current_x, target_y - current_y)
                is_precise = (dist >= 5.0)  # 5mm以上なら厳密停止（プレビューと同じ）

                self.add_log(f"({i + 1}/{len(points)}) 移動: X={target_x:.2f}, Y={target_y:.2f}")

                # ★移動命令 (precise_modeを指定)
                self.motion.move_xy_abs(target_x, target_y, self.active_preset, precise_mode=is_precise)

                # 現在位置を更新
                current_x = target_x
                current_y = target_y

                if i == 0:
                    time.sleep(1)

                self.motion.execute_welding_press(self.welder, self.active_preset)

            # ループを完走した場合のみ原点復帰を行う
            if not self.stop_event.is_set():
                self.add_log("--- 溶着ジョブ完了 ---")
                self.motion.return_to_origin()
                self.status_label.config(text="待機中", fg="black")
            else:
                self.add_log("緊急停止状態のため、原点復帰をスキップします。")

        except Exception as e:
            # ★詳細なエラー情報をコンソールに出力
            traceback.print_exc()
            # ログにも表示
            err_msg = f"エラー発生: {e}\n{traceback.format_exc()}"
            self.add_log(err_msg)
            messagebox.showerror("実行時エラー", str(e))
            self.status_label.config(text="エラー停止", fg="red")

    def run_dry_run_preview(self):
        self.add_log("動作プレビューは未実装です（範囲チェックのみ実行されます）")
        points = self.controller.shared_data.get('weld_points', [])
        run_preview(self.motion, points, (0, 0), self.active_preset)

    def on_emergency_stop(self):
        self.stop_event.set()
        # 念のためpause_eventもsetして待機ループを抜けさせる（緊急停止処理を優先）
        self.pause_event.set()
        self.logic.on_emergency_stop()
        self.status_label.config(text="緊急停止", fg="red")

    def on_recovery(self):
        self.stop_event.clear()
        self.pause_event.set()
        self.logic.on_recovery()
        self.status_label.config(text="待機中", fg="black")

    def add_log(self, msg):
        if hasattr(self, 'log_text') and self.log_text.winfo_exists():
            self.log_text.config(state='normal')
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state='disabled')
        else:
            print(msg)