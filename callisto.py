#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""Simple package to handle the operation of callisto spectrometer and its calibration unit in Linux using system callisto binary files available for major distributions, TCP connection to send signals to spectrometer and serial connection to control relay switch in Calibration Unit.

@Author: Luciano Barosi
@Date: 15.04.2022
@Links: https://github.com/lbarosi/callisto

"""
#----------------------------
#----------------------------
__license__ = "GPL"
__version__ = "1.0.1"
__maintainer__ = "Luciano Barosi"
__email__ = "lbarosi@df.ufcg.edu.br"
__status__ = "Development"
#----------------------------
#----------------------------
from io import StringIO
import multiprocessing
import os
import sys
import serial
import shlex
import signal
import socket
import subprocess
#----------------------------
import pandas as pd
#----------------------------
#----------------------------
# Wow, a global variable. Long time no see!
VERSION = "Version: ETHZ Arduino_PrototypeV85.ino; 2016-08-17/cm"
#----------------------------
#----------------------------
# Module functions
def run_command(command):
    """Execute given command string as a shell process."""
    process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = process.communicate()
    return (out, err)

def run_detached(command):
    """Execute the given command in a separate thread and continue execution."""
    process = multiprocessing.Process(target = run_command, args=command)
    process.start()
    result = process.pid
    return result
#----------------------------
# CLASS
#----------------------------
class Callisto:
    """Class `Callisto` controls the operation of spectrometer in manual mode via command line and tcp connection."""
    def __init__(self, IP=None, PORT=6789, fits_command="start", ovs_command="overview", stop_command="stop", quit_command="quit", daemon="callisto.service", executable="/usr/sbin/callisto", cal_unit=None):
        self.IP = IP
        self.PORT = PORT
        self.fits_command = fits_command
        self.ovs_command = ovs_command
        self.stop_command = stop_command
        self.quit_command = quit_command
        self.daemon = daemon
        self.executable = executable
        self.cal_unit = cal_unit

    def get_ip(self):
        """Retrieve local IP."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0)
        try:
            # doesn't even have to be reachable
            sock.connect(('10.255.255.255', 1))
            self.IP = sock.getsockname()[0]
        except Exception:
            self.IP = '127.0.0.1'
        finally:
            sock.close()
        return self

    def get_PID(self):
        """Determine PID of callisto process running as daemon and return a list with IPs of an empty list. Uses system `ps`."""
        try:
            command = "ps aux"
            process_name = "callisto"
            # Run in place, do not detach this.
            ps = subprocess.run(shlex.split(command), check=True, capture_output=True)
            processNames = subprocess.run(shlex.split('grep ' + process_name), input=ps.stdout, capture_output=True)
            if processNames.stdout.decode():
                # very roundabout way to get all hits in ps command into a dataframe for proper parsing.
                df_ps = pd.read_table(StringIO(processNames.stdout.decode()), header=None)[0].str.split(' +', expand=True)
                # PID is list.
                PID = df_ps[df_ps[10] == process_name][1].values.tolist()
            else:
                PID = []
        except subprocess.CalledProcessError as err:
            print("Could not retrieve PID information for callisto: {}.".format(err))
        return PID

    def run_daemon(self, manager="sudo /bin/systemctl", action="start"):
        """Start callisto daemon."""
        # Safe to as forgiveness in thread, systemd service stop always behave nicely.
        try:
            command = manager + " " + action + " " + self.daemon
            result = run_detached(command)
            return result
        except OSError as err:
            print("Something went wrong when starting the Daemon: {}".format(err))
            return None
        return

    def stop(self):
        """Stop every instance of callisto program running. First stops de systemd service, that aggresively kills all remaining processess. Needs sudoer rules inplace."""
        # Stop daemon
        self.run_daemon(action="stop")
        # Check any stray processes.
        PIDs = self.get_PID()
        try:
            #[ os.kill(int(PID), signal.SIGSTOP) for PID in PIDs if PIDs ]
            # Aggressive kill should be re-examined.
            # Need to include sudoers rule to pkill.
            # Is there a better way to kill other users process that may be running callisto?
            subprocess.run(shlex.split("sudo pkill " + self.executable))
        except PermissionError as err:
            print("Could not kill all callisto instances. Trying via tcp later and hoping for the best.")
            pass
        return


    def run(self, mode):
        """Run a manual measurement with callisto in the `mode` determined in the argument. Appropriate config files should be present."""
        # This is a manual run that load a config file, need to first stop all running processes.
        self.stop()
        try:
            command = self.executable + " --config /etc/callisto/callisto_" + str(mode) + ".cfg"
            result = run_detached(command)
            return result
        except OSError as err:
            print("run_callisto Smothing went wrong when starting the Daemon: {}".format(err))
            return None
        return

    def connect(self):
        """Create socket for TCP connection with callisto software."""
        if not self.IP:
            self.get_ip()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_address = (self.IP, self.PORT)
            sock.connect(server_address)
        except socket.error as err:
            print("Caught exception {}".format(err))
        return sock


    def do_callisto(self, command=None):
        """Open tcp socket to control callisto program."""
        if self.get_PID():
            try:
                sock = self.connect()
                sock.sendall(command.encode())
                sock.shutdown(socket.SHUT_RDWR)
                sock.close()
            except socket.error as err:
                print("do_callisto Caught exception {}".format(err))
                pass
        return self

    def record_ovs(self, mode):
        """Run a single manual spectrum overview."""
        self.run(mode)
        self.do(self.stop_command)
        self.do(self.ovs_command)
        self.do(self.stop_command)
        return

    def record_fits(self, mode):
        """Run a single manual fits measurement."""
        self.run_callisto(mode)
        self.do_callisto(self.stop_command)
        self.do_callisto(self.fits_command)
        self.do_callisto(self.stop_command)
        return

    def _calibrate(self, mode):
        """Measure for calibration in single mode of operation."""
        # Set control unit in correct mode.
        self.cal_unit.set_relay(mode)
        # Run measurementes
        self.record_ovs()
        self.record_fits()
        # Always go back to sky mode.
        self.cal_unit.set_relay("SKY")
        return

    def calibrate(self):
        """Calibrate all modes."""
        if self.cal_unit.check():
            # Start COLD calibration.
            for mode in ["COLD", "WARM", "HOT"]:
                self._calibrate(mode)
            self.do_callisto(self.stop_command)
            self.run_daemon(action="start")
        return
