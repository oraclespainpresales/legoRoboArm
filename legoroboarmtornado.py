#!/usr/bin/env python
#
# ev3dev-lang-python program for the Robot Arm H25 model that is part of
# the 45544 LEGO Education EV3 kit.
#
# Authors:
#    <ivan sampedro postigo: ivan.sampedro@oracle.com>
#

# We use import ev3dev.ev3 instead of ev3dev.auto because we only use ev3 devices


from multiprocessing import Process
from threading import Thread
from ev3dev.ev3 import *
from tornado import ioloop
from tornado import web
from tornado import gen
from tornado import httpserver

import logging
import tornado
import asyncio

BASE_GEAR_RATIO = 12.0 / 36.0  # 12-tooth gear turn 36-tooth gear
LIFT_ARM_LIMIT = 40            # reflected light value (units: %)
LIFT_ARM_POS = 270             # vertical amount
BASE_EXTRA = 0.06              # to account for slop in gears (units: rotations)
SPEED_BASE = 150               # speed of base motor
SPEED_LIFT = 150               # speed of lift motor
TEMP_LIMIT = 300               # temp in C (no decimals) to stop arm fail simulation

logger = logging.getLogger(__name__)
button = Button()
sound = Sound()


# init logger
logging.basicConfig(filename='roboarm.log',
                    level=logging.DEBUG,
                    format='%(asctime)s %(levelname)8s: %(message)s')
# color the errors and warnings
logging.addLevelName(logging.FATAL, "\033[91m%s\033[0m" % logging.getLevelName(logging.FATAL))
logging.addLevelName(logging.ERROR, "\033[91m%s\033[0m" % logging.getLevelName(logging.ERROR))
logging.addLevelName(logging.WARNING, "\033[71m%s\033[0m" % logging.getLevelName(logging.WARNING))


