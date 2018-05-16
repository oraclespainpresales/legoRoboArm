# legoRoboArm
python 3.4 code for lego mondstorm ev3 H25 roboArm. 

Two codes available:

legoroboarmweb.py ---> python code with web.py webserver to send commands to roboarm
legoroboarmtornado.py --> python code with tornado webserver to send commands to roboarm. 

Web.py is a blocking webserver and API coded in python. http://webpy.org
Tornado is a non-blocking webserver and API coded in python. http://www.tornadoweb.org/en/stable/#

To run this project you'll need:

- A lego mindstorm EV3 H25 roboarm (build instructions on http://robotsquare.com/wp-content/uploads/2013/10/45544_robotarmh25.pdf)
- Wifi dondle for EV3 controller (wifi enable)
- Temperature sensor to simulate a roboarm failure
- web.py libraries for web.py version
- tornado libraries for tornado version

To install web and tornado libraries you must installed pip in you python environment. You can use pip or pip3
to install pip or pip3:

in Ubuntu       : sudo apt install python3-pip
in Debian Jessie: sudo apt-get install python-pip

To install web.py and tornado:

- sudo pip install web.py
- sudo pip install tornado

Additional resources: 

I'm coding this two programs with pyCharm Jetbrains IDE. You can get it for free at: www.jetbrains.com/PyCharm

More information about lego EV3 development at http://www.ev3dev.org/

In this website you can get a new firmware to change lego ev3 firmware with ev3dev firmware (more functionalities and languajes, including python 3.4 version).

In ev3dev.org you can get instructions to configure a dev environmet (git) with python, ev3dev firmware and pycharm

To execute the python scripts you must copy them in the ev3 controller.
You can access to the linux jessie of ev3 controller with putty.

- User: robot
- pass: maker

Next chmod +x <script_name>.py
Next python3 <script_name>.py

If you exit the script with CTRL+Z, webserver and two process could get defunc state. To avoid memory leaks or problem with defunc process you culd execute:

ps -al 

and search the defunc process, take note of PPID field

kill -9 <PPID>

All defunc process with the same PPID will be killed
