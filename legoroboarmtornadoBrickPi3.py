#!/usr/bin/env python
#
# ev3dev-lang-python program for the Robot Arm H25 model that is part of
# the 45544 LEGO Education EV3 kit.
#
# Authors:
#    <ivan sampedro postigo: ivan.sampedro@oracle.com>
#

# We use import ev3dev.ev3 instead of ev3dev.auto because we only use ev3 devices

from multiprocessing import Process, Event
from threading import Thread
from _thread import start_new_thread
from ev3dev.brickpi3 import *
from tornado import web
from tornado import ioloop
from tornado import httpserver

import tornado
import logging
import requests

# URL requests to IOT JAVA
urlIOT = "http://192.168.1.28:8080/send_temp?bot=1&temp="
urlIOTTimeOut = 0.01

# while true loops timeout
WHILE_LOOP_TIMEOUT = 5000

# Tornado HttpServer Port
HTTP_SERVER_PORT = 8080

BASE_GEAR_RATIO = 12.0 / 36.0  # 12-tooth gear turn 36-tooth gear
LIFT_ARM_LIMIT = 40            # reflected light value (units: %)
LIFT_ARM_POS = 270             # vertical amount
BASE_EXTRA = 0.03              # to account for slop in gears (units: rotations)
SPEED_BASE = 150               # speed of base motor
SPEED_LIFT = 150               # speed of lift motor
TEMP_LIMIT = 300               # temp in C (no decimals) to stop arm fail simulation

# keyboard control (keypress)
button = ButtonBase()
keyPressed = 'a'

# init logger
logger = logging.getLogger(__name__)
logging.basicConfig(filename='roboarm.log',
                    level=logging.DEBUG,
                    filemode='w',
                    format='%(asctime)s %(levelname)8s: %(message)s')
# color the errors and warnings
logging.addLevelName(logging.FATAL, "\033[91m%s\033[0m" % logging.getLevelName(logging.FATAL))
logging.addLevelName(logging.ERROR, "\033[91m%s\033[0m" % logging.getLevelName(logging.ERROR))
logging.addLevelName(logging.WARNING, "\033[71m%s\033[0m" % logging.getLevelName(logging.WARNING))


