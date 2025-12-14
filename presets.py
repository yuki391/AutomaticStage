# presets.py

# ==========================================================================
# 溶着プリセット定義
# ==========================================================================
# ここに、材質や用途に応じた複数の設定を定義します。
# GUIのドロップダウンメニューに、ここの名前が表示されます。
#
# パラメータの説明:
#   'weld_pitch'       : 標準2.0．DXFから経路を生成する際の、溶着点の間隔 (mm)。
#   'velocity_xy'      : 標準300．XY軸の最高速度。大きいほど速い。
#   'acceleration_xy'  : 標準50．XY軸の加速度。小さいほど滑らか。
#   'weld_current'     : 標準5．溶着時の加圧電流 (mA)。大きいほど強く押す。
#   'gentle_current'   : ゆっくりめ-1，速め10．接触検知時の優しい接触電流 (mA)。　
#   'weld_time'        : 標準1．超音波を発振する時間 (秒)。
# ==========================================================================

WELDING_PRESETS = {
    "下記から選択": {#config.pyでこの名前使ってるからこの名前は変えないで．
        'weld_pitch': 10.0,
        'velocity_xy': 300,
        'acceleration_xy': 50,
        'weld_current': 5,
        'gentle_current': 8,
        'weld_time': 1,
        #基本的なパラメーター．amptdは80
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

