import tkinter as tk
from tkinter import ttk
import ui_components
from page_welding_control_logic import WeldingControlLogic
import config
import presets


class PageManualControl(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # ハードウェア参照
        self.motion = self.controller.hardware['motion']
        self.dio = self.controller.hardware['dio']
        self.welder = self.controller.hardware['welder']
        self.sensors = self.controller.hardware['sensors']

        if self.motion:
            self.motion.log = self.add_log

        # 変数初期化
        self.is_moving = False
        self.step_entries = {}
        self.jog_buttons = []

        # Z軸位置表示用変数
        self.z_pos_var = tk.StringVar(value="Z軸現在地: --- mm")

        # プリセット読み込み
        self.active_preset = {}
        default_name = getattr(config, 'DEFAULT_PRESET_NAME', None)
        if default_name and default_name in presets.WELDING_PRESETS:
            self.active_preset = presets.WELDING_PRESETS[default_name]
        elif len(presets.WELDING_PRESETS) > 0:
            first_key = list(presets.WELDING_PRESETS.keys())[0]
            self.active_preset = presets.WELDING_PRESETS[first_key]
        else:
            self.active_preset = {
                'velocity_xy': 10, 'acceleration_xy': 10,
                'weld_pitch': 1.0, 'weld_current': 0, 'weld_time': 0, 'gentle_current': 0
            }

        # ロジッククラス
        self.logic = WeldingControlLogic(self)

        # --- UI構築 ---
        label = tk.Label(self, text="ステップ1: 初期設定・手動操作", font=("Arial", 16, "bold"))
        label.pack(pady=10)

        btn_next = tk.Button(self, text="次へ: 溶着データ作成 (DXF編集) >>",
                             bg="lightblue", font=("Arial", 12), height=2,
                             command=lambda: controller.show_page("PageDxfEditor"))
        btn_next.pack(pady=10)

        ui_components.create_calibration_widgets(self, self)
        ui_components.create_manual_control_widgets(self, self)
        ui_components.create_emergency_stop_widgets(self, self)

        # UI更新ループ開始
        self._start_ui_update_loop()

        if self.motion:
            # 現在のパルス位置を読み取ってオフセットに設定
            self.motion.set_z_origin_here()
            # ロジック側の「原点設定済み」フラグを立てる
            self.logic.is_z_homed = True
            self.add_log("起動時設定: 現在位置をZ軸原点(0.0)に設定しました。")

            # ▼▼▼ 追加: 起動時にZ軸を安全位置へ移動 (スレッド実行) ▼▼▼
            def startup_z_move():
                # 安全位置設定が config にあるか確認 (デフォルト値 2100)
                safe_pulse = getattr(config, 'SAFE_Z_PULSE', 2100)
                self.add_log(f"起動時: Z軸を安全位置({safe_pulse})へ移動します...")
                self.motion.move_z_abs_pulse(safe_pulse)
                self.add_log("起動時: Z軸移動完了")

            # Logicクラスの機能を使って別スレッドで実行（画面が固まらないようにする）
            self.logic.run_in_thread(startup_z_move)

    def on_page_show(self):
        # ページが表示されたときに、ログ出力先をこの画面に設定しなおす
        if self.motion:
            self.motion.log = self.add_log

    def _start_ui_update_loop(self):
        """Z軸の現在位置表示を定期的に更新する"""
        if self.motion and hasattr(self, 'z_pos_var'):
            # 原点復帰済みかどうかに関わらず、現在のパルスから計算した値を表示
            # (未復帰時は大きな値になる可能性がありますが、動きを確認するため表示)
            try:
                # MotionSystemのcurrent_posは移動完了時に更新されるが、
                # リアルタイム性を高めるなら直接読む手もある。
                # ここでは簡易的にmotion.current_posを使うか、
                # 以前のように直接read_present_positionするのが確実。
                # 今回は MotionSystem 内で管理されている current_pos['z'] を表示
                z_mm = self.motion.current_pos.get('z', 0.0)
                # 上方向を正とするか、下方向を正とするかはシステムによるが、
                # ここでは画面表示に合わせて符号を調整（例: 下降がプラスならそのまま）
                self.z_pos_var.set(f"Z軸現在地: {z_mm:.2f} mm")
            except Exception:
                pass

        if self.winfo_exists():
            self.after(300, self._start_ui_update_loop)

    # ---------------------------------------------------------
    # ui_components.py から呼び出されるウィジェット作成メソッド
    # ---------------------------------------------------------
    def create_position_control(self, parent, label_text, unit, axis):
        """X/Y軸などのシンプルな位置制御パネルを作成"""
        frame = ttk.LabelFrame(parent, text=label_text)
        frame.pack(fill='x', padx=10, pady=5)

        minus_btn = tk.Button(frame, text="-", width=5, font=("Arial", 12, "bold"),
                              command=lambda: self.move_axis(axis, -1))
        minus_btn.pack(side='left', padx=10, pady=5)
        self.jog_buttons.append(minus_btn)

        entry = tk.Entry(frame, width=10)
        entry.insert(0, "10.0")
        entry.pack(side='left', padx=5)
        self.step_entries[axis] = entry

        tk.Label(frame, text=unit).pack(side='left')

        plus_btn = tk.Button(frame, text="+", width=5, font=("Arial", 12, "bold"),
                             command=lambda: self.move_axis(axis, 1))
        plus_btn.pack(side='right', padx=10, pady=5)
        self.jog_buttons.append(plus_btn)

    def create_advanced_control(self, parent, label_text, unit, axis):
        """Z軸用の詳細制御パネルを作成"""
        frame = ttk.LabelFrame(parent, text=label_text)
        frame.pack(fill='x', padx=10, pady=5)

        # 1. 現在地モニター（ボタンの外に配置）
        if axis == 'z':
            monitor_frame = tk.Frame(frame)
            monitor_frame.pack(fill='x', pady=(5, 0), padx=5)
            # 青色で目立つように表示
            pos_label = tk.Label(monitor_frame, textvariable=self.z_pos_var,
                                 font=("Arial", 11, "bold"), fg="blue", bg="#f0f0f0", relief="solid", borderwidth=1)
            pos_label.pack(fill='x', padx=5)

        # 2. 位置制御 (相対移動)
        pos_frame = tk.Frame(frame)
        pos_frame.pack(fill='x', pady=5)
        tk.Label(pos_frame, text="相対移動:", width=12, anchor='w').pack(side='left')

        minus_btn = tk.Button(pos_frame, text="▲ UP (-)", width=8,
                              command=lambda: self.move_axis(axis, -1))
        minus_btn.pack(side='left', padx=(5, 0))
        self.jog_buttons.append(minus_btn)

        entry = tk.Entry(pos_frame, width=8)
        entry.insert(0, "5.0")
        entry.pack(side='left', padx=5)
        self.step_entries[axis] = entry

        tk.Label(pos_frame, text=unit).pack(side='left')

        plus_btn = tk.Button(pos_frame, text="DOWN ▼ (+)", width=8,
                             command=lambda: self.move_axis(axis, 1))
        plus_btn.pack(side='left', padx=5)
        self.jog_buttons.append(plus_btn)

        # 3. パルス制御 (絶対移動)
        if axis == 'z':
            pulse_frame = tk.Frame(frame)
            pulse_frame.pack(fill='x', pady=2)
            # ラベル幅を広げて見切れを防止
            tk.Label(pulse_frame, text="パルス指定:", width=12, anchor='w').pack(side='left')

            pulse_entry = tk.Entry(pulse_frame, width=12)
            default_pulse = getattr(config, 'SAFE_Z_PULSE', 2100)
            pulse_entry.insert(0, str(default_pulse))
            pulse_entry.pack(side='left', padx=5)
            self.step_entries['z_pulse'] = pulse_entry

            goto_pulse_btn = tk.Button(pulse_frame, text="移動 (Goto)",
                                       command=lambda: self.logic.run_set_z_pulse() if hasattr(self.logic,
                                                                                               'run_set_z_pulse') else print(
                                           "Not Implemented"))
            goto_pulse_btn.pack(side='left', padx=6)

            # 4. 電流制御
            cur_frame = tk.Frame(frame)
            cur_frame.pack(fill='x', pady=2)
            tk.Label(cur_frame, text="電流制御:", width=12, anchor='w').pack(side='left')

            cur_entry = tk.Entry(cur_frame, width=8)
            cur_entry.insert(0, "50")
            cur_entry.pack(side='left', padx=5)
            self.step_entries[f"{axis}_adv_cur"] = cur_entry
            tk.Label(cur_frame, text="mA").pack(side='left')

            up_btn = tk.Button(cur_frame, text="▲", width=4, command=lambda: self.set_current_only_move(axis, -1))
            up_btn.pack(side='left', padx=5)
            self.jog_buttons.append(up_btn)

            down_btn = tk.Button(cur_frame, text="▼", width=4, command=lambda: self.set_current_only_move(axis, 1))
            down_btn.pack(side='left', padx=2)
            self.jog_buttons.append(down_btn)

            stop_btn = tk.Button(cur_frame, text="停止", bg="yellow", command=lambda: self.stop_continuous(axis))
            stop_btn.pack(side='left', padx=10)
            self.jog_buttons.append(stop_btn)

    # --- Logicへの委譲メソッド ---
    def run_homing_sequence(self):
        self.logic.run_homing_sequence()

    def run_set_z_rot_origin(self):
        self.logic.run_set_z_origin()

    def move_axis(self, axis, direction):
        self.logic.move_axis(axis, direction)

    def run_calibration(self):
        self.logic.run_calibration()

    def run_calib_move(self):
        self.logic.run_calib_move()

    def calculate_and_apply(self):
        self.logic.calculate_and_apply()

    def on_emergency_stop(self):
        self.logic.on_emergency_stop()

    def on_recovery(self):
        self.logic.on_recovery()

    def set_current_only_move(self, axis, direction):
        self.logic.set_current_only_move(axis, direction)

    def stop_continuous(self, axis):
        self.logic.stop_continuous(axis)

    def add_log(self, msg):
        if hasattr(self, 'log_text'):
            self.log_text.config(state='normal')
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state='disabled')