class LegoRoboArm:
    def __init__(self):

        # variables init
        self.shutdown_flag = False
        self.arm_in_movement = False
        self.temp_present = True
        self.stop_event = Event()
        self.pro = Process(target=self.arm_movement)

        time.sleep(2)

        # setup the motors and sensors
        try:
            self.grab_motor = LargeMotor(OUTPUT_A)
            self.grab_motor.reset()
            self.grab_motor.stop_action = self.grab_motor.STOP_ACTION_BRAKE
        except:
            logger.fatal("Medium Motor (GRAB) not present in port A - " + str(sys.exc_info()[0]))
            sys.exit(-1)

        try:
            self.lift_motor = LargeMotor(OUTPUT_B)
            self.lift_motor.reset()
            self.lift_motor.stop_action = self.lift_motor.STOP_ACTION_HOLD
            # using polarity="inversed" so that lifting up is the positive direction
            # self.lift_motor.polarity = self.lift_motor.POLARITY_INVERSED
        except:
            logger.fatal("Large Motor (LIFT) not present in port B - " + str(sys.exc_info()[0]))
            sys.exit(-1)

        try:
            self.base_motor = LargeMotor(OUTPUT_D)
            self.base_motor.reset()
            self.base_motor.stop_action = self.base_motor.STOP_ACTION_HOLD
        except:
            logger.fatal("Large Motor (BASE) not present in port D - " + str(sys.exc_info()[0]))
            sys.exit(-1)

        try:
            self.base_limit_sensor = TouchSensor(INPUT_4)
            self.base_limit_sensor.mode = "TOUCH"
        except:
            try:
                logger.debug("TouchSensor not present in port S4 - creating sensor")

                p = LegoPort(INPUT_4)
                p.mode = "ev3-analog"
                p.set_device = "lego-ev3-touch"
                time.sleep(0.5)
                self.base_limit_sensor = TouchSensor(INPUT_4)
                self.base_limit_sensor.mode = "TOUCH"
            except:
                logger.fatal("TouchSensor not present in port S4 - " + str(sys.exc_info()[0]))
                sys.exit(-1)

        try:
            self.lift_limit_sensor = ColorSensor(INPUT_1)
            # Set the lift arm to a known position using the color sensor in reflect mode
            self.lift_limit_sensor.mode = "COL-REFLECT"
            logger.debug("Sensor LUZ: " + str(self.lift_limit_sensor.value(0)))
        except:
            try:
                logger.debug("ColorSensor not present in port S1 - creating sensor")
                p = LegoPort(INPUT_1)
                p.mode = "ev3-uart"
                p.set_device = "lego-ev3-color"
                time.sleep(0.5)
                self.lift_limit_sensor = ColorSensor(INPUT_1)
                self.lift_limit_sensor.mode = "COL-REFLECT"
            except:
                logger.fatal("ColorSensor not present in port S1 - " + str(sys.exc_info()[0]))
                sys.exit(-1)

        try:
            self.temperature_sensor = Sensor(str(INPUT_3) + ':i2c76')
            self.temperature_sensor.mode = "NXT-TEMP-C"
            try:
                logger.debug("TEMP: " + str(float(self.temperature_sensor.value() / 10.0)))
                requests.get(urlIOT + str(float(self.temperature_sensor.value()/10.0)), data='', timeout=urlIOTTimeOut)
            except requests.exceptions.ConnectionError as error:
                logger.error("AMCS Connection Error - " + str(error))
        except:
            try:
                logger.debug("TemperatureSensor not present in port S3 - creating sensor")
                p = LegoPort(INPUT_3)
                p.mode = "nxt-i2c"
                p.set_device = "lego-nxt-temp 0x4C"
                time.sleep(0.5)
                self.temperature_sensor = Sensor(str(INPUT_3) + ':i2c76')
                self.temperature_sensor.mode = "NXT-TEMP-C"
                time.sleep(0.5)
                logger.debug("TEMP: " + str(float(self.temperature_sensor.value() / 10.0)))
                requests.get(urlIOT + str(float(self.temperature_sensor.value() / 10.0)), data='', timeout=urlIOTTimeOut)
            except:
                logger.warning("No Temperature Sensor on port S3 - " + str(sys.exc_info()[0]))
                self.temp_present = False

        # if all went OK then init position vars

        try:
            logger.info("POSITION VARS:")
            self.base_position = int(self.base_motor.count_per_rot * (0.25 + BASE_EXTRA) / BASE_GEAR_RATIO)
            logger.info("- BASE POSITION: " + str(self.base_position))
            self.grab_position = int(self.grab_motor.count_per_rot * -0.25)  # 90 degrees
            logger.info("- GRAB POSITION: " + str(self.grab_position))
            self.lift_position = int(self.lift_motor.count_per_rot * LIFT_ARM_POS / 360.0)
            logger.info("- LIFT POSITION: " + str(self.lift_position))
            self.lift_initial_position = 0
        except:
            logger.fatal("Position vars not inicialized")
            sys.exit(-1)
        return

    def lift_move(self, speed, timeout=None):
        self.lift_motor.polarity = self.lift_motor.POLARITY_INVERSED
        self.lift_motor.run_forever(speed_sp=speed)
        tic = time.time()
        while self.lift_limit_sensor.value(0) <= LIFT_ARM_LIMIT \
                and self.lift_motor.STATE_OVERLOADED not in self.lift_motor.state:
            self.create_str_log_debug("[LIFT_MOVE] sensor value: ", str(self.lift_limit_sensor.value(0)) +
                                      " status: " + str(self.lift_motor.state), tic, timeout)
            if timeout is not None and time.time() >= tic + timeout / 1000:
                return False
        time.sleep(0.01)
        self.create_str_log_debug("[LIFT_MOVE] sensor value: ", str(self.lift_limit_sensor.value(0)) +
                                  " status: " + str(self.lift_motor.state), tic, timeout)
        return

    def lift_move_calup(self, speed, timeout=None):
        self.lift_motor.polarity = self.lift_motor.POLARITY_NORMAL
        self.lift_motor.run_forever(speed_sp=speed)
        tic = time.time()
        while self.lift_limit_sensor.value(0) > LIFT_ARM_LIMIT \
                and self.lift_motor.STATE_OVERLOADED not in self.lift_motor.state:
            self.create_str_log_debug("[LIFT_UP] sensor value: ", str(self.lift_limit_sensor.value(0)) +
                                      " status: " + str(self.lift_motor.state), tic, timeout)
            if timeout is not None and time.time() >= tic + timeout / 1000:
                return False
        time.sleep(0.01)
        self.create_str_log_debug("[LIFT_UP] sensor value: ", str(self.lift_limit_sensor.value(0)) +
                                  " status: " + str(self.lift_motor.state), tic, timeout)
        return

    def grab_close(self, speed):
        self.grab_motor.run_forever(speed_sp=speed)
        time.sleep(0.8)
        self.grab_motor.stop()
        return

    def grab_open(self, speed, grab_position, timeout=None):
        self.grab_motor.run_to_rel_pos(speed_sp=speed, position_sp=grab_position)
        tic = time.time()
        while self.grab_motor.STATE_RUNNING in self.grab_motor.state \
                and self.grab_motor.STATE_OVERLOADED not in self.grab_motor.state:
            self.create_str_log_debug("[GRAB_OPEN] status: ", str(self.grab_motor.state), tic, timeout)
            if timeout is not None and time.time() >= tic + timeout / 1000:
                return False
        time.sleep(0.01)
        self.create_str_log_debug("[GRAB_OPEN] FINAL status: ", str(self.grab_motor.state), tic, timeout)
        return

    def lift_move_pos(self, speed, position, timeout=None):
        # self.lift_motor.run_to_abs_pos(speed_sp=speed, position_sp=position)
        self.lift_motor.polarity = self.lift_motor.POLARITY_NORMAL
        logger.debug("[LIFT_MOVE] move to : " + str(position))
        self.lift_motor.run_to_rel_pos(speed_sp=speed, position_sp=position)
        tic = time.time()
        self.create_str_log_debug("[LIFT_DOWN] status: ", str(self.lift_motor.position) +
                                  " sensor: " + str(self.lift_limit_sensor.value(0)) +
                                  " state: " + str(self.lift_motor.state), tic, timeout)
        while self.lift_motor.STATE_HOLDING not in self.lift_motor.state \
                and self.lift_limit_sensor.value(0) <= (LIFT_ARM_LIMIT+7):
            self.create_str_log_debug("[LIFT_DOWN] status: ", str(self.lift_motor.position) +
                                      " sensor: " + str(self.lift_limit_sensor.value(0)) +
                                      " state: " + str(self.lift_motor.state), tic, timeout)
            if timeout is not None and time.time() >= tic + timeout / 1000:
                return False
        time.sleep(0.01)
        self.create_str_log_debug("[LIFT_DOWN] status: ", str(self.lift_motor.position) +
                                  " sensor: " + str(self.lift_limit_sensor.value(0)) +
                                  " state: " + str(self.lift_motor.state), tic, timeout)
        return

    def base_motor_touch(self, speed, timeout=None):
        self.base_motor.run_forever(speed_sp=speed)
        tic = time.time()
        while not self.base_limit_sensor.value(0):
            self.create_str_log_debug("[BASE_MOTOR_TOUCH] Touch value: ", str(self.base_motor.state), tic, timeout)
            if timeout is not None and time.time() >= tic + timeout / 1000:
                return False
        self.base_motor.stop()
        self.create_str_log_debug("[BASE_MOTOR_TOUCH] FINAL Touch value: ", str(self.base_motor.state), tic, timeout)

    def base_motor_to_position(self, speed, position, timeout=None):
        self.base_motor.run_to_rel_pos(speed_sp=speed, position_sp=position)
        tic = time.time()
        logger.debug("[BASE_MOTOR_POS] Status: " + str(self.base_motor.state))
        while self.base_motor.STATE_HOLDING not in self.base_motor.state \
                and self.base_motor.STATE_OVERLOADED not in self.base_motor.state:
            self.create_str_log_debug("[BASE_MOTOR_POS] Status: ", str(self.base_motor.state), tic, timeout)
            if timeout is not None and time.time() >= tic + timeout / 1000:
                return False
        self.create_str_log_debug("[BASE_MOTOR_POS] FINAL Status: ", str(self.base_motor.state), tic, timeout)

    def create_str_log_debug(self, str_base, str_status, tic=None, timeout=None):
        str_log = str_base + str_status
        if timeout is not None:
            str_log += " timeout: " + str(time.time() >= tic + timeout / 1000)
        logger.debug(str_log)

    def initialize(self):
        # Send Temp before initialize.
        try:
            logger.debug("[INITIALIZE][TEMPERATURE]: " + str(float(self.temperature_sensor.value() / 10.0)))
            requests.get(urlIOT + str(float(self.temperature_sensor.value() / 10.0)), data='', timeout=urlIOTTimeOut)
        except requests.exceptions.ConnectionError as error:
            logger.error("[INITIALIZE][AMCS] Connection Error - " + str(error))

        try:
            if self.lift_limit_sensor.value(0) > LIFT_ARM_LIMIT:
                self.lift_move_calup(SPEED_LIFT, WHILE_LOOP_TIMEOUT)
            else:
                self.lift_move(SPEED_LIFT, WHILE_LOOP_TIMEOUT)
            self.lift_motor.stop()
            self.lift_initial_position = self.lift_motor.position

            # Set the grabber to a known position by closing it all the way and then opening it
            self.grab_close(180)
            time.sleep(0.2)
            self.grab_open(600, self.grab_position, WHILE_LOOP_TIMEOUT)

            # set the base rotation to a known position using the touch sensor as a limit switch
            self.base_motor_touch(SPEED_BASE, WHILE_LOOP_TIMEOUT)
            time.sleep(0.01)
            logger.debug("[INITIALIZE][BASE-MOTOR-SENSOR]: " + str(self.base_limit_sensor.value(0)))
            logger.debug("[INITIALIZE][BASE-MOTOR] Position: " + str(self.base_motor.position))
            self.base_motor.position = self.base_position
            logger.debug("[INITIALIZE][BASE-MOTOR] Position: " + str(self.base_motor.position))
            self.base_motor_to_position(SPEED_BASE, int(self.base_motor.position - 50), WHILE_LOOP_TIMEOUT)
            self.base_motor.stop()
            time.sleep(0.01)
            if self.base_motor.STATE_OVERLOADED in self.base_motor.state:
                logger.error("[INITIALIZE][BASE-MOTOR] Motor OVERLOADED!!")
                sys.exit(-1)
            else:
                time.sleep(0.5)
                self.base_motor.reset()
                self.base_motor.stop_action = self.base_motor.STOP_ACTION_HOLD
                logger.debug("[INITIALIZE][BASE-MOTOR] Position   : " + str(self.base_motor.position))
                logger.debug("[INITIALIZE][BASE-MOTOR] Stop action: " + str(self.base_motor.stop_action))
        except:
            logger.fatal("[INITIALIZE][BASE-MOTOR] ERROR: " + str(sys.exc_info()[1]))
            sys.exit(-1)
        return

    def move(self, direction):
        # rotate the base 90 degrees and wait for completion
        logger.debug("[MOVE][MOTOR-BASE] MOVE_1 to : " + str(direction * self.base_position))
        self.base_motor_to_position(SPEED_BASE, (direction * self.base_position), WHILE_LOOP_TIMEOUT)
        self.base_motor.stop()
        time.sleep(0.01)
        if self.base_motor.STATE_OVERLOADED in self.base_motor.state:
            logger.error("[INITIALIZE][BASE-MOTOR] Motor OVERLOADED!!")
            sys.exit(-1)
        else:
            time.sleep(0.5)
            # lower the lift arm and wait for completion
            logger.debug("[MOVE][MOTOR-LIFT] MOVE_2... LIFT DOWN")
            self.lift_move_pos(SPEED_LIFT, self.lift_position, WHILE_LOOP_TIMEOUT)

            # grab an object
            logger.debug("[MOVE][MOTOR-GRAB] MOVE_3 GRAB OBJECT")
            self.grab_close(180)

            # raise the lift to the limit
            logger.debug("[MOVE][MOTOR-LIFT] MOVE_4... LIFT UP")
            self.lift_move(SPEED_LIFT, WHILE_LOOP_TIMEOUT)
            self.lift_motor.stop()

            # rotate the base back to the center position and wait for completion
            logger.debug("[MOVE][MOTOR-BASE] MOVE_5 to : " + str(direction * -self.base_position))
            self.base_motor_to_position(SPEED_BASE, (direction * -self.base_position), WHILE_LOOP_TIMEOUT)
            self.base_motor.stop()
            time.sleep(0.01)
            if self.base_motor.STATE_OVERLOADED in self.base_motor.state:
                logger.error("[MOVE][BASE-MOTOR] Motor OVERLOADED!!")
                sys.exit(-1)
            else:
                # lower the lift arm and wait for completion
                self.lift_move_pos(SPEED_LIFT, self.lift_position, WHILE_LOOP_TIMEOUT)
                time.sleep(0.2)
                # release the object
                self.grab_open(600, self.grab_position, WHILE_LOOP_TIMEOUT)

                # raise the lift arm to the limit
                time.sleep(0.5)
                self.lift_move(SPEED_LIFT, WHILE_LOOP_TIMEOUT)
                self.lift_motor.stop()
        return

    def arm_movement(self):
        logger.debug("[ARM_MOVEMENT] start arm movement. ")
        while True:
            if self.temp_present and self.temperature_sensor.value() != '':
                logger.debug("TEMP: " + str(self.temperature_sensor.value()))
            self.move(1)
            time.sleep(1)
            self.move(-1)
            time.sleep(1)
            if self.temp_present:
                logger.debug("TEMP: " + str(float(self.temperature_sensor.value()/10.0)))

    def infinite_movement(self):
        log.debug("[INFINITE_MOVEMENT] preparing arm new process.")
        try:
            self.pro.daemon = True
            self.pro.start()
            if not self.temp_present:
                logger.info("[INFINITE_MOVEMENT] Started TEMP SENSOR NOT PRESENT.")
                while not self.stop_event.is_set():
                    self.stop_event.wait(1)
            else:
                logger.info("INFINITE_MOVEMENT] Started with TEMP SENSOR.")
                while not self.stop_event.is_set() and int(self.temperature_sensor.value()) < TEMP_LIMIT:
                    self.stop_event.wait(1)
            if self.pro is not None:
                self.pro.terminate()
                self.stop()
                logger.debug("[INFINITE_MOVEMENT] infinite movement terminated!")
            self.pro = Process(target=self.arm_movement)
            time.sleep(1)
            self.arm_in_movement = False
            self.stop_event.clear()
        except:
            logger.error("[INFINITE_MOVEMENT] error: " + str(sys.exc_info()))
        return

    def create_infinite_movement(self):
        result = ""

        logger.info("[INFINITE_MOVEMENT] status: " + str(self.arm_in_movement))
        if self.arm_in_movement:
            # if arm is moving, a second call could create problems
            logger.info("[INFINITE_MOVEMENT] arm moving, move arm call discard.")
            result = "arm moving, call discarted"
        else:
            self.arm_in_movement = True
            logger.debug("[INFINITE_MOVEMENT] status: " + str(self.arm_in_movement))
            result = "arm movement initialized"
            try:
                start_new_thread(self.infinite_movement, ())
            except:
                logger.error("[INFINITE_MOVEMENT] Error: " + str(sys.exc_info()))
            time.sleep(1)
        return result

    def create_initialize(self):
        result = ""

        logger.info("[CREATE_INITIALIZE] status: " + str(self.arm_in_movement))
        if self.arm_in_movement:
            # if arm is moving, a second call could create problems
            logger.info("[CREATE_INITIALIZE] arm moving, initialize arm call discard.")
            result = "arm moving, initialize call discarted"
        else:
            logger.debug("[CREATE_INITIALIZE] status: " + str(self.arm_in_movement))
            result = "initialized"
            try:
                self.initialize()
            except:
                logger.error("[CREATE_INITIALIZE] Error: " + str(sys.exc_info()))
            time.sleep(1)
        return result

    def shutdown_roboarm(self):
        logger.info("[SHUTDOWN_ROBOARM] Stopping robot.")
        # self.shutdown_flag = True
        self.stop_event.set()
        time.sleep(1)

        return False

    def stop(self):
        try:
            if self.pro is not None:
                self.pro.terminate()

            self.grab_motor.stop()
            self.lift_motor.stop_action = self.lift_motor.STOP_ACTION_BRAKE
            self.lift_motor.stop()

            self.base_motor.stop_action = self.base_motor.STOP_ACTION_BRAKE
            self.base_motor.stop()

            self.lift_limit_sensor.mode = self.lift_limit_sensor.MODE_COL_REFLECT
            self.grab_motor.reset()
            self.lift_motor.reset()
            self.lift_motor.stop_action = self.lift_motor.STOP_ACTION_HOLD

            self.base_motor.reset()
            self.base_motor.stop_action = self.base_motor.STOP_ACTION_HOLD
        except:
            logger.error("[STOP] Error stopping roboarm" + str(sys.exc_info()))

    def get_temperature(self):
        logger.debug("[GET_TEMPERATURE] value: " + str(float(self.temperature_sensor.value() / 10.0)))
        return str(float(self.temperature_sensor.value()/10.0))