class LegoRoboArm:

    def __init__(self):

        # variables init
        self.shutdown_flag = False
        self.temp_present = True
        self.pro = Process(target=self.infinite_movement)

        time.sleep(2)
        sound.speak("WEDO Robo Arm Initialiting")

        # setup the motors and sensors
        try:
            self.grab_motor = MediumMotor(OUTPUT_D)
            self.grab_motor.reset()
            self.grab_motor.stop_action = self.grab_motor.STOP_ACTION_HOLD
        except Exception as error:
            logger.fatal("Medium Motor (GRAB) not present in port D - " + str(error))
            raise Exception("Medium Motor (GRAB) not present in port D") from error

        try:
            self.lift_motor = LargeMotor(OUTPUT_B)
            self.lift_motor.reset()
            self.lift_motor.stop_action = self.lift_motor.STOP_ACTION_HOLD
            # using polarity="inversed" so that lifting up is the positive direction
            self.lift_motor.polarity = self.lift_motor.POLARITY_INVERSED
        except Exception as error:
            logger.fatal("Large Motor (LIFT) not present in port B - " + str(error))
            sys.exit(-1)

        try:
            self.base_motor = LargeMotor(OUTPUT_C)
            self.base_motor.reset()
            self.base_motor.stop_action = self.base_motor.STOP_ACTION_HOLD
        except Exception as error:
            logger.fatal("Large Motor (BASE) not present in port C - " + str(error))
            exit(-1)

        try:
            self.base_limit_sensor = TouchSensor(INPUT_1)
            self.base_limit_sensor.mode = self.base_limit_sensor.MODE_TOUCH
        except Exception as error:
            logger.fatal("TouchSensor not present in port 1 - " + str(error))
            sys.exit(-1)

        try:
            self.lift_limit_sensor = ColorSensor(INPUT_3)
            # Set the lift arm to a known position using the color sensor in reflect mode
            self.lift_limit_sensor.mode = self.lift_limit_sensor.MODE_COL_REFLECT
            logger.debug("Sensor LUZ: " + str(self.lift_limit_sensor.value(0)))
        except Exception as error:
            logger.fatal("ColorSensor not present in port 3 - " + str(error))
            sys.exit(-1)

        try:
            self.temperature_sensor = Sensor(INPUT_4)
            self.temperature_sensor.mode = "NXT-TEMP-C"
            logger.debug("TEMP: " + str(float(self.temperature_sensor.value()/10.0)))
        except Exception as error:
            logger.warning("No Temperature Sensor on port 4 - " + str(error))
            self.temp_present = False

        # if all went OK then init position vars

        try:
            logger.info("POSITION VARS")
            self.base_position = int(self.base_motor.count_per_rot * (0.25 + BASE_EXTRA) / BASE_GEAR_RATIO)
            logger.info(str(self.base_position))
            self.grab_position = int(self.grab_motor.count_per_rot * -0.25)  # 90 degrees
            logger.info(str(self.grab_position))
            self.lift_position = int(self.lift_motor.count_per_rot * LIFT_ARM_POS / 360.0)
            logger.info(str(self.lift_position))
            self.lift_initial_position = 0
        except:
            logger.fatal("Position vars not inicialized")
            sys.exit(-1)

    def lift_move(self, speed):
        self.lift_motor.run_forever(speed_sp=speed)
        while self.lift_limit_sensor.value(0) <= LIFT_ARM_LIMIT:
            # logger.debug("sensor_luz: " + str(self.lift_limit_sensor.value(0)))
            pass

    def lift_move_calup(self, speed):
        self.lift_motor.polarity = self.lift_motor.POLARITY_NORMAL
        self.lift_motor.run_forever(speed_sp=speed)
        while self.lift_limit_sensor.value(0) > LIFT_ARM_LIMIT:
            pass
        self.lift_motor.polarity = self.lift_motor.POLARITY_INVERSED

    def lift_move_pos(self, speed, position):
        # self.lift_motor.run_to_abs_pos(speed_sp=speed, position_sp=position)
        self.lift_motor.run_to_rel_pos(speed_sp=speed, position_sp=position)
        while self.lift_motor.STATE_HOLDING not in self.lift_motor.state:
            # logger.debug(str(self.lift_motor.state))
            pass

    def initialize(self):
        try:
            Leds.set_color(Leds.LEFT, Leds.AMBER)
            if self.lift_limit_sensor.value(0) > LIFT_ARM_LIMIT:
                Leds.set_color(Leds.LEFT, Leds.RED)
                self.lift_move_calup(SPEED_LIFT)
            else:
                Leds.set_color(Leds.LEFT, Leds.BLACK)
                self.lift_move(SPEED_LIFT)
            self.lift_motor.stop()
            self.lift_initial_position = self.lift_motor.position

            print("Posicion Inicial: ", self.lift_initial_position)
            Leds.set_color(Leds.LEFT, Leds.GREEN)

            # Set the grabber to a known position by closing it all the way and then opening it

            Leds.set_color(Leds.RIGHT, Leds.AMBER)
            self.grab_motor.run_forever(speed_sp=400)
            time.sleep(1)
            self.grab_motor.run_to_rel_pos(speed_sp=600, position_sp=self.grab_position)
            Leds.set_color(Leds.RIGHT, Leds.GREEN)

            # set the base rotation to a known position using the touch sensor as a limit switch

            Leds.set_color(Leds.LEFT, Leds.AMBER)
            self.base_motor.run_forever(speed_sp=SPEED_BASE)
            while not self.base_limit_sensor.value(0):
                pass
            Leds.set_color(Leds.LEFT, Leds.RED)
            self.base_motor.stop()
            self.base_motor.position = self.base_position
            self.base_motor.run_to_abs_pos(speed_sp=SPEED_BASE, position_sp=0)
            while self.base_motor.STATE_RUNNING in self.base_motor.state:
                pass
            Leds.set_color(Leds.LEFT, Leds.GREEN)
            time.sleep(1)
            sound.speak("Arm Ready!")
        except:
            logger.fatal("Error: " + str(sys.exc_info()[0]))
            sys.exit(-1)

    def move(self, direction):
        # rotate the base 90 degrees and wait for completion
        print("Posicion base agarrar:", self.base_position)
        self.base_motor.run_to_abs_pos(speed_sp=SPEED_BASE, position_sp=direction * self.base_position)
        while self.base_motor.STATE_HOLDING not in self.base_motor.state:
            pass

        # lower the lift arm and wait for completion

        print("Posicion sp: ", self.lift_motor.position_sp)
        print("Posicion brazo: ", -self.lift_position)
        self.lift_move_pos(SPEED_LIFT, -self.lift_position)

        # grab an object

        print("coge objeto")
        self.grab_motor.run_forever(speed_sp=400)
        time.sleep(1)
        self.grab_motor.stop()

        # raise the lift to the limit

        self.lift_move(SPEED_LIFT)
        self.lift_motor.stop()

        # rotate the base back to the center position and wait for completion

        print("posicion base soltar:", -self.base_position)
        self.base_motor.run_to_abs_pos(speed_sp=SPEED_BASE, position_sp=direction * -self.base_position)
        while self.base_motor.STATE_HOLDING not in self.base_motor.state:
            pass

        # lower the lift arm and wait for completion

        print("Posicion brazo: ", -self.lift_position)
        self.lift_move_pos(SPEED_LIFT, -self.lift_position)

        # release the object

        print("suelta objeto")
        self.grab_motor.run_to_rel_pos(speed_sp=600, position_sp=self.grab_position)
        while self.grab_motor.STATE_HOLDING not in self.grab_motor.state:
            pass

        # raise the lift arm to the limit

        self.lift_move(SPEED_LIFT)
        self.lift_motor.stop()

    def stop(self):
        try:
            if self.pro is not None:
                print("no es NONE")
                self.pro.terminate()
        except:
            logger.warning("Process terminated")
        self.lift_limit_sensor.mode = self.lift_limit_sensor.MODE_COL_REFLECT
        self.grab_motor.reset()
        self.lift_motor.reset()
        self.base_motor.reset()

    def infinite_movement(self):
        while True:
            self.move(1)
            time.sleep(2)
            self.move(-1)
            time.sleep(1)
            if self.temp_present:
                print("TEMP: ", float(self.temperature_sensor.value()/10.0))

    def start_inf(self):
        pth = Thread(target=self.start_infinite_movement())
        pth.daemon = True
        pth.start()

    def start_infinite_movement(self):
        try:
            self.shutdown_flag = False
            self.pro.start()
            if not self.temp_present:
                while "backspace" not in button.buttons_pressed:
                    asyncio.sleep(2)
                    if self.shutdown_flag:
                        return
            else:
                while self.temperature_sensor.value() < TEMP_LIMIT and "backspace" not in button.buttons_pressed:
                    asyncio.sleep(2)
                    if self.shutdown_flag:
                        return
            if self.pro is not None:
                self.pro.terminate()
            self.pro = Process(target=self.infinite_movement)
            time.sleep(1)
            sound.speak("Warning. Warning. Failure Detected!")
            time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
            time.sleep(1)
            sound.speak("Good Bye!").wait()

    def shutdown_roboarm(self):
        self.shutdown_flag = True
        # self.stop()

    def run(self):
        while True:
            time.sleep(2)

            if self.shutdown_flag:
                logger.debug("Robo ARM shutdown!")
                return


