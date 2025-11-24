# main_app.py

# I/O Terminal ピン配置
# CN1
# ピンO-PC:24V
# ピンO-NC:GND
# ピンo-00:溶着機11
#
# CN2
# ピンI-PC:24V
# ピンI-00:フットペダル
# ピンI-01:X軸リミットスイッチ
# ピンI-02:Y軸リミットスイッチ
# ピンI-03:非常停止ボタン
#
# その他
# 溶着機12:24V
# フットペダル:GND
# 非常停止ボタン:GND

# トラブルシューティング
# 加速度がおかしい時はDYNAMIXEL Wizard 2.0 等でモーターの Drive Mode (Address 10) を確認し、Time-based Profileになっていないか確認。
# 通常動作に戻すには，選択解除して０にする。

import tkinter as tk
from tkinter import messagebox
import sys

# 各ページクラスのインポート
from page_manual_control import PageManualControl  # Page 1 (新規)
from page_dxf_editor import PageDxfEditor  # Page 2 (既存修正)
from page_path_preview import PagePathPreview  # Page 3 (新規)
from page_execution import PageExecution  # Page 4 (新規)

# ハードウェア関連
from myADconvert import ADfunc
from motion_system import MotionSystem
from io_controller import WelderController, SensorController
import config
import presets


class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("自動溶着機コントロールアプリ v2.0")
        self.geometry("1200x850")

        # --- データ共有用 ---
        # 全ページで共有したいデータ（溶着点リスト、選択中のプリセット名など）
        default_preset = list(presets.WELDING_PRESETS.keys())[0]
        self.shared_data = {
            "weld_points": [],  # 溶着点の座標リスト [{'x':.., 'y':..}, ...]
            "preset_name": default_preset  # 選択されたプリセット名
        }

        # --- ハードウェア初期化 (アプリ全体で1つだけ作成) ---
        self.hardware = {
            "dio": None,
            "motion": None,
            "welder": None,
            "sensors": {},
            "emergency_sensor": None
        }
        # 起動時にハードウェア接続を試みる
        self._init_hardware()

        # --- 画面コンテナの作成 ---
        container = tk.Frame(self)
        container.pack(side="top", fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.pages = {}
        # 4つのページクラスを登録
        page_classes = (PageManualControl, PageDxfEditor, PagePathPreview, PageExecution)

        for PageClass in page_classes:
            page_name = PageClass.__name__
            # controllerとして自分自身(MainApp)を渡すことで、ページ遷移や共有データ・ハードウェアへのアクセスを可能にする
            frame = PageClass(parent=container, controller=self)
            self.pages[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        # 最初のページを表示
        self.show_page("PageManualControl")

    def _init_hardware(self):
        """ハードウェアの接続と初期化"""
        print("ハードウェアを初期化しています...")
        try:
            # 1. DIO (Contec)
            dio = ADfunc('DIO')
            if not dio.init("DIO000"):
                messagebox.showerror("エラー", "CONTEC DIOの初期化に失敗しました。\n接続を確認してください。")
                return
            self.hardware["dio"] = dio

            # 2. Motion System (Dynamixel)
            # ログは標準出力に出す設定（必要ならGUIのログウィジェットに繋ぐことも可能）
            self.hardware["motion"] = MotionSystem(log_callback=print)

            # 3. 周辺機器 (溶着機、センサー)
            self.hardware["welder"] = WelderController(dio)
            self.hardware["sensors"] = {
                'x': SensorController(dio, config.LIMIT_SWITCH_X_PIN),
                'y': SensorController(dio, config.LIMIT_SWITCH_Y_PIN)
            }
            # 非常停止ボタンの監視用
            self.hardware["emergency_sensor"] = SensorController(dio, config.EMERGENCY_STOP_PIN)

            print("ハードウェア初期化完了")

        except Exception as e:
            messagebox.showerror("初期化エラー", f"ハードウェア初期化中にエラーが発生しました:\n{e}")

    def show_page(self, page_name):
        """ページを切り替える"""
        if page_name not in self.pages:
            return

        frame = self.pages[page_name]
        frame.tkraise()  # 最前面に表示

        # ページが表示されたタイミングで実行したい処理があれば呼ぶ
        if hasattr(frame, 'on_page_show'):
            frame.on_page_show()


if __name__ == "__main__":
    app = MainApp()
    app.mainloop()