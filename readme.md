# Running Callisto Spectrometer in Linux

Callisto spectrometer has packages to run with major linux distributions, including raspian. Nevertheless, Linux distribution lacks some important functionalities which are important to controll calibration unit.

Since the callibration unit is controlled by an ARDUINO UNO whose serial port is available to external communication, it is possible to combine the funcionalities of the command line utility with some funcionalities to control the serial port.

The instalation script `install.sh` should be run as privileged user or you may take a look into it and adapt to your needs.

The basic procedure is:
- Create user and set permissions to use the serial port and appropriate folders.
- Create a directory structure with configuration files in `/etc`
- Install callisto as a system service.
- Install a python script that will handle the serial port communication and some manual tweaking to change focus code.
- Install service as a cron job.

In order to the python script to be able to control the daemon, there must be a configuration in sudoers to allow access to the script.
