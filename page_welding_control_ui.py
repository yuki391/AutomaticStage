import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import config
import presets


class WeldingControlUI:
    """
    UI構築専用クラス。

    このクラスは PageWeldingControl の UI 部分を切り出したもので、
    実際の動作（ロジック／ハードウェア操作）は親オブジェクト（main）側に委譲する。

    使い方例:
        ui = WeldingControlUI(parent_frame, controller, main)
        # main 側は start_welding_flow, load_from_csv, run_calibration などの
        # メソッドを実装している必要がある。
    """

    def __init__(self, parent, controller, main):
        self.parent = parent
        self.controller = controller
        self.main = main  # PageWeldingControl インスタンスを想定

        # ウィジェット参照を親（main）でも使えるように main に登録
        # 例: main.start_btn, main.preset_combo など
        self._create_ui()

    def _create_ui(self):
        main_frame = tk.Frame(self.parent, padx=10, pady=10)
        main_frame.pack(fill='both', expand=True)

        # --- 操作フレーム ---
        op_frame = tk.Frame(main_frame)
        op_frame.pack(fill='x', pady=5)

        self.main.start_btn = tk.Button(op_frame, text="① 溶着開始フロー", command=self.main.start_welding_flow)
        self.main.start_btn.pack(side='left', padx=5, pady=5)

        self.main.load_btn = tk.Button(op_frame, text="CSVから経路読込", command=self.main.load_from_csv)
        self.main.load_btn.pack(side='left', padx=5, pady=5)

        back_btn = tk.Button(op_frame, text="<< DXF編集ページに戻る",
                             command=lambda: self.controller.show_page("PageDxfEditor"))
        back_btn.pack(side='right', padx=5, pady=5)

        # --- プリセット選択 ---
        preset_frame = ttk.LabelFrame(main_frame, text="溶着設定プリセット")
        preset_frame.pack(fill='x', pady=5, padx=5)

        self.main.preset_var = tk.StringVar()
        self.main.preset_combo = ttk.Combobox(preset_frame, textvariable=self.main.preset_var, state='readonly', width=30)
        self.main.preset_combo.pack(side='left', padx=10, pady=10)

        preset_names = list(presets.WELDING_PRESETS.keys())
        self.main.preset_combo['values'] = preset_names
        # デフォルト選択
        default_name = preset_names[0] if preset_names else ''
        # controller.shared_data に保存された名前があればそちらを優先
        shared = getattr(self.controller, 'shared_data', {})
        shared_name = shared.get('preset_name')
        if shared_name in preset_names:
            default_name = shared_name
        self.main.preset_var.set(default_name)
        self.main.preset_combo.bind('<<ComboboxSelected>>', lambda e: self.main.on_preset_selected())

        # --- キャリブレーション部分 ---
        calib_container = tk.Frame(main_frame)
        calib_container.pack(fill='x', pady=5)

        calib_frame = ttk.LabelFrame(calib_container, text="傾斜キャリブレーション")
        calib_frame.pack(side='left', fill='x', expand=True, padx=5)

        self.main.calib_points_var = tk.StringVar(value="3")
        rb3 = ttk.Radiobutton(calib_frame, text="3点測定", variable=self.main.calib_points_var, value="3")
        rb3.pack(side='left', padx=5)
        rb16 = ttk.Radiobutton(calib_frame, text="16点測定", variable=self.main.calib_points_var, value="16")
        rb16.pack(side='left', padx=5)

        self.main.calib_start_btn = tk.Button(calib_frame, text="開始", command=self.main.run_calibration)
        self.main.calib_start_btn.pack(side='left', padx=10)

        dist_calib_frame = ttk.LabelFrame(calib_container, text="距離キャリブレーション")
        dist_calib_frame.pack(side='left', fill='x', expand=True, padx=5)

        self.main.calib_axis_var = tk.StringVar(value="x")
        axis_menu = ttk.OptionMenu(dist_calib_frame, self.main.calib_axis_var, "x", "x", "y")
        axis_menu.pack(side='left', padx=5)

        tk.Label(dist_calib_frame, text="目標:").pack(side='left')
        self.main.target_dist_entry = tk.Entry(dist_calib_frame, width=8)
        self.main.target_dist_entry.insert(0, "500.0")
        self.main.target_dist_entry.pack(side='left')

        move_btn = tk.Button(dist_calib_frame, text="移動", command=self.main.run_calib_move)
        move_btn.pack(side='left', padx=5)

        tk.Label(dist_calib_frame, text="実測:").pack(side='left')
        self.main.actual_dist_entry = tk.Entry(dist_calib_frame, width=8)
        self.main.actual_dist_entry.pack(side='left')

        calc_btn = tk.Button(dist_calib_frame, text="適用", command=self.main.calculate_and_apply)
        calc_btn.pack(side='left', padx=5)

        # --- 手動操作フレーム ---
        manual_frame = ttk.LabelFrame(main_frame, text="手動操作")
        manual_frame.pack(fill='x', pady=10, padx=5)

        manual_btn_frame = tk.Frame(manual_frame)
        manual_btn_frame.pack(pady=5)

        self.main.homing_button = tk.Button(manual_btn_frame, text="XY原点復帰", command=self.main.run_homing_sequence)
        self.main.homing_button.pack(side='left', padx=10)

        self.main.z_origin_btn = tk.Button(manual_btn_frame, text="Z軸の現在地を原点に", command=self.main.run_set_z_origin)
        self.main.z_origin_btn.pack(side='left', padx=10)

        # ステップ入力やジョグボタン参照を main に持たせる
        self.main.step_entries = {}
        self.main.jog_buttons = []

        # X,Yの位置制御UIを生成
        self._create_position_control(manual_frame, "X軸", "mm", "x")
        self._create_position_control(manual_frame, "Y軸", "mm", "y")
        self._create_z_control(manual_frame)

        # --- 緊急停止とログ ---
        bottom_frame = tk.Frame(main_frame)
        bottom_frame.pack(fill='both', expand=True)

        stop_btn_frame = tk.Frame(bottom_frame)
        stop_btn_frame.pack(fill='x', pady=10)

        self.main.stop_btn = tk.Button(stop_btn_frame, text="緊急停止",
                                       bg="red", fg="white", font=("メイリオ", 10, "bold"),
                                       command=self.main.on_emergency_stop)
        self.main.stop_btn.pack(side='left', padx=5)

        self.main.recover_btn = tk.Button(stop_btn_frame, text="復帰", command=self.main.on_recovery, state='disabled')
        self.main.recover_btn.pack(side='left', padx=5)

        self.main.status_label = tk.Label(bottom_frame, text="待機中", anchor='w')
        self.main.status_label.pack(fill='x')

        log_frame = ttk.LabelFrame(bottom_frame, text="ログ")
        log_frame.pack(fill='both', expand=True, pady=5)

        self.main.log_text = tk.Text(log_frame, height=10, state='disabled', bg='black', fg='lightgray', font=("Courier", 9))
        self.main.log_text.pack(fill='both', expand=True, padx=5, pady=5)

        # 最後に UI 初期化ログ
        if hasattr(self.main, 'add_log'):
            self.main.add_log("UI を構築しました。")

    def _create_position_control(self, parent, label_text, unit, axis):
        frame = ttk.LabelFrame(parent, text=label_text)
        frame.pack(fill='x', padx=10, pady=5)

        minus_btn = tk.Button(frame, text="-", width=5, font=("Arial", 12, "bold"),
                              command=lambda: self.main.move_axis(axis, -1))
        minus_btn.pack(side='left', padx=10, pady=5)
        self.main.jog_buttons.append(minus_btn)

        entry = tk.Entry(frame, width=10)
        entry.insert(0, "10.0")
        entry.pack(side='left', padx=5)
        self.main.step_entries[axis] = entry

        tk.Label(frame, text=unit).pack(side='left')

        plus_btn = tk.Button(frame, text="+", width=5, font=("Arial", 12, "bold"),
                             command=lambda: self.main.move_axis(axis, 1))
        plus_btn.pack(side='right', padx=10, pady=5)
        self.main.jog_buttons.append(plus_btn)

    def _create_z_control(self, parent):
        axis = 'z'
        frame = ttk.LabelFrame(parent, text="Z軸")
        frame.pack(fill='x', padx=10, pady=5)

        pos_frame = tk.Frame(frame)
        pos_frame.pack(fill='x', pady=2)
        tk.Label(pos_frame, text="位置制御:", width=10, anchor='w').pack(side='left')

        minus_btn = tk.Button(pos_frame, text="▲ UP", width=8, command=lambda: self.main.move_axis(axis, -1))
        minus_btn.pack(side='left', padx=(10, 0))
        self.main.jog_buttons.append(minus_btn)

        entry = tk.Entry(pos_frame, width=8)
        entry.insert(0, "5.0")
        entry.pack(side='left', padx=5)
        self.main.step_entries[axis] = entry

        tk.Label(pos_frame, text="mm").pack(side='left')

        plus_btn = tk.Button(pos_frame, text="DOWN ▼", width=8, command=lambda: self.main.move_axis(axis, 1))
        plus_btn.pack(side='left', padx=5)
        self.main.jog_buttons.append(plus_btn)

        # パルス入力
        pulse_frame = tk.Frame(frame)
        pulse_frame.pack(fill='x', pady=2)
        tk.Label(pulse_frame, text="パルス制御:", width=10, anchor='w').pack(side='left')

        self.main.step_entries['z_pulse'] = tk.Entry(pulse_frame, width=12)
        # config.SAFE_Z_PULSE を初期値として設定（存在しない場合作成側で例外処理）
        try:
            self.main.step_entries['z_pulse'].insert(0, str(config.SAFE_Z_PULSE))
        except Exception:
            self.main.step_entries['z_pulse'].insert(0, "2100")
        self.main.step_entries['z_pulse'].pack(side='left', padx=5)

        goto_pulse_btn = tk.Button(pulse_frame, text="Goto Pulse", command=self.main.run_set_z_pulse)
        goto_pulse_btn.pack(side='left', padx=6)

        # 電流制御エリア
        cur_frame = tk.Frame(frame)
        cur_frame.pack(fill='x', pady=2)
        tk.Label(cur_frame, text="電流制御:", width=10, anchor='w').pack(side='left')
        tk.Label(cur_frame, text="電流(mA):").pack(side='left', padx=(10, 0))

        cur_entry = tk.Entry(cur_frame, width=8)
        cur_entry.insert(0, "50")
        cur_entry.pack(side='left')
        self.main.step_entries[f"{axis}_adv_cur"] = cur_entry

        up_btn = tk.Button(cur_frame, text="▲ UP", command=lambda: self.main.set_current_only_move(axis, -1))
        up_btn.pack(side='left', padx=5)
        self.main.jog_buttons.append(up_btn)

        down_btn = tk.Button(cur_frame, text="DOWN ▼", command=lambda: self.main.set_current_only_move(axis, 1))
        down_btn.pack(side='left', padx=5)
        self.main.jog_buttons.append(down_btn)

        stop_btn = tk.Button(cur_frame, text="停止", bg="yellow", command=lambda: self.main.stop_continuous(axis))
        stop_btn.pack(side='left', padx=5)
        self.main.jog_buttons.append(stop_btn)

    # ヘルパー: main 側に代替メソッドがない場合に備えた安全なラッパー
    # （本来は main 側が実装していることを期待）
    def safe_add_log(self, message):
        if hasattr(self.main, 'add_log'):
            self.main.add_log(message)
        else:
            try:
                # fallback: 簡単な print
                print(message)
            except Exception:
                pass
