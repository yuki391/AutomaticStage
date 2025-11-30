import tkinter as tk
from tkinter import ttk, messagebox
import ui_components
from page_welding_control_logic import WeldingControlLogic
import presets
import config

# ロジッククラスがボタンのconfigメソッドを呼び出そうとした時に
# エラーにならないようにするためのダミー
class DummyWidget:
    def config(self, **kwargs):
        pass


class PageExecution(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # MainAppからハードウェア参照
        self.motion = self.controller.hardware['motion']
        self.dio = self.controller.hardware['dio']
        self.welder = self.controller.hardware['welder']
        self.sensors = self.controller.hardware['sensors']

        # ロジッククラスの互換性のためのダミーボタン設定
        # (Logicクラスが self.main.homing_button.config(...) を呼ぶため)
        self.homing_button = DummyWidget()
        self.z_origin_btn = DummyWidget()

        # UIで使う変数の初期化
        self.step_entries = {}
        self.jog_buttons = []
        self.is_moving = False  # Logicが参照するフラグ

        # ロジッククラス (ハードウェア操作用)
        self.logic = WeldingControlLogic(self)

        # --- UI ---
        top_frame = tk.Frame(self, pady=10)
        top_frame.pack(fill='x')
        tk.Label(top_frame, text="Step 4: 実行・原点調整", font=("Arial", 14, "bold")).pack(side='left', padx=10)

        # 戻るボタン
        tk.Button(top_frame, text="<< 経路確認に戻る",
                  command=lambda: controller.show_page("PagePathPreview")).pack(side='right', padx=10)

        main_content = tk.Frame(self, padx=10)
        main_content.pack(fill='both', expand=True)

        # --- 1. プリセット確認 ---
        info_frame = ttk.LabelFrame(main_content, text="設定情報")
        info_frame.pack(fill='x', pady=5)
        self.lbl_preset = tk.Label(info_frame, text="プリセット: ---", font=("Arial", 11), fg="blue")
        self.lbl_preset.pack(anchor='w', padx=10, pady=5)
        self.lbl_points = tk.Label(info_frame, text="点数: 0", font=("Arial", 11))
        self.lbl_points.pack(anchor='w', padx=10, pady=5)

        # --- 2. 原点調整 (ジョグ) ---
        jog_frame = ttk.LabelFrame(main_content, text="原点位置の微調整 (手動)")
        jog_frame.pack(fill='x', pady=10)

        self.create_advanced_control(jog_frame, "Z軸 (高さ調整)", "mm", "z")

        tk.Label(jog_frame, text="現在位置を加工原点(0,0)として設定します。位置合わせを行ってください。").pack(pady=5)

        # 簡易ジョグパネル
        axis_frame = tk.Frame(jog_frame)
        axis_frame.pack()

        # X軸
        self.create_mini_jog(axis_frame, "x", "X軸")
        # Y軸
        self.create_mini_jog(axis_frame, "y", "Y軸")

        # ステップ移動量入力
        step_frame = tk.Frame(jog_frame)
        step_frame.pack(pady=5)
        tk.Label(step_frame, text="移動量(mm):").pack(side='left')

        self.step_entries['x'] = tk.Entry(step_frame, width=5)
        self.step_entries['x'].insert(0, "1.0")
        self.step_entries['x'].pack(side='left')
        # Y軸も同じEntryを参照させる（簡易実装）
        self.step_entries['y'] = self.step_entries['x']

        # 原点設定ボタン
        btn_set_origin = tk.Button(jog_frame, text="現在位置を「加工原点」に設定",
                                   bg="lightgreen", height=2,
                                   command=self.set_work_origin_here)
        btn_set_origin.pack(pady=10, fill='x', padx=50)

        # --- 3. 実行コントロール ---
        exec_frame = ttk.LabelFrame(main_content, text="実行")
        exec_frame.pack(fill='x', pady=10)

        # プレビュー実行
        btn_preview = tk.Button(exec_frame, text="動作プレビュー (溶着なし)",
                                command=self.run_dry_run_preview)
        btn_preview.pack(side='left', padx=20, pady=20, fill='x', expand=True)

        # 本番実行
        self.start_btn = tk.Button(exec_frame, text="★ 溶着開始 ★", bg="red", fg="white", font=("Arial", 14, "bold"),
                                   command=self.start_real_welding)
        self.start_btn.pack(side='right', padx=20, pady=20, fill='x', expand=True)

        # --- ログと緊急停止 ---
        # ここで on_emergency_stop 等が呼ばれるため、メソッド定義が必須
        ui_components.create_emergency_stop_widgets(self, self)

        self.active_preset = {}
        default_name = getattr(config, 'DEFAULT_PRESET_NAME', None)
        if default_name and default_name in presets.WELDING_PRESETS:
            self.active_preset = presets.WELDING_PRESETS[default_name]
        elif len(presets.WELDING_PRESETS) > 0:
            first_key = list(presets.WELDING_PRESETS.keys())[0]
            self.active_preset = presets.WELDING_PRESETS[first_key]

    def create_mini_jog(self, parent, axis, label):
        f = tk.Frame(parent)
        f.pack(side='left', padx=15)
        tk.Label(f, text=label).pack()

        btn_minus = tk.Button(f, text="< -", command=lambda: self.logic.move_axis(axis, -1))
        btn_minus.pack(side='left')
        self.jog_buttons.append(btn_minus)

        btn_plus = tk.Button(f, text="+ >", command=lambda: self.logic.move_axis(axis, 1))
        btn_plus.pack(side='left')
        self.jog_buttons.append(btn_plus)

    def on_page_show(self):
        p_name = self.controller.shared_data.get('preset_name', 'Unknown')
        points = self.controller.shared_data.get('weld_points', [])

        # ★追加: データがまだシフトされていない(DXFから来たばかり)なら、基準データとして保存
        is_shifted = self.controller.shared_data.get('is_shifted', False)

        # 初回ロード時、またはDXFエディタから再生成された場合は base_points を更新
        if not is_shifted or self.base_points is None:
            # deepcopyして保存（元のリストとは別物にする）
            self.base_points = copy.deepcopy(points)
            # フラグをFalseに（明示的リセット）
            self.controller.shared_data['is_shifted'] = False

        self.lbl_preset.config(text=f"プリセット: {p_name}")
        self.lbl_points.config(text=f"点数: {len(points)} 点")

        if p_name in presets.WELDING_PRESETS:
            self.active_preset = presets.WELDING_PRESETS[p_name]

        self.draw_preview(points)

    # ------------------------------------------------
    # 必須メソッド群 (ui_components / Logic から呼ばれる)
    # ------------------------------------------------
    def on_emergency_stop(self):
        self.logic.on_emergency_stop()

    def on_recovery(self):
        self.logic.on_recovery()

    def add_log(self, msg):
        """ログウィンドウへの出力"""
        if hasattr(self, 'log_text') and self.log_text.winfo_exists():
            self.log_text.config(state='normal')
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state='disabled')
        else:
            print(msg)

    # ------------------------------------------------
    # 独自ロジック
    # ------------------------------------------------
    def set_work_origin_here(self):
        """
        現在の機械座標を、加工上の原点(0,0)として記録する。
        ※注: teach_origin_by_jog はダイアログを出す関数なので、
        ここでは独自に座標を取得して設定する。
        """
        if self.motion:
            x = self.motion.current_pos['x']
            y = self.motion.current_pos['y']

            # 共有データなどに保存する（ロジック側で参照できるようにする）
            # 簡易的にインスタンス変数に保存
            self.custom_work_origin = (x, y)

            self.add_log(f"加工原点を設定しました (機械座標): X={x:.2f}, Y={y:.2f}")
            messagebox.showinfo("設定完了", "現在の位置を加工原点として設定しました。")
        else:
            messagebox.showerror("エラー", "モーションシステムが接続されていません。")

    def run_dry_run_preview(self):
        # プリセットの溶着電流を0にしたコピーを作って実行するなどの工夫が必要
        # 今回は簡易的に「溶着フロー」を呼ぶが、原点設定ステップを飛ばす必要がある
        # 実装が複雑になるため、一旦ログ出力のみ
        self.add_log("プレビュー機能は未実装です（Logicクラスの拡張が必要です）")

    def start_real_welding(self):
        if not hasattr(self, 'custom_work_origin'):
            if not messagebox.askyesno("確認", "加工原点が設定されていません。\n現在位置を原点として開始しますか？"):
                return
            self.set_work_origin_here()

        # ここでLogicクラスのstart_welding_flowを呼び出すが、
        # Logic側で teach_origin_by_jog が呼ばれると再度ダイアログが出てしまう。
        # 本来はLogicクラスを改修して「引数で原点を渡す」ようにすべき。
        self.logic.start_welding_flow()

    def create_advanced_control(self, parent, label_text, unit, axis):
        """Z軸などの詳細制御パネルを作成 (PageExecution用)"""
        frame = ttk.LabelFrame(parent, text=label_text)
        frame.pack(fill='x', padx=10, pady=5)

        # --- パルス位置直接入力 ---
        pulse_frame = tk.Frame(frame)
        pulse_frame.pack(fill='x', pady=2)
        tk.Label(pulse_frame, text="パルス制御:", width=10, anchor='w').pack(side='left')

        pulse_entry = tk.Entry(pulse_frame, width=12)
        # configがあれば初期値を設定
        default_pulse = getattr(config, 'SAFE_Z_PULSE', 2100)
        pulse_entry.insert(0, str(default_pulse))
        pulse_entry.pack(side='left', padx=5)
        self.step_entries['z_pulse'] = pulse_entry

        goto_pulse_btn = tk.Button(pulse_frame, text="Goto Pulse",
                                   command=self.logic.run_set_z_pulse)  # 直接呼び出し
        goto_pulse_btn.pack(side='left', padx=6)

        # --- 位置制御 (UP/DOWN) ---
        pos_frame = tk.Frame(frame)
        pos_frame.pack(fill='x', pady=2)
        tk.Label(pos_frame, text="位置制御:", width=10, anchor='w').pack(side='left')

        btn_up = tk.Button(pos_frame, text="▲ UP", command=lambda: self.logic.move_axis(axis, -1))
        btn_up.pack(side='left')

        entry = tk.Entry(pos_frame, width=8)
        entry.insert(0, "5.0")
        entry.pack(side='left', padx=5)
        self.step_entries[axis] = entry

        tk.Label(pos_frame, text=unit).pack(side='left')

        btn_down = tk.Button(pos_frame, text="DOWN ▼", command=lambda: self.logic.move_axis(axis, 1))
        btn_down.pack(side='left', padx=5)