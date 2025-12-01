# dynamixel_controller.py

import os
import time
import config
from dynamixel_sdk import *

# コントロールテーブルのアドレス
ADDR_TORQUE_ENABLE = 64
ADDR_OPERATING_MODE = 11
ADDR_GOAL_VELOCITY = 104
ADDR_GOAL_POSITION = 116
ADDR_PRESENT_POSITION = 132
ADDR_GOAL_CURRENT = 102
ADDR_PRESENT_CURRENT = 126
ADDR_PROFILE_VELOCITY = 112
ADDR_PROFILE_ACCELERATION = 108
ADDR_MOVING = 122
ADDR_ACCELERATION_LIMIT = 40
ADDR_POSITION_P_GAIN = 800

class DynamixelController:
    def __init__(self, log_callback=print):
        self.log = log_callback
        self.portHandler = PortHandler(config.DEVICENAME)
        self.packetHandler = PacketHandler(config.DXL_PROTOCOL_VERSION)
        self.log("  [HW] Dynamixelコントローラを初期化しました。")

    def connect(self, devicename):
        if self.portHandler.openPort():
            self.log(f"  [HW] Dynamixelポート '{devicename}' のオープンに成功。")
        else:
            self.log(f"  [HW] エラー: Dynamixelポート '{devicename}' のオープンに失敗。");
            return False
        if self.portHandler.setBaudRate(config.DXL_BAUDRATE):
            self.log(f"  [HW] ボーレートを {config.DXL_BAUDRATE} に設定しました。")
        else:
            self.log(f"  [HW] エラー: ボーレートの設定に失敗。");
            return False
        return True

    def disconnect(self):
        self.portHandler.closePort()
        self.log("  [HW] Dynamixelポートの接続を解除しました。")

    def _check_error(self, dxl_comm_result, dxl_error, dxl_id, operation):
        if dxl_comm_result != COMM_SUCCESS:
            self.log(f"  [HW] エラー (ID:{dxl_id}, {operation}): {self.packetHandler.getTxRxResult(dxl_comm_result)}");
            return False
        elif dxl_error != 0:
            self.log(f"  [HW] エラー (ID:{dxl_id}, {operation}): {self.packetHandler.getRxPacketError(dxl_error)}");
            return False
        return True

    def ping(self, dxl_id):
        _, dxl_comm_result, dxl_error = self.packetHandler.ping(self.portHandler, dxl_id)
        return self._check_error(dxl_comm_result, dxl_error, dxl_id, "Ping")

    def enable_torque(self, dxl_id):
        dxl_comm_result, dxl_error = self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_TORQUE_ENABLE, 1)
        if self._check_error(dxl_comm_result, dxl_error, dxl_id, "Torque ON"):
            self.log(f"  [HW] モーターID {dxl_id} のトルクをONにしました。")

    def disable_torque(self, dxl_id):
        dxl_comm_result, dxl_error = self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_TORQUE_ENABLE, 0)
        if self._check_error(dxl_comm_result, dxl_error, dxl_id, "Torque OFF"):
            self.log(f"  [HW] モーターID {dxl_id} のトルクをOFFにしました。")

    def set_operating_mode(self, dxl_id, mode):
        self.disable_torque(dxl_id)
        dxl_comm_result, dxl_error = self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_OPERATING_MODE,
                                                                       mode)
        if self._check_error(dxl_comm_result, dxl_error, dxl_id, "Set Mode"):
            self.log(f"  [HW] モーターID {dxl_id} の動作モードを {mode} に設定。")
        self.enable_torque(dxl_id)

    def set_profile(self, dxl_id, velocity, acceleration):
        self.packetHandler.write4ByteTxRx(self.portHandler, dxl_id, ADDR_PROFILE_VELOCITY, velocity)
        self.packetHandler.write4ByteTxRx(self.portHandler, dxl_id, ADDR_PROFILE_ACCELERATION, acceleration)
        self.log(f"  [HW] モーターID {dxl_id} のプロファイルを設定: V={velocity}, A={acceleration}")

    def set_current_limit(self, dxl_id, current_ma):
        current_pulse = int(current_ma / 2.69)
        dxl_comm_result, dxl_error = self.packetHandler.write2ByteTxRx(self.portHandler, dxl_id, ADDR_GOAL_CURRENT,
                                                                       current_pulse)
        if self._check_error(dxl_comm_result, dxl_error, dxl_id, "Set Current Limit"):
            self.log(f"  [HW] ID {dxl_id} の電流制限値を {current_ma}mA (pulse:{current_pulse}) に設定。")

    def set_goal_current(self, dxl_id, current_ma):
        current_pulse = int(current_ma / 2.69)
        dxl_comm_result, dxl_error = self.packetHandler.write2ByteTxRx(self.portHandler, dxl_id, ADDR_GOAL_CURRENT,
                                                                       current_pulse)
        self._check_error(dxl_comm_result, dxl_error, dxl_id,
                          f"Set Goal Current: {current_ma}mA (pulse:{current_pulse})")

    def set_goal_velocity(self, dxl_id, velocity_pulse):
        dxl_comm_result, dxl_error = self.packetHandler.write4ByteTxRx(self.portHandler, dxl_id, ADDR_GOAL_VELOCITY,
                                                                       velocity_pulse)
        self._check_error(dxl_comm_result, dxl_error, dxl_id, f"Set Goal Velocity: {velocity_pulse}")

    def set_goal_position(self, dxl_id, position_pulse):
        dxl_comm_result, dxl_error = self.packetHandler.write4ByteTxRx(self.portHandler, dxl_id, ADDR_GOAL_POSITION,
                                                                       position_pulse)
        self._check_error(dxl_comm_result, dxl_error, dxl_id, f"Set Goal Pos: {position_pulse}")

    def read_present_position(self, dxl_id):
        try:
            # tryブロックで囲むことで、SDK内部のエラーをキャッチします
            dxl_present_position, dxl_comm_result, dxl_error = self.packetHandler.read4ByteTxRx(self.portHandler,
                                                                                                dxl_id,
                                                                                                ADDR_PRESENT_POSITION)
            if self._check_error(dxl_comm_result, dxl_error, dxl_id, "Read Position"):
                return dxl_present_position
        except Exception as e:
            # エラーが発生した場合はログを出して -1 (失敗) を返す
            self.log(f"  [HW] 警告: 位置読み取りで例外が発生しました (ID:{dxl_id}) - {e}")
            pass

        return -1

    def read_present_current(self, dxl_id):
        dxl_present_current, dxl_comm_result, dxl_error = self.packetHandler.read2ByteTxRx(self.portHandler, dxl_id,
                                                                                           ADDR_PRESENT_CURRENT)
        if self._check_error(dxl_comm_result, dxl_error, dxl_id, "Read Current"):
            if dxl_present_current > 32767:
                dxl_present_current -= 65536
            return int(dxl_present_current * 2.69)
        return -1

    def is_moving(self, dxl_id):
        is_moving_val, dxl_comm_result, dxl_error = self.packetHandler.read1ByteTxRx(self.portHandler, dxl_id,
                                                                                     ADDR_MOVING)
        if self._check_error(dxl_comm_result, dxl_error, dxl_id, "Read IsMoving"):
            return is_moving_val == 1
        return False

    def set_acceleration_limit(self, dxl_id, acceleration_limit):
        dxl_comm_result, dxl_error = self.packetHandler.write4ByteTxRx(self.portHandler, dxl_id,
                                                                       ADDR_ACCELERATION_LIMIT, acceleration_limit)
        if self._check_error(dxl_comm_result, dxl_error, dxl_id, f"Set Accel Limit: {acceleration_limit}"):
            self.log(f"  [HW] モーターID {dxl_id} の加速度制限値を設定: {acceleration_limit}")

    def set_position_p_gain(self, dxl_id, p_gain):
        # Pゲインは 2バイトデータなので write2ByteTxRx を使用
        dxl_comm_result, dxl_error = self.packetHandler.write2ByteTxRx(
            self.portHandler, dxl_id, ADDR_POSITION_P_GAIN, p_gain
        )
        if self._check_error(dxl_comm_result, dxl_error, dxl_id, f"Set P-Gain: {p_gain}"):
            self.log(f"  [HW] モーターID {dxl_id} の Position P Gain を {p_gain} に設定しました。")