class GetTemperature(tornado.web.RequestHandler):
    def get(self):
        try:
            logger.info("GET Temperature received!")
            self.set_header("Content-Type", "text/json")
            result = roboarm.get_temperature()
            self.write({"temperature": result})
            self.flush()
            self.finish()
            logger.debug("GET Temperature sended!")
            return
        except:
            logger.fatal("Start_movement error: " + str(sys.exc_info()))


class StartMovement(tornado.web.RequestHandler):
    async def get(self):
        try:
            logger.info("GET start_movement received!")
            self.set_header("Content-Type", "text/json")
            result = roboarm.create_infinite_movement()
            self.write({"movement": result})
            logger.debug("[STARTMOVEMENT] Thread infinite movement launched!")
            self.flush()
            self.finish()
            return
        except:
            logger.fatal("Start_movement error: " + str(sys.exc_info()))


class StopMovement(tornado.web.RequestHandler):
    def get(self):
        try:
            logger.info("GET stop_movement received!")
            self.set_header("Content-Type", "text/json")
            self.write({"movement": "stopped"})
            roboarm.shutdown_roboarm()
            self.flush()
            self.finish()
            return
        except:
            logger.fatal("Stop_movement error: " + str(sys.exc_info()))


class Initialize(tornado.web.RequestHandler):
    def get(self):
        try:
            logger.info("GET initialize received!")
            self.set_header("Content-Type", "text/json")
            result = roboarm.create_initialize()
            self.write({"movement": result})
            self.flush()
            self.finish()
            return
        except:
            logger.fatal("Initialize error: " + str(sys.exc_info()))


