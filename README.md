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
- web.py libraries for web.py version
- tornado libraries for tornado version

To install web and tornado libraries you must installed pip in you python environment. You can use pip or pip3
to install pip or pip3:

in Ubuntu       : sudo apt install python3-pip
in Debian Jessie: sudo apt-get install python-pip

To install web.py and tornado:

- pip install web.py
- pip install tornado

Additional resources: 

I was coding this two programs with pyCharm Jetbrains IDE. You can get it for free at: www.jetbrains.com/PyCharm

More information about lego EV3 development at http://www.ev3dev.org/
In this website you can change ev3 firmware with ev3dev firmware (more functionalities and languajes). 
In ev3dev.org you can get instructions to configure a dev environmet (git) with python, ev3dev firmware and pycharm
