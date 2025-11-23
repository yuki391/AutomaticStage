# presets.py

# ==========================================================================
# 溶着プリセット定義
# ==========================================================================
# ここに、材質や用途に応じた複数の設定を定義します。
# GUIのドロップダウンメニューに、ここの名前が表示されます。
#
# パラメータの説明:
#   'weld_pitch'       : DXFから経路を生成する際の、溶着点の間隔 (mm)。
#   'velocity_xy'      : XY軸の最高速度。大きいほど速い。★変わらない★
#   'acceleration_xy'  : XY軸の加速度。小さいほど滑らか。★変わらない★
#   'weld_current'     : 溶着時の加圧電流 (mA)。大きいほど強く押す。
#   'gentle_current'   : 接触検知時の優しい接触電流 (mA)。　★自重で落ちて意味ないから後でマイナスの値で下がるやつにしたい★
#   'weld_time'        : 超音波を発振する時間 (秒)。
# ==========================================================================

WELDING_PRESETS = {
    "下記から選択": {#この名前は変えないで．config.pyでこの名前使ってる
        'weld_pitch': 2.0,#点の間隔
        'velocity_xy': 0,
        'acceleration_xy':0,
        'weld_current': 30,#押し付け力
        'gentle_current': 30,
        'weld_time': 2,#秒数
        #amptdは６５
    },

    "ポリウレタン(0.6+0.3mm)": {
        'weld_pitch': 2.0,#点の間隔
        'velocity_xy': 150,
        'acceleration_xy':15,
        'weld_current': 120,#押し付け力
        'gentle_current': 10,
        'weld_time': 1.3,#秒数
        #amptdは80
    },
    "test2": {
        'weld_pitch': 2.0,
        'velocity_xy': 10,
        'acceleration_xy': 150,
        'weld_current': 100,
        'gentle_current': 200,
        'weld_time': 2.0,
    },
    "test1": {
        'weld_pitch': 2.0,
        'velocity_xy': 150,
        'acceleration_xy': 20,
        'weld_current': 50,
        'gentle_current': 35,
        'weld_time': 1,
    },
    "ポリウレタン_強め(0.3+0.3mm)": {
        'weld_pitch': 1.8,#点の間隔
        'velocity_xy': 15,
        'acceleration_xy':15,
        'weld_current': 70,#押し付け力
        'gentle_current': 200,
        'weld_time': 1.4,#秒数
        #amptdは80
    },
    "ポリウレタン(0.3+0.3mm)": {
        'weld_pitch': 2.0,#点の間隔
        'velocity_xy': 300,
        'acceleration_xy':15,
        'weld_current': 50,#押し付け力
        'gentle_current': 200,
        'weld_time': 1.2,#秒数
        #amptdは80
    },
}

