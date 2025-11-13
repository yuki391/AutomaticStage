# page_welding_control.py

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os
import time

from motion_system import MotionSystem
from procedures import run_tilt_calibration, teach_origin_by_jog, run_preview
from csv_handler import load_path_from_csv
from io_controller import SensorController, WelderController
from myADconvert import ADfunc
import config
import presets


class PageWeldingControl(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.stop_event = threading.Event()
        self.is_moving = False

        # ハードウェアオブジェクトを最初にNoneで初期化する
        self.motion = None
        self.welder = None
        self.sensors = None
        self.dio = None

        # プリセットファイルにデフォルト名が存在するか確認
        if hasattr(config, 'DEFAULT_PRESET_NAME') and config.DEFAULT_PRESET_NAME in presets.WELDING_PRESETS:
            self.active_preset = presets.WELDING_PRESETS[config.DEFAULT_PRESET_NAME].copy()
        else:
            # 存在しない場合、リストの最初のプリセットを使用する
            first_preset_name = list(presets.WELDING_PRESETS.keys())[0]
            self.active_preset = presets.WELDING_PRESETS[first_preset_name].copy()
            # configに属性がない場合も考慮して、共有データ用に名前を設定
            if not hasattr(config, 'DEFAULT_PRESET_NAME'):
                config.DEFAULT_PRESET_NAME = first_preset_name

        main_frame = tk.Frame(self, padx=10, pady=10)
        main_frame.pack(fill='both', expand=True)

        # --- 操作フレーム ---
        op_frame = tk.Frame(main_frame)
        op_frame.pack(fill='x', pady=5)
        self.start_btn = tk.Button(op_frame, text="① 溶着開始フロー", command=self.start_welding_flow)
        self.start_btn.pack(side='left', padx=5, pady=5)
        self.load_btn = tk.Button(op_frame, text="CSVから経路読込", command=self.load_from_csv)
        self.load_btn.pack(side='left', padx=5, pady=5)
        back_btn = tk.Button(op_frame, text="<< DXF編集ページに戻る",
                             command=lambda: controller.show_page("PageDxfEditor"))
        back_btn.pack(side='right', padx=5, pady=5)

        # プリセット選択UI
        preset_frame = ttk.LabelFrame(main_frame, text="溶着設定プリセット")
        preset_frame.pack(fill='x', pady=5, padx=5)

        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(preset_frame, textvariable=self.preset_var, state='readonly', width=30)
        self.preset_combo.pack(side='left', padx=10, pady=10)

        preset_names = list(presets.WELDING_PRESETS.keys())
        self.preset_combo['values'] = preset_names

        self.preset_var.set(preset_names[0])

        self.preset_combo.bind('<<ComboboxSelected>>', self.on_preset_selected)

        # --- キャリブレーションフレーム ---
        calib_container = tk.Frame(main_frame)
        calib_container.pack(fill='x', pady=5)
        calib_frame = ttk.LabelFrame(calib_container, text="傾斜キャリブレーション")
        calib_frame.pack(side='left', fill='x', expand=True, padx=5)
        self.calib_points_var = tk.StringVar(value="3")
        rb3 = ttk.Radiobutton(calib_frame, text="3点測定", variable=self.calib_points_var, value="3")
        rb3.pack(side='left', padx=5)
        rb16 = ttk.Radiobutton(calib_frame, text="16点測定", variable=self.calib_points_var, value="16")
        rb16.pack(side='left', padx=5)
        self.calib_start_btn = tk.Button(calib_frame, text="開始", command=self.run_calibration)
        self.calib_start_btn.pack(side='left', padx=10)
        dist_calib_frame = ttk.LabelFrame(calib_container, text="距離キャリブレーション")
        dist_calib_frame.pack(side='left', fill='x', expand=True, padx=5)
        self.calib_axis_var = tk.StringVar(value="x")
        axis_menu = ttk.OptionMenu(dist_calib_frame, self.calib_axis_var, "x", "x", "y")
        axis_menu.pack(side='left', padx=5)
        tk.Label(dist_calib_frame, text="目標:").pack(side='left')
        self.target_dist_entry = tk.Entry(dist_calib_frame, width=8);
        self.target_dist_entry.insert(0, "500.0")
        self.target_dist_entry.pack(side='left')
        move_btn = tk.Button(dist_calib_frame, text="移動", command=self.run_calib_move)
        move_btn.pack(side='left', padx=5)
        tk.Label(dist_calib_frame, text="実測:").pack(side='left')
        self.actual_dist_entry = tk.Entry(dist_calib_frame, width=8)
        self.actual_dist_entry.pack(side='left')
        calc_btn = tk.Button(dist_calib_frame, text="適用", command=self.calculate_and_apply)
        calc_btn.pack(side='left', padx=5)

        # --- 手動操作フレーム ---
        manual_frame = ttk.LabelFrame(main_frame, text="手動操作")
        manual_frame.pack(fill='x', pady=10, padx=5)
        manual_btn_frame = tk.Frame(manual_frame)
        manual_btn_frame.pack(pady=5)
        self.homing_button = tk.Button(manual_btn_frame, text="XY原点復帰", command=self.run_homing_sequence)
        self.homing_button.pack(side='left', padx=10)
        self.z_origin_btn = tk.Button(manual_btn_frame, text="Z軸の現在地を原点に",
                                      command=self.run_set_z_origin)
        self.z_origin_btn.pack(side='left', padx=10)

        self.step_entries = {}
        self.jog_buttons = []
        self.create_position_control(manual_frame, "X軸", "mm", "x")
        self.create_position_control(manual_frame, "Y軸", "mm", "y")
        self.create_z_control(manual_frame)

        # --- 緊急停止とログ ---
        bottom_frame = tk.Frame(main_frame)
        bottom_frame.pack(fill='both', expand=True)
        stop_btn_frame = tk.Frame(bottom_frame);
        stop_btn_frame.pack(fill='x', pady=10)
        self.stop_btn = tk.Button(stop_btn_frame, text="緊急停止", bg="red", fg="white", font=("メイリオ", 10, "bold"),
                                  command=self.on_emergency_stop)
        self.stop_btn.pack(side='left', padx=5)
        self.recover_btn = tk.Button(stop_btn_frame, text="復帰", command=self.on_recovery, state='disabled')
        self.recover_btn.pack(side='left', padx=5)
        self.status_label = tk.Label(bottom_frame, text="待機中", anchor='w');
        self.status_label.pack(fill='x')
        log_frame = ttk.LabelFrame(bottom_frame, text="ログ");
        log_frame.pack(fill='both', expand=True, pady=5)
        self.log_text = tk.Text(log_frame, height=10, state='disabled', bg='black', fg='lightgray', font=("Courier", 9))
        self.log_text.pack(fill='both', expand=True, padx=5, pady=5)

        # --- ハードウェア初期化 ---
        self.add_log("ハードウェアを初期化しています...")
        try:
            self.dio = ADfunc('DIO')
            if not self.dio.init("DIO000"):
                messagebox.showerror("ハードウェアエラー", "CONTEC DIOボードの初期化に失敗しました。");
                return
            self.motion = MotionSystem(log_callback=self.add_log)
            self.welder = WelderController(self.dio, log_callback=self.add_log)
            self.sensors = {
                'x': SensorController(self.dio, config.LIMIT_SWITCH_X_PIN, log_callback=self.add_log),
                'y': SensorController(self.dio, config.LIMIT_SWITCH_Y_PIN, log_callback=self.add_log)
            }
            self.add_log("ハードウェアの初期化が完了しました。")
            self.add_log(f"デフォルトの溶着設定「{config.DEFAULT_PRESET_NAME}」を読み込みました。")
            self.run_in_thread(self._initial_z_retract_thread)

        except Exception as e:
            messagebox.showerror("初期化エラー", f"ハードウェアの初期化中にエラーが発生しました:\n{e}")
            self.add_log(f"!!! 初期化エラー: {e}")
        self.add_log("警告: 原点復帰が未完了です。最初の手動操作は意図しない動きをする可能性があります。")

    def _initial_z_retract_thread(self):
        self.add_log("--- Z軸を安全な高さへ移動させています... ---")
        if self.motion:
            self.motion.move_z_abs_pulse(config.SAFE_Z_PULSE)
            self.add_log("--- Z軸の初期位置決め完了 ---")
        else:
            self.add_log("--- Z軸移動スキップ（モーションシステム未初期化） ---")

    def on_preset_selected(self, event=None):
        preset_name = self.preset_var.get()
        self.active_preset = presets.WELDING_PRESETS[preset_name].copy()
        self.controller.shared_data['preset_name'] = preset_name
        self.add_log(f"溶着設定を「{preset_name}」に変更しました。")
        self.add_log(
            f"  速度: {self.active_preset['velocity_xy']}, 加速度: {self.active_preset['acceleration_xy']}, 溶着時間: {self.active_preset['weld_time']}s")

    def on_page_show(self):
        shared_preset_name = self.controller.shared_data.get('preset_name')
        if shared_preset_name and shared_preset_name in self.preset_combo['values']:
            self.preset_var.set(shared_preset_name)
            self.on_preset_selected()

        self.run_in_thread(self.check_motor_connection)

    def check_motor_connection(self):
        self.add_log("モーターとの接続を確認しています...")
        if not self.motion:
            self.add_log("!!! エラー: モーションシステムが初期化されていません。")
            return
        if not self.motion.check_connection('x'):
            self.add_log("!!! 警告: モーターからの応答がありません。")
        else:
            self.add_log("モーターとの接続は正常です。")

    def start_welding_flow(self):
        if not self.motion: messagebox.showerror("エラー", "モーションシステムが初期化されていません。"); return
        points = self.controller.shared_data.get('weld_points')
        if not points: messagebox.showwarning("データなし", "溶着データがありません。"); return
        self.stop_event.clear();
        self.run_in_thread(self._welding_flow_thread, points)

    def _welding_flow_thread(self, points):
        try:
            self.add_log("--- 溶着プロセス開始 ---")
            self.motion.home_all_axes(self.sensors)
            if self.stop_event.is_set():
                self.add_log("中断されました。")
                return

            work_origin = teach_origin_by_jog(self.motion)
            if work_origin is None or self.stop_event.is_set():
                self.add_log("中断されました。")
                return

            # 最初のプレビュー実行
            if not run_preview(self.motion, points, work_origin, self.active_preset):
                self.add_log("プレビューに失敗したため、フローを停止します。")
                return
            if self.stop_event.is_set():
                self.add_log("中断されました。")
                return

            # ユーザーに「開始 / もう一回プレビュー / 中止」を選ばせるループ
            while True:
                ans = messagebox.askyesnocancel(
                    "最終確認",
                    "プレビューが完了しました。\nこの位置で溶着を開始しますか？\n\n"
                    "「はい」: 溶着開始\n"
                    "「いいえ」: もう一回プレビューを表示\n"
                    "「キャンセル」: 中止"
                )
                # ans == True  -> はい（開始）
                # ans == False -> いいえ（もう一回プレビュー）
                # ans == None  -> キャンセル（中止）
                if ans is True:
                    # ユーザーが開始を選択したのでループを抜けて実行へ
                    break
                elif ans is False:
                    # もう一回プレビューを実行
                    self.add_log("ユーザー操作: もう一回プレビューを表示します。")
                    ok = run_preview(self.motion, points, work_origin, self.active_preset)
                    if not ok:
                        self.add_log("プレビューに失敗したため、フローを停止します。")
                        return
                    if self.stop_event.is_set():
                        self.add_log("中断されました。")
                        return
                    # ループして再度確認ダイアログへ
                    continue
                else:
                    # キャンセル（中止）
                    self.add_log("ユーザーにより操作が中断されました。")
                    return

            # ユーザーが「開始」を選択したので溶着ジョブを実行
            self.add_log(f"--- 溶着ジョブ開始 ({len(points)}点) ---")
            for i, p in enumerate(points):
                if self.stop_event.is_set():
                    self.add_log("中断されました。")
                    return

                target_x = work_origin[0] + p['x']
                target_y = work_origin[1] + p['y']



                self.add_log(f"({i + 1}/{len(points)}) 点へ移動: X={target_x:.2f}, Y={target_y:.2f}")

                self.motion.move_xy_abs(target_x, target_y, self.active_preset)

                if i == 0:
                    self.add_log("-> 初回移動のため1秒待機します。")
                    time.sleep(1)
                self.motion.execute_welding_press(self.welder, self.active_preset)

            self.add_log("--- 溶着ジョブ完了 ---")
            self.motion.return_to_origin()

        except Exception as e:
            self.add_log(f"エラーが発生しました: {e}")
            messagebox.showerror("実行時エラー", f"ジョブ実行中にエラーが発生しました:\n{e}")

    def create_position_control(self, parent, label_text, unit, axis):
        frame = ttk.LabelFrame(parent, text=label_text)
        frame.pack(fill='x', padx=10, pady=5)
        minus_btn = tk.Button(frame, text="-", width=5, font=("Arial", 12, "bold"),
                              command=lambda: self.move_axis(axis, -1))
        minus_btn.pack(side='left', padx=10, pady=5);
        self.jog_buttons.append(minus_btn)
        entry = tk.Entry(frame, width=10);
        entry.insert(0, "10.0");
        entry.pack(side='left', padx=5)
        self.step_entries[axis] = entry
        tk.Label(frame, text=unit).pack(side='left')
        plus_btn = tk.Button(frame, text="+", width=5, font=("Arial", 12, "bold"),
                             command=lambda: self.move_axis(axis, 1))
        plus_btn.pack(side='right', padx=10, pady=5);
        self.jog_buttons.append(plus_btn)

    def create_z_control(self, parent):
        axis = 'z'
        frame = ttk.LabelFrame(parent, text="Z軸")
        frame.pack(fill='x', padx=10, pady=5)

        pos_frame = tk.Frame(frame);
        pos_frame.pack(fill='x', pady=2)
        tk.Label(pos_frame, text="位置制御:", width=10, anchor='w').pack(side='left')
        minus_btn = tk.Button(pos_frame, text="▲ UP", width=8, command=lambda: self.move_axis(axis, -1))
        minus_btn.pack(side='left', padx=(10, 0));
        self.jog_buttons.append(minus_btn)
        entry = tk.Entry(pos_frame, width=8);
        entry.insert(0, "5.0");
        entry.pack(side='left', padx=5)
        self.step_entries[axis] = entry
        tk.Label(pos_frame, text="mm").pack(side='left')
        plus_btn = tk.Button(pos_frame, text="DOWN ▼", width=8, command=lambda: self.move_axis(axis, 1))
        plus_btn.pack(side='left', padx=5);
        self.jog_buttons.append(plus_btn)

        # --- 追加: パルス位置直接入力（絶対移動） ---
        pulse_frame = tk.Frame(frame)
        pulse_frame.pack(fill='x', pady=2)
        tk.Label(pulse_frame, text="パルス制御:", width=10, anchor='w').pack(side='left')
        pulse_entry = tk.Entry(pulse_frame, width=12)
        pulse_entry.insert(0, str(config.SAFE_Z_PULSE))  # 初期値を安全位置（2100 等）に
        pulse_entry.pack(side='left', padx=5)
        self.step_entries['z_pulse'] = pulse_entry
        goto_pulse_btn = tk.Button(pulse_frame, text="Goto Pulse", command=self.run_set_z_pulse)
        goto_pulse_btn.pack(side='left', padx=6)

        # 電流制御と停止などの既存UI
        cur_frame = tk.Frame(frame);
        cur_frame.pack(fill='x', pady=2)
        tk.Label(cur_frame, text="電流制御:", width=10, anchor='w').pack(side='left')
        tk.Label(cur_frame, text="電流(mA):").pack(side='left', padx=(10, 0))
        cur_entry = tk.Entry(cur_frame, width=8);
        cur_entry.insert(0, "50");
        cur_entry.pack(side='left')
        self.step_entries[f"{axis}_adv_cur"] = cur_entry
        up_btn = tk.Button(cur_frame, text="▲ UP", command=lambda: self.set_current_only_move(axis, -1))
        up_btn.pack(side='left', padx=5);
        self.jog_buttons.append(up_btn)
        down_btn = tk.Button(cur_frame, text="DOWN ▼", command=lambda: self.set_current_only_move(axis, 1))
        down_btn.pack(side='left', padx=5);
        self.jog_buttons.append(down_btn)
        stop_btn = tk.Button(cur_frame, text="停止", bg="yellow", command=lambda: self.stop_continuous(axis))
        stop_btn.pack(side='left', padx=5);
        self.jog_buttons.append(stop_btn)

    def run_set_z_pulse(self):
        """UIから呼ばれる：エントリのパルス値へ移動（スレッドで実行）"""
        if not self.motion:
            messagebox.showerror("エラー", "モーションシステムが初期化されていません。")
            return
        try:
            pulse_str = self.step_entries.get('z_pulse').get()
            pulse = int(float(pulse_str))
        except Exception:
            messagebox.showerror("入力エラー", "パルス位置には整数または数値を入力してください。")
            return
        if not messagebox.askyesno("確認", f"Z軸を絶対パルス位置 {pulse} に移動しますか？"):
            return
        self.run_in_thread(self._set_z_pulse_thread, pulse)

    def _set_z_pulse_thread(self, pulse):
        try:
            self.is_moving = True
            self.set_jog_buttons_state('disabled')
            self.homing_button.config(state='disabled')
            self.z_origin_btn.config(state='disabled')
            self.add_log(f"Z軸を絶対パルス位置 {pulse} へ移動します...")
            self.motion.move_z_abs_pulse(pulse)
            self.add_log("移動完了。")
        finally:
            self.is_moving = False
            self.set_jog_buttons_state('normal')
            self.homing_button.config(state='normal')
            self.z_origin_btn.config(state='normal')

    def set_jog_buttons_state(self, state):
        for btn in self.jog_buttons: btn.config(state=state)

    def add_log(self, message):
        if not self.winfo_exists(): return
        self.log_text.config(state='normal');
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END);
        self.log_text.config(state='disabled');
        self.update_idletasks()

    def update_status(self):
        self.status_label.config(
            text=f"読み込み済みの溶着点: {len(self.controller.shared_data.get('weld_points', []))} 点")

    def run_in_thread(self, target_func, *args):
        thread = threading.Thread(target=target_func, args=args);
        thread.daemon = True;
        thread.start()

    def on_emergency_stop(self):
        self.stop_event.set()
        if self.motion:
            self.motion.emergency_stop()

        if self.welder:
            self.welder.turn_off()
            self.add_log("!!! 溶着機をOFFにしました。 !!!")

        self.recover_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        messagebox.showwarning("緊急停止",
                               "全モーターのトルクがOFFになり、溶着機が停止しました。\n機械を手で安全な範囲に移動させた後、「復帰」ボタンを押してください。")

    def on_recovery(self):
        self.recover_btn.config(state='disabled');
        self.run_in_thread(self._recovery_thread)

    def _recovery_thread(self):
        if self.motion: self.motion.recover_from_stop()
        self.stop_event.clear();
        self.stop_btn.config(state='normal')
        self.add_log("復帰完了。待機状態に戻りました。")

    def run_calibration(self):
        if not self.motion: messagebox.showerror("エラー", "モーションシステムが初期化されていません。"); return
        num_points = int(self.calib_points_var.get())
        self.add_log(f"--- {num_points}点での傾斜キャリブレーションを開始します ---")
        self.run_in_thread(self._calibration_thread, num_points)

    def _calibration_thread(self, num_points):
        plane = run_tilt_calibration(self.motion, num_points, self.active_preset)
        if plane:
            self.motion.set_tilt_plane(plane);
            self.add_log("傾斜キャリブレーションが完了し、補正データを適用しました。")
        else:
            self.add_log("キャリブレーションが中止または失敗しました。")

    def load_from_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")]);
        if not path: return
        points = load_path_from_csv(path)
        if points:
            self.controller.shared_data['weld_points'] = points;
            self.update_status()
            self.add_log(f"CSVから {len(points)} 点を読み込みました。")

    def run_calib_move(self):
        if not self.motion: messagebox.showerror("エラー", "モーションシステムが初期化されていません。"); return
        if not self.motion.is_homed: messagebox.showerror("エラー", "最初に原点復帰を実行してください。"); return
        try:
            target_dist = float(self.target_dist_entry.get());
            axis = self.calib_axis_var.get()
            self.run_in_thread(self._calib_move_thread, axis, target_dist)
        except ValueError:
            messagebox.showerror("入力エラー", "目標距離には数値を入力してください。")

    def _calib_move_thread(self, axis, distance):
        self.add_log(f"--- 距離キャリブレーション: {axis.upper()}軸を +{distance}mm 移動します ---")
        if axis == 'x':
            self.motion.move_xy_rel(dx_mm=distance, dy_mm=0, preset=self.active_preset)
        elif axis == 'y':
            self.motion.move_xy_rel(dx_mm=0, dy_mm=distance, preset=self.active_preset)
        self.add_log("移動完了。実際の移動距離を測定し、入力してください。")

    def calculate_and_apply(self):
        """
        距離キャリブレーションの「適用」ボタンで呼ばれる関数。
        変更点:
          - 選択された軸（self.calib_axis_var）だけを補正するよう明確化。
          - 適用前に現在値と補正後の値をユーザーへ確認するダイアログを追加。
          - 適用処理は MotionSystem.update_pulses_per_mm(axis, new_value) に委譲し、
            その中で settings.json への永続化が行われる想定（既存の実装）。
        """
        if not self.motion:
            messagebox.showerror("エラー", "モーションシステムが初期化されていません。")
            return

        try:
            target_dist = float(self.target_dist_entry.get())
            actual_dist = float(self.actual_dist_entry.get())
        except ValueError:
            messagebox.showerror("入力エラー", "目標距離と実測値には数値を入力してください。")
            return

        if actual_dist == 0:
            messagebox.showerror("計算エラー", "実測値に0は入力できません。")
            return

        axis = self.calib_axis_var.get()  # 'x' または 'y'
        if axis not in ('x', 'y'):
            messagebox.showerror("エラー", f"未対応の軸が選択されています: {axis}")
            return

        # 現在の pulses_per_mm を取得
        if axis == 'x':
            current_ppm = self.motion.pulses_per_mm_x
        else:
            current_ppm = self.motion.pulses_per_mm_y

        correction_factor = target_dist / actual_dist
        new_ppm = current_ppm * correction_factor

        # ユーザー確認ダイアログを出す（変更が一目でわかるように）
        msg = (
            f"{axis.upper()}軸 距離キャリブレーションの適用\n\n"
            f"目標距離: {target_dist:.4f} mm\n"
            f"実測距離: {actual_dist:.4f} mm\n\n"
            f"補正係数: {correction_factor:.6f}\n"
            f"現在の pulses/mm: {current_ppm:.6f}\n"
            f"補正後の pulses/mm: {new_ppm:.6f}\n\n"
            "この変更を適用してよろしいですか？"
        )
        if not messagebox.askokcancel("適用の確認", msg):
            self.add_log("ユーザーがキャリブレーションの適用をキャンセルしました。")
            return

        # 実際に更新（MotionSystem 側で永続化される）
        try:
            self.motion.update_pulses_per_mm(axis, new_ppm)
            self.add_log(f"{axis.upper()}軸の pulses/mm を {current_ppm:.6f} -> {new_ppm:.6f} に更新しました。")
            messagebox.showinfo("適用完了", f"{axis.upper()}軸のキャリブレーションを適用しました。")
        except Exception as e:
            self.add_log(f"キャリブレーション適用中にエラーが発生しました: {e}")
            messagebox.showerror("適用エラー", f"キャリブレーションの適用に失敗しました:\n{e}")
    def move_axis(self, axis, direction):
        if not self.motion: messagebox.showerror("エラー", "モーションシステムが初期化されていません。"); return
        if self.is_moving: self.add_log("警告: 現在、別の移動命令を実行中です。"); return
        if axis in ['x', 'y'] and not self.motion.is_homed:
            self.add_log("エラー: XY軸を動かすには、先に「XY原点復帰」を実行してください。")
            messagebox.showerror("エラー", "機械のXY座標が不明です。\n最初に「XY原点復帰」を実行してください。");
            return
        try:
            step = float(self.step_entries[axis].get())
            amount = step * direction
            self.run_in_thread(self._move_thread, axis, amount)
        except ValueError:
            self.add_log("エラー: 移動量には数値を入力してください。")

    def _move_thread(self, axis, amount):
        try:
            self.is_moving = True;
            self.set_jog_buttons_state('disabled');
            self.homing_button.config(state='disabled');
            self.z_origin_btn.config(state='disabled')
            self.add_log(f"手動操作: {axis.upper()}軸を {amount:+.2f}mm 動かします...")
            if axis == "x":
                self.motion.move_xy_rel(dx_mm=amount, dy_mm=0, preset=self.active_preset)
            elif axis == "y":
                self.motion.move_xy_rel(dx_mm=0, dy_mm=amount, preset=self.active_preset)
            elif axis == "z":
                self.motion.move_z_rel(amount)
            self.add_log(f"完了: {axis.upper()}軸 移動完了。")
        finally:
            self.is_moving = False;
            self.set_jog_buttons_state('normal');
            self.homing_button.config(state='normal');
            self.z_origin_btn.config(state='normal')

    def run_homing_sequence(self):
        if not self.motion: messagebox.showerror("エラー", "モーションシステムが初期化されていません。"); return
        if self.is_moving: self.add_log("警告: 現在、別の移動命令を実行中です。"); return
        if messagebox.askyesno("確認", "XY原点復帰を開始します。\n機械周りに障害物がないか確認してください。"):
            self.run_in_thread(self._homing_thread)

    def _homing_thread(self):
        try:
            self.is_moving = True
            self.homing_button.config(state='disabled')
            self.z_origin_btn.config(state='disabled')
            self.set_jog_buttons_state('disabled')

            self.add_log("--- 原点復帰の前にZ軸を安全な高さへ移動します ---")
            self.motion.move_z_abs_pulse(config.SAFE_Z_PULSE)
            self.motion.home_all_axes(self.sensors)

            if self.motion.is_homed:
                self.set_jog_buttons_state('normal')
                self.add_log("原点復帰が完了しました。手動操作が可能です。")
        finally:
            self.is_moving = False
            self.homing_button.config(state='normal')
            self.z_origin_btn.config(state='normal')
            if self.motion and self.motion.is_homed: self.set_jog_buttons_state('normal')

    def run_set_z_origin(self):
        if not self.motion: messagebox.showerror("エラー", "モーションシステムが初期化されていません。"); return
        if self.is_moving: self.add_log("警告: 現在、別の移動命令を実行中です。"); return
        if messagebox.askyesno("確認", "現在のZ軸の位置を、新しい原点(0)として設定しますか？"):
            self.run_in_thread(self._set_z_origin_thread)

    def _set_z_origin_thread(self):
        try:
            self.is_moving = True
            self.set_jog_buttons_state('disabled');
            self.homing_button.config(state='disabled');
            self.z_origin_btn.config(state='disabled')
            self.motion.set_z_origin_here()
            self.add_log("Z軸の原点設定完了。")
        finally:
            self.is_moving = False
            self.homing_button.config(state='normal')
            self.z_origin_btn.config(state='normal')
            self.set_jog_buttons_state('normal')

    def set_current_only_move(self, axis, direction):
        if not self.motion: messagebox.showerror("エラー", "モーションシステムが初期化されていません。"); return
        if self.is_moving: self.add_log("警告: 別の移動命令が実行中です。"); return
        try:
            current = float(self.step_entries[f"{axis}_adv_cur"].get())
            self.run_in_thread(self._current_only_thread, axis, current * direction)
        except ValueError:
            self.add_log("エラー: 電流値には数値を入力してください。")

    def _current_only_thread(self, axis, current):
        try:
            self.is_moving = True;
            self.set_jog_buttons_state('disabled')
            self.motion.set_axis_current(axis, current)
        finally:
            self.is_moving = False;
            self.set_jog_buttons_state('normal')

    def stop_continuous(self, axis):
        if not self.motion: messagebox.showerror("エラー", "モーションシステムが初期化されていません。"); return
        if self.is_moving: self.add_log("警告: 別の移動命令が実行中です。"); return
        self.run_in_thread(self._stop_thread, axis)

    def _stop_thread(self, axis):
        try:
            self.is_moving = True;
            self.set_jog_buttons_state('disabled')
            self.motion.stop_continuous_move(axis)
        finally:
            self.is_moving = False;
            self.set_jog_buttons_state('normal')