# motion_system.py
# フルファイル（改良版）: ホーミング時のバックオフを「位置制御」ではなく
# 「速度制御」で行う実装に差し替えました。
#
# ポイント:
# - 初回センサー通過前の高速アプローチは元のまま（速度制御）に戻しています。
# - センサー検知後のバックオフは位置目標ではなく速度指令で行い、
#   read_present_position を監視して所要パルスだけ移動したら停止します。
# - こうすることでファームウェアが大きな position target を clamp して
#   ガタつく問題を回避し、バックオフ動作を滑らかにします。
# - タイムアウト・ロギング・安全 clamp を入れてあります。
#
# 実機で試す前に必ず非常停止と周囲安全確認を行ってください。
# ------------------------------------------------------------------------------

import time
import math
import config
import presets
from dynamixel_controller import DynamixelController
from settings_io import load_settings, save_settings


class MotionSystem:
    def __init__(self, log_callback=print):
        self.log = log_callback
        self.log("モーションシステムを初期化しています...")

        # デフォルト値（config から）
        default_x = config.PULSES_PER_MM_X
        default_y = config.PULSES_PER_MM_Y
        default_z = config.PULSES_PER_MM_Z

        # settings.json から読み込み（モジュールディレクトリの settings.json を使う）
        try:
            settings = load_settings()
            self.log(f"settings.json を読み込みました: {settings}")
        except Exception as e:
            settings = {}
            self.log(f"settings.json の読み込みに失敗しました（無視）: {e}")

        # 永続化された値があればそれを使う（なければ config の既定値）
        self.pulses_per_mm_x = float(settings.get("pulses_per_mm_x", default_x))
        self.pulses_per_mm_y = float(settings.get("pulses_per_mm_y", default_y))
        self.pulses_per_mm_z = float(settings.get("pulses_per_mm_z", default_z))

        # 以下は既存の初期化処理
        self.homing_offsets = {'x': 0, 'y': 0, 'z': 0}
        self.is_homed = False
        self.dxl = DynamixelController(log_callback=self.log)
        self.current_pos = {'x': 0.0, 'y': 0.0, 'z': 0.0}
        self.tilt_plane = None

        self.homing_backoff_speed = getattr(config, 'HOMING_BACKOFF_SPEED', 30)
        self.homing_backoff_acceleration = getattr(config, 'HOMING_BACKOFF_ACCELERATION', 5)
        self.homing_backoff_mm = getattr(config, 'HOMING_BACKOFF_MM', 20)
        self._backoff_timeout = getattr(config, 'HOMING_BACKOFF_TIMEOUT', 5.0)

        if not self.dxl.connect(config.DEVICENAME):
            raise ConnectionError("Dynamixelへの接続に失敗しました。")
        self._setup_motors()
        self.log("モーションシステムの初期化が完了しました。")

    def _setup_motors(self):
        self.log("全モーターのセットアップを開始...")
        for axis, dxl_id in config.DXL_IDS.items():
            self.dxl.enable_torque(dxl_id)
            if axis in ['x', 'y']:
                self.dxl.set_operating_mode(dxl_id, 4)
            else:
                self.dxl.set_operating_mode(dxl_id, 3)
                self.dxl.set_profile(dxl_id, config.PROFILE_VELOCITY_Z, config.PROFILE_ACCELERATION_Z)
        self.log("全モーターのセットアップ完了。")

    def update_homing_backoff(self, speed=None, acceleration=None, backoff_mm=None, timeout=None):
        """ランタイム更新（必要なら UI から呼べるように）"""
        try:
            if speed is not None:
                self.homing_backoff_speed = float(speed)
            if acceleration is not None:
                self.homing_backoff_acceleration = float(acceleration)
            if backoff_mm is not None:
                self.homing_backoff_mm = float(backoff_mm)
            if timeout is not None:
                self._backoff_timeout = float(timeout)
            self.log(f"ホーミングバックオフ設定更新: speed={self.homing_backoff_speed}, accel={self.homing_backoff_acceleration}, mm={self.homing_backoff_mm}, timeout={self._backoff_timeout}")
            return True
        except Exception as e:
            self.log(f"ホーミングバックオフ設定更新エラー: {e}")
            return False

    def move_xy_abs(self, x_mm, y_mm, preset):
        self.log(f"XY -> ({x_mm:.2f}, {y_mm:.2f})mm")
        velocity = preset['velocity_xy']
        acceleration = preset['acceleration_xy']

        self.dxl.set_profile(config.DXL_IDS['x'], velocity, acceleration)
        self.dxl.set_profile(config.DXL_IDS['y'], velocity, acceleration)

        x_pulse = self._mm_to_pulses(x_mm, 'x')
        y_pulse = self._mm_to_pulses(y_mm, 'y')

        self.dxl.set_goal_position(config.DXL_IDS['x'], x_pulse)
        self.dxl.set_goal_position(config.DXL_IDS['y'], y_pulse)

        while self.dxl.is_moving(config.DXL_IDS['x']) or self.dxl.is_moving(config.DXL_IDS['y']):
            time.sleep(0.05)

        self.current_pos['x'], self.current_pos['y'] = x_mm, y_mm
        self.log("XY 移動完了。")

    def _home_single_axis(self, axis, sensor):
        """
        単軸ホーミング（バックオフを速度制御で実行）
        手順:
          1) 高速速度制御で接近し、センサー検知まで待つ（従来通り）
          2) センサー検知後、速度制御で「離れる方向に一定速度」を出し、
             read_present_position を監視して所要パルス分移動したら停止する（滑らかな動作）
          3) 低速再接近で原点を決定（従来通り）
        """
        dxl_id = config.DXL_IDS[axis]
        homing_sign = config.HOMING_VELOCITY_SIGN.get(axis, -1)
        fast_speed = int(config.HOMING_SPEED_FAST * homing_sign)
        slow_speed = int(config.HOMING_SPEED_SLOW * homing_sign)

        # --- 初回アプローチ（元の速度制御） ---
        self.log(f"{axis.upper()}軸 原点探索 (高速)... (homing_sign={homing_sign}, fast_speed={fast_speed})")
        self.dxl.set_operating_mode(dxl_id, 1)  # 速度制御モード
        self.dxl.set_goal_velocity(dxl_id, fast_speed)
        while not sensor.is_triggered():
            time.sleep(0.005)
        # 停止
        self.dxl.set_goal_velocity(dxl_id, 0)
        self.log(f"{axis.upper()}軸 センサー検知。")
        time.sleep(0.3)
        # --- ここまでが初回通過前の動作（元に戻した） ---

        # --- バックオフ：速度制御で離れる方向に一定速度を出す ---
        start_pos = self.dxl.read_present_position(dxl_id)
        if start_pos == -1:
            self.log("  !! 警告: 現在位置の読み取りに失敗しました。バックオフをスキップします。")
        else:
            pulse_per_mm = self.pulses_per_mm_x if axis == 'x' else self.pulses_per_mm_y
            backoff_mm = float(self.homing_backoff_mm)
            # 以前の実装と同じ意味でのパルス計算（離れる方向は -homing_sign）
            desired_backoff_pulses = int(backoff_mm * pulse_per_mm * -homing_sign)
            self.log(f"バックオフ開始: start_pos={start_pos}, backoff_mm={backoff_mm}, desired_backoff_pulses={desired_backoff_pulses}")

            # 速度値は homing_backoff_speed を使い、方向は -homing_sign
            velocity_value = int(self.homing_backoff_speed * (-homing_sign))
            # safety: clamp small non-zero
            if velocity_value == 0:
                velocity_value = int(1 * (-homing_sign))
            self.log(f"  set_goal_velocity for backoff: {velocity_value} (unit: device velocity)")

            # 切替：速度制御モード（既に1だが明示）
            self.dxl.set_operating_mode(dxl_id, 1)
            # set velocity to start moving away
            self.dxl.set_goal_velocity(dxl_id, velocity_value)

            # 監視：所要パルスだけ移動したら停止
            t0 = time.time()
            timeout = self._backoff_timeout
            target_reached = False

            while True:
                now = time.time()
                if now - t0 > timeout:
                    self.log("  !! バックオフがタイムアウトしました。停止します。")
                    break
                pos = self.dxl.read_present_position(dxl_id)
                if pos == -1:
                    self.log("  !! read_present_position が -1 を返しました。停止します。")
                    break
                moved = pos - start_pos
                # desired_backoff_pulses には方向が含まれる（負または正）
                if (desired_backoff_pulses >= 0 and moved >= desired_backoff_pulses) or \
                   (desired_backoff_pulses <= 0 and moved <= desired_backoff_pulses):
                    target_reached = True
                    self.log(f"  バックオフ目標到達: start={start_pos}, now={pos}, moved={moved}")
                    break
                # 短いインターバルでポーリング（0.01〜0.05 秒）
                time.sleep(0.02)

            # 停止指令（速度0）
            self.dxl.set_goal_velocity(dxl_id, 0)
            # 少し待って確定
            time.sleep(0.05)
            final_pos = self.dxl.read_present_position(dxl_id)
            self.log(f"  バックオフ完了後の位置 read={final_pos} (target_reached={target_reached})")

        # --- 低速で再接近（元の実装） ---
        self.log(f"{axis.upper()}軸 原点確定 (低速)...")
        self.dxl.set_operating_mode(dxl_id, 1)
        self.dxl.set_goal_velocity(dxl_id, slow_speed)
        while not sensor.is_triggered():
            time.sleep(0.005)
        self.dxl.set_goal_velocity(dxl_id, 0)
        final_pos = self.dxl.read_present_position(dxl_id)
        self.log(f"{axis.upper()}軸 原点確定。絶対パルス位置: {final_pos}")
        time.sleep(0.3)

        # 位置モードに戻してオフセットを保存
        self.dxl.set_operating_mode(dxl_id, 4)
        self.homing_offsets[axis] = final_pos
        self.current_pos[axis] = 0.0
        return True

    def home_all_axes(self, sensors):
        self.log("--- XY原点復帰シーケンス開始 ---")
        self._home_single_axis('x', sensors['x'])
        self._home_single_axis('y', sensors['y'])
        self.log("--- XY原点復帰シーケンス完了 ---")
        default_preset = presets.WELDING_PRESETS[config.DEFAULT_PRESET_NAME]
        self.move_xy_abs(0, 0, default_preset)
        self.is_homed = True

    def descend_until_contact(self, preset):
        self.log("  Z軸を下降させ、接触点を探索...")
        z_id = config.DXL_IDS['z']
        self.dxl.set_profile(z_id, config.PROFILE_VELOCITY_Z, config.PROFILE_ACCELERATION_Z)
        self.dxl.set_operating_mode(z_id, 0)
        gentle_current = preset['gentle_current'] * config.MOTOR_DIRECTIONS['z*1']
        self.dxl.set_goal_current(z_id, gentle_current)
        time.sleep(0.3)
        self.dxl.set_goal_current(z_id, 0)
        time.sleep(0.2)
        contact_pulse = self.dxl.read_present_position(z_id)
        if contact_pulse == -1:
            self.log("  エラー: Z軸の位置読み取りに失敗。")
            self.dxl.set_operating_mode(z_id, 3)
            return None
        self.log(f"  接触を検知。パルス位置: {contact_pulse}")
        self.dxl.set_operating_mode(z_id, 3)
        return contact_pulse

    def update_pulses_per_mm(self, axis, new_value):
        """
        axis: 'x'|'y'|'z'
        new_value: float
        内部値を更新したあと settings.json に保存して永続化する
        """
        try:
            nv = float(new_value)
        except Exception:
            self.log(f"update_pulses_per_mm: 無効な値 {new_value}")
            return False

        if axis == 'x':
            self.pulses_per_mm_x = nv
        elif axis == 'y':
            self.pulses_per_mm_y = nv
        elif axis == 'z':
            self.pulses_per_mm_z = nv
        else:
            self.log(f"update_pulses_per_mm: 未知の axis '{axis}'")
            return False

        self.log(f"✅ {axis.upper()}軸の単位換算値を更新しました: {nv:.6f}")

        # 永続化: settings.json を読み、該当キーを更新して保存
        try:
            s = load_settings() or {}
            s['pulses_per_mm_x'] = float(self.pulses_per_mm_x)
            s['pulses_per_mm_y'] = float(self.pulses_per_mm_y)
            s['pulses_per_mm_z'] = float(self.pulses_per_mm_z)
            ok = save_settings(s)
            if ok:
                self.log("設定を settings.json に保存しました。 (場所: settings_io.SETTINGS_PATH)")
                return True
            else:
                self.log("警告: settings.json の保存に失敗しました。書き込み権限やパスを確認してください。")
                return False
        except Exception as e:
            self.log(f"settings.json の保存中に例外が発生しました: {e}")
            return False

    def _mm_to_pulses(self, mm_value, axis):
        pulse_delta = 0
        if axis == 'x':
            pulse_delta = int(mm_value * self.pulses_per_mm_x)
        elif axis == 'y':
            pulse_delta = int(mm_value * self.pulses_per_mm_y)
        elif axis == 'z':
            pulse_delta = int(mm_value * self.pulses_per_mm_z)
        final_pulse = self.homing_offsets[axis] + (pulse_delta * config.MOTOR_DIRECTIONS[axis])
        return final_pulse

    def _pulses_to_mm(self, pulse_value, axis):
        if axis not in self.homing_offsets:
            return 0.0
        pulse_delta = (pulse_value - self.homing_offsets[axis]) * config.MOTOR_DIRECTIONS[axis]
        mm_value = 0.0
        if axis == 'x' and self.pulses_per_mm_x != 0:
            mm_value = pulse_delta / self.pulses_per_mm_x
        elif axis == 'y' and self.pulses_per_mm_y != 0:
            mm_value = pulse_delta / self.pulses_per_mm_y
        elif axis == 'z' and self.pulses_per_mm_z != 0:
            mm_value = pulse_delta / self.pulses_per_mm_z
        return mm_value

    def set_tilt_plane(self, plane_coeffs):
        self.tilt_plane = plane_coeffs
        self.log(f"傾斜補正データを設定: a={plane_coeffs['a']:.4f}, b={plane_coeffs['b']:.4f}, c={plane_coeffs['c']:.4f}")

    def get_tilted_z(self, x_mm, y_mm):
        if self.tilt_plane:
            return self.tilt_plane['a'] * x_mm + self.tilt_plane['b'] * y_mm + self.tilt_plane['c']
        return 0.0

    def move_z_abs(self, z_mm):
        self.log(f"Z -> {z_mm:.2f}mm")
        # mm をパルスに変換
        z_pulse = self._mm_to_pulses(z_mm, 'z')

        # 共通メソッドを呼び出して移動（ここでリミットチェックが行われる）
        self.move_z_abs_pulse(z_pulse)

        # 現在位置(mm)を更新
        self.current_pos['z'] = z_mm
        self.log("Z 移動完了。")

    def move_z_abs_pulse(self, z_pulse):
        # --- ソフトリミットによる制限処理 ---
        original_pulse = z_pulse

        # 最小値チェック
        if z_pulse < config.Z_LIMIT_MIN_PULSE:
            z_pulse = config.Z_LIMIT_MIN_PULSE
            self.log(
                f"⚠️ 警告: Z指令値({original_pulse})が下限を超えています。{config.Z_LIMIT_MIN_PULSE} に制限しました。")

        # 最大値チェック
        elif z_pulse > config.Z_LIMIT_MAX_PULSE:
            z_pulse = config.Z_LIMIT_MAX_PULSE
            self.log(
                f"⚠️ 警告: Z指令値({original_pulse})が上限を超えています。{config.Z_LIMIT_MAX_PULSE} に制限しました。")

        self.log(f"Z -> 絶対パルス位置 {z_pulse} へ移動...")
        z_id = config.DXL_IDS['z']

        # 1. モードとプロファイルを設定
        self.dxl.set_operating_mode(z_id, 3)  # 位置制御モード
        self.dxl.set_profile(z_id, config.PROFILE_VELOCITY_Z, config.PROFILE_ACCELERATION_Z)

        # 2. 目標位置を書き込み（制限済みの値を使用）
        self.dxl.set_goal_position(z_id, z_pulse)

        # --- 移動完了待ち処理 (既存コードのまま) ---
        self.log(f"  (移動待機中... 目標: {z_pulse})")
        POSITION_THRESHOLD = 10
        timeout_sec = 5.0
        start_time = time.time()

        while True:
            current_pulse = self.dxl.read_present_position(z_id)
            if current_pulse == -1:
                self.log("  (警告: 現在位置の読み取りに失敗。待機を中断)")
                break

            diff = abs(z_pulse - current_pulse)
            if diff <= POSITION_THRESHOLD:
                self.log(f"  (目標位置に到達。 現在: {current_pulse})")
                break

            if (time.time() - start_time) > timeout_sec:
                self.log(f"  (警告: Z軸移動がタイムアウトしました。 現在: {current_pulse})")
                break
            time.sleep(0.05)

        final_pulse = self.dxl.read_present_position(z_id)
        if final_pulse != -1:
            self.log(f"Z軸 パルス移動完了。 最終位置: {final_pulse}")
        else:
            self.log("Z軸 パルス移動完了。（最終位置の読み取りに失敗しました）")

    def move_xy_rel(self, dx_mm=0, dy_mm=0, preset=None):
        if preset is None:
            self.log("エラー: move_xy_relにプリセットが指定されていません。")
            return
        target_x = self.current_pos['x'] + dx_mm
        target_y = self.current_pos['y'] + dy_mm
        self.move_xy_abs(target_x, target_y, preset)

    def move_z_rel(self, dz_mm):
        target_z = self.current_pos['z'] + dz_mm
        self.move_z_abs(target_z)

    def set_z_origin_here(self):
        self.log("--- Z軸の現在位置を原点として設定します ---")
        axis = 'z'
        dxl_id = config.DXL_IDS[axis]
        current_pulse = self.dxl.read_present_position(dxl_id)
        if current_pulse != -1:
            self.homing_offsets[axis] = current_pulse
            self.current_pos[axis] = 0.0
            self.log(f"{axis.upper()}軸の原点オフセットを {current_pulse} に設定。")
        return True

    def execute_welding_press(self, welder, preset):
        self.log("--- 溶着プレスシーケンス開始 ---")
        z_id = config.DXL_IDS['z']
        self.log("  ステップ1: 優しい接触を開始 (電流制御)...")
        self.descend_until_contact(preset)

        self.log(f"  ステップ2: {preset['weld_current']}mAで加圧し、溶着を実行...")
        self.dxl.set_operating_mode(z_id, 0)
        press_current_ma = preset['weld_current'] * config.MOTOR_DIRECTIONS['z']
        self.dxl.set_goal_current(z_id, press_current_ma)
        time.sleep(0.5)
        welder.turn_on()
        weld_time_sec = preset['weld_time']
        time.sleep(weld_time_sec)
        welder.turn_off()
        self.log(f"  ステップ2: {weld_time_sec}秒の溶着完了。")
        self.dxl.set_goal_current(z_id, 0)
        self.log(f"  ステップ3: 安全なパルス位置({config.SAFE_Z_PULSE})へ退避...")
        self.move_z_abs_pulse(config.SAFE_Z_PULSE)
        self.log("--- 溶着プレスシーケンス完了 ---")
        return True

    def set_axis_current(self, axis, current):
        dxl_id = config.DXL_IDS.get(axis)
        if dxl_id is None:
            return
        self.dxl.set_operating_mode(dxl_id, 0)
        current_ma = int(current * config.MOTOR_DIRECTIONS.get(axis, 1))
        self.dxl.set_goal_current(dxl_id, current_ma)
        self.log(f"  [電流制御] {axis.upper()}軸 駆動開始: {current_ma}mA")

    def stop_continuous_move(self, axis):
        dxl_id = config.DXL_IDS.get(axis)
        if dxl_id is None:
            return
        self.dxl.set_goal_current(dxl_id, 0)
        self.log(f"  [連続] {axis.upper()}軸 停止。")
        time.sleep(0.1)
        op_mode = 4 if axis in ['x', 'y'] else 3
        self.dxl.set_operating_mode(dxl_id, op_mode)

    def check_connection(self, axis='x'):
        dxl_id = config.DXL_IDS.get(axis)
        return self.dxl.ping(dxl_id) if dxl_id else False

    def return_to_origin(self):
        self.log("--- 原点への復帰を開始 ---")
        self.move_z_abs_pulse(config.SAFE_Z_PULSE)
        default_preset = presets.WELDING_PRESETS[config.DEFAULT_PRESET_NAME]
        self.move_xy_abs(0, 0, default_preset)
        self.log("--- 原点への復帰完了 ---")

    def final_return_to_origin(self):
        self.log("--- 全工程完了。最終退避位置へ移動後、原点へ復帰します ---")
        self.move_z_abs_pulse(config.FINAL_RETRACT_PULSE)
        default_preset = presets.WELDING_PRESETS[config.DEFAULT_PRESET_NAME]
        self.move_xy_abs(0, 0, default_preset)
        self.log("--- 原点復帰完了 ---")

    def emergency_stop(self):
        self.log("!!! 緊急停止作動。全モーターのトルクをOFF。 !!!")
        for dxl_id in config.DXL_IDS.values():
            self.dxl.disable_torque(dxl_id)

    def recover_from_stop(self):
        self.log("--- 復帰シーケンス開始 ---")
        self._setup_motors()
        self.log("全モーターのトルクをONにしました。")

    def shutdown(self):
        self.log("シャットダウン処理...")
        for dxl_id in config.DXL_IDS.values():
            self.dxl.disable_torque(dxl_id)
        self.dxl.disconnect()
        self.log("シャットダウン完了。")