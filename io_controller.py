# io_controller.py

"""
myADconvert モジュールを使い、超音波溶着機と
リミットスイッチ（センサー）の制御を行うための高レベルなインターフェースです。
"""

import config
from myADconvert import DIO_ch  # myADconvertから必要なクラスをインポート


class WelderController:
    def __init__(self, dio_instance, log_callback=print):
        self.log = log_callback
        self.dio = dio_instance
        self.pin = config.WELDER_PIN
        self.log("  [HW] 溶着機コントローラを初期化しました。")

    def turn_on(self):
        self.log("  [HW] << 溶着機 ON >>")
        # ★★★ ここを修正 ★★★
        # myADconvertの仕様に合わせて AO_DO='DO' 引数を追加
        self.dio.write(channel=DIO_ch(self.pin), value=1, AO_DO='DO')

    def turn_off(self):
        self.log("  [HW] << 溶着機 OFF >>")
        # ★★★ ここを修正 ★★★
        # myADconvertの仕様に合わせて AO_DO='DO' 引数を追加
        self.dio.write(channel=DIO_ch(self.pin), value=0, AO_DO='DO')

    def shutdown(self):
        self.turn_off()
        self.log("  [HW] 溶着機をシャットダウンしました。")


class SensorController:
    def __init__(self, dio_instance, pin_number, log_callback=print):
        self.log = log_callback
        self.dio = dio_instance
        self.pin = pin_number
        self.log(f"  [HW] センサーコントローラを初期化しました (PIN: {self.pin})。")

    def is_triggered(self):
        """センサーが押されたか（信号を読み取ったか）を返す"""
        # myADconvertのread関数に、'AI_DI'引数を追加する
        state = self.dio.read(channel=self.pin, AI_DI='DI')

        # センサーが押されたときに0(Low)になる場合、 not state を返す
        return not state