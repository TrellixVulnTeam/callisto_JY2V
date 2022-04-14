#!/usr/bin/python3
"""
Module with definitions for handling callisto and its calibration unit.
Implement classes for command line and serial port.
"""
import os
import sys
import serial
import shlex
import socket
import subprocess


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
        """Determina IP da máquina local.

        Returns:
            str: IP.
        """
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
        """Determine PID of callisto process running as daemon."""
        try:
            file = open(self.PIDFile)
            PID = file.readline()
            file.close()
        except FileNotFoundError as err:
            PID = None
        return PID

    def connect(self):
        """Create socket for TCP connection with callisto software."""
        if not self.IP:
            self.get_ip()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_address = (self.IP, self.PORT)
        try:
            sock.connect(server_address)
        except socket.error as err:
            print("Caught exception {}".format(err))
        return sock

    def check_daemon(self):
        """Check if callisto is running as daemon;"""
        if self.get_PID():
            # Daemon is already running
            return self.get_PID()
        else:
            return None

    def run_daemon(self, manager="sudo /bin/systemctl", action="start"):
        """Start callisto daemon."""
        try:
            command = manager + " " + action + " " + self.daemon
            process = subprocess.Popen(shlex.split(command), check=True)
            result = self.get_PID()
            return result
        except subprocess.CalledProcessError as err:
            print("Smothing went wrong when starting the Daemon: {}".format(err))
            return None
        return

    def run_callisto(self, mode):
        """Run a manual measurement with callisto in the `mode` determined in the argument. Appropriate config files should be present."""
        if self.check_daemon():
            # Manual operation. First kill any running daemon.
            self.run_daemon(action="stop")
        try:
            # Manual operation. Kill any stray callisto program via tcp.
            self.do_callisto(self.quit_command)
            command = self.executable + "--config /etc/callisto/callisto_" + str(mode) + ".cfg"
            # Run callisto with appropriate configuration file in manual mode.
            process = subprocess.Popen(shlex.split(command), check=True)
            result = self.get_PID()
            return result
        except subprocess.CalledProcessError as err:
            print("Smothing went wrong when starting the Daemon: {}".format(err))
            return None
        return

    def do_callisto(self, command=None):
        """Open tcp socket to control callisto program."""
        try:
            sock = self.connect()
            sock.sendall(command)
        except socket.error as err:
            print("Caught exception {}".format(err))
        finally:
            sock.shutdown(socket.SHUT_RDWR)
            sock.close()
        return self

    def record_ovs(self, conf=None):
        """Run a single manual spectrum overview."""
        self.run_callisto()
        self.do_callisto(self.stop_command)
        self.do_callisto(self.ovs_command)
        self.do_callisto(self.stop_command)
        return

    def record_fits(self, conf=None):
        """Run a single manual fits measurement."""
        self.run_callisto()
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


class CalibrationUnit():
    """Class `CalibrationUnit` controls the arduino which, in turn, controls the relay switched in the calibration unit of callisto spectrometer via serial port."""

    def __init__(self, tty="/dev/ttyACM0"):
        self._tty = tty
        self.baudrate = 9600
        self.bytesize = serial.EIGHTBITS
        self.parity = serial.PARITY_NONE
        self.stopbits = serial.STOPBITS_ONE
        self.timeout = 1
        self.serial = None
        return

    @property
    def tty(self):
        return self._tty

    @tty.setter
    def tty(self, tty):
        self._tty = tty

    def connect(self):
        """Star serial connection with arduino in calibration unit."""
        self.serial = serial.Serial(self.tty, self.baudrate, self.bytesize, self.stopbits, timeout=1)
        return self

    def check(self):
        """To be implemented."""
        return True

    def set_relay(self, mode):
        """Set relay state in calibration unit."""
        try:
            if mode == "COLD":
                command = b"Tcold"
            elif mode == "WARM":
                command = b"Twarm"
            elif mode == "HOT":
                command = b"Thot"
            elif mode == "SKY":
                command = b"Tsky"
            else:
                print("Mode unkown.")
            self.connect()
            result = self.serial.write(command)
        except serial.SerialTimeoutException as err:
            print("Mode {} not set - Timeout: {}".format(mode, err))
        finally:
            self.serial.close()
        return result

def main():
    cal_unit = CalibrationUnit(tty="/dev/ttyACM0")
    callisto = Callisto(PORT=6789, cal_unit=cal_unit):
    callisto.calibrate()

if __name__ == "__main__":
    main()
