#20251008 溶着機をフットスイッチで操作する

import time
import sys
# myADconvert.pyが同じフォルダにあることを確認してください
from myADconvert import ADfunc

# --- 設定項目 ---
# デジタル入出力デバイスのため、通常は "DIO000" となります。
DEVICE_NAME = "DIO000"

# ボタンを接続しているデジタル入力(DI)チャンネル番号
BUTTON_CH = 0

# 溶接機に接続しているデジタル出力(DO)チャンネル番号
WELDER_CH = 0


# --- 設定項目ここまで ---

def main():
    """
    ADコンバータを初期化し、ボタン入力に応じて溶接機を制御するメイン関数
    """
    ad_converter = ADfunc('DIO')

    if not ad_converter.init(DEVICE_NAME):
        print(f"デバイス '{DEVICE_NAME}' の初期化に失敗しました。", file=sys.stderr)
        print("CONTEC I/Oユニットが接続されてるか確認してください。", file=sys.stderr)
        return

    print("デバイスの初期化に成功しました。")
    print("ボタンを押してコンソールの表示が変わるか確認してください。")
    print("プログラムを終了するには Ctrl+C を押してください。")

    last_state = -1  # 前回のボタン状態を保持する変数

    try:
        while True:
            # デジタル入力チャンネルからボタンの状態を読み取る
            button_state = ad_converter.read(channel=BUTTON_CH, AI_DI='DI')

            # 状態が変化した時だけ表示を更新
            if button_state != last_state:
                if button_state == 1:
                    # ボタンが押された
                    print("ボタン ON -> 溶接機作動中...")
                    ad_converter.write(channel=WELDER_CH, value=1, AO_DO='DO')
                else:
                    # ボタンが離された
                    print("ボタン OFF -> 溶接機停止中...")
                    ad_converter.write(channel=WELDER_CH, value=0, AO_DO='DO')

                last_state = button_state  # 現在の状態を保存

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nプログラムを終了します。")
    except Exception as e:
        print(f"\nエラーが発生しました: {e}", file=sys.stderr)
    finally:
        print("安全のため、全てのデジタル出力をOFFにしてデバイスを終了します。")
        ad_converter.exit()
        print("デバイスを正常に終了しました。")


if __name__ == "__main__":
    main()