class MyApplication(tornado.web.Application):
    def __init__(self):
        try:
            # variables init
            handlers = [(r"/move_start/", StartMovement),
                        (r"/move_stop/", StopMovement),
                        (r"/initialize/", Initialize),
                        (r"/get_temperature/", GetTemperature),
                        ]
            super(MyApplication, self).__init__(handlers)
            logger.debug("Web Server Initialize. ShutDown Flag - " + str(roboarm.shutdown_flag))
        except:
            logger.fatal("StartMovement Error" + str(sys.exc_info()))


if __name__ == "__main__":
    try:
        roboarm = LegoRoboArm()
        app = MyApplication()

        # start the web server
        try:
            logger.info("Launching webserver port(" + str(HTTP_SERVER_PORT) + ")")
            server = tornado.httpserver.HTTPServer(app)
            server.bind(HTTP_SERVER_PORT)
            server.start(1)  # Forks multiple sub-processes
            ioloop.IOLoop.current().start()
            logger.info("Closing webserver")
        except:
            logger.error('Could not START REST API web server ' + str(sys.exc_info()))
            ioloop.IOLoop.current().stop()
            roboarm.shutdown_roboarm()
            roboarm.stop()
            exit(-1)
    except:
        time.sleep(1)
        ioloop.IOLoop.current().stop()
        if str(sys.exc_info()[0]) != 'SystemExit':
            if sys.exc_info()[1] < 0:
                logger.fatal("Exit Program: " + str(sys.exc_info()[1]))
                sys.exit(-1)
            else:
                sys.exit(0)