class StartMovement(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    def get(self):
        try:
            logger.debug("GET start_movement received!")
            self.set_header("Content-Type", "text/json")
            self.finish({"movement": "started"})
            self.flush()
            ioloop.IOLoop.current().spawn_callback(self.inf_movement_corutine())
            logger.debug("Infinite movement LAUNCHED!")
            return
        except:
            logger.fatal("Start_movement error: " + str(sys.exc_info()))

    @tornado.gen.coroutine
    def inf_movement_corutine(self):
        roboarm.start_inf()


class StopMovement(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    def get(self):
        try:
            logger.debug("GET stop_movement received!")
            self.set_header("Content-Type", "text/json")
            self.finish({"movement": "stoped"})
            self.flush()
            roboarm.shutdown_roboarm()
            return
        except:
            logger.fatal("Stop_movement error: " + str(sys.exc_info()))


class Initialize(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    def get(self):
        try:
            logger.debug("GET initialize received!")
            self.set_header("Content-Type", "text/json")
            self.finish({"command": "initialize"})
            self.flush()
            roboarm.initialize()
            logger.debug("Initialize Robot Arm LAUNCHED!")
            return
        except:
            logger.fatal("Initialize error: " + str(sys.exc_info()))


def make_app():
    return tornado.web.Application([
        (r"/move_start/", StartMovement),
        (r"/move_stop/", StopMovement),
        (r"/initialize/", Initialize),
    ])


if __name__ == "__main__":
    try:
        roboarm = LegoRoboArm()

        app = tornado.httpserver.HTTPServer(make_app())
        app.listen(8080)

        # start the web server
        try:
            logger.debug('Launching webserver')
            ioloop.IOLoop.instance().start()
            logger.debug('Closing webserver')
        except:
            logger.error('Could not START REST API web server ' + str(sys.exc_info()))
            ioloop.IOLoop.current().stop()
            roboarm.shutdown_roboarm()
            roboarm.stop()
            exit(-1)
    except:
        time.sleep(1)
        if str(sys.exc_info()[0]) != 'SystemExit':
            if sys.exc_info()[1] < 0:
                logger.fatal("Exit Program: " + str(sys.exc_info()[1]))
                sys.exit(-1)
            else:
                sys.exit(0)