#----------------------------
# CLASS
#----------------------------
class CalibrationUnit():
    """Class `CalibrationUnit` controls the arduino which, in turn, controls the relay switched in the calibration unit of callisto spectrometer via serial port."""

    def __init__(self, tty="/dev/ttyACM0", baudrate=9600, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=1, version=VERSION):
        self._tty = tty
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self.serial = None
        self.version = version
        return

    @property
    def tty(self):
        return self._tty

    @tty.setter
    def tty(self, tty):
        self._tty = tty

    def connect(self):
        """Star serial connection with arduino in calibration unit."""
        self.serial = serial.Serial(self.tty, self.baudrate, self.bytesize, self.parity, self.stopbits, timeout=1)
        return self

    def check(self):
        """Check if device in serial may respond as a Callisto Callibration Unit by checking the version of software being used."""
        try:
            self.connect()
            self.serial.write(b"V?\n")
            response = self.serial.readline().decode(encoding='UTF-8',errors='strict').strip()
            if response == self.version:
                result = True
            else:
                result = False
        except serial.SerialException as err:
            print("Ops: {}".format(err))
            result = False
            pass
        return result

    def set_relay(self, mode):
        """Set relay state in calibration unit."""
        try:
            if mode == "COLD":
                command = b"Tcold\n"
            elif mode == "WARM":
                command = b"Twarm\n"
            elif mode == "HOT":
                command = b"Thot\n"
            elif mode == "SKY":
                command = b"Tsky\n"
            else:
                print("Mode unkown.")
            self.connect()
            result = self.serial.write(command)
            self.serial.close()
        except serial.SerialTimeoutException as err:
            print("Mode {} not set - Timeout: {}".format(mode, err))
        finally:
            self.serial.close()
        return

#----------------------------
# MAIN
#----------------------------
def main():
    cal_unit = CalibrationUnit(tty="/dev/ttyACM0")
    callisto = Callisto(PORT=6789, cal_unit=cal_unit)
    callisto.calibrate()

if __name__ == "__main__":
    main()
#----------------------------
#----------------------------
