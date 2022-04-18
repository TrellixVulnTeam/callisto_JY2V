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
# ----------------------------
# ----------------------------
from io import StringIO
import logging
import multiprocessing
import shlex
import socket
import subprocess
import threading
import time
# ----------------------------
import pandas as pd
import serial
import watchdog.events
from watchdog.observers import Observer
# ----------------------------
# ----------------------------
# Wow, a global variable. Long time no see!
VERSION = "Version: ETHZ Arduino_PrototypeV85.ino; 2016-08-17/cm"
# ----------------------------
# ----------------------------
# Module functions


def run_command(command):
    """Execute given command string as a shell process."""
    process = subprocess.Popen(
                                shlex.split(command),
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE
                                )
    out, err = process.communicate()
    return (out, err)


def run_detached(command):
    """Execute the given command in separate thread and continue execution."""
    process = multiprocessing.Process(
                                      target=run_command,
                                      args=(command,),
                                      daemon=True
                                      )
    process.start()
    result = process.pid
    return result


class Handler(watchdog.events.PatternMatchingEventHandler):
    def __init__(self, pattern=None):
        """Handler to watchdog filesystem checker."""
        # Set the patterns for PatternMatchingEventHandler
        watchdog.events.PatternMatchingEventHandler.__init__(self,
        patterns=[pattern], ignore_directories=True, case_sensitive=False)
        self.created = False

    def on_created(self, event):
        logging.info("File created: {}".format(event.src_path))
        self.created = True


class WatchFolder:
    """WatchDog Class."""

    def __init__(self, path=None, recursive=False, pattern=None, watch_time=None):
        self.observer = Observer()
        self.path = path
        self.recursive= recursive
        self.pattern = pattern
        self.watch_time = watch_time

    def run(self):
        event_handler = Handler(pattern=self.pattern)
        self.observer.schedule(
                                event_handler,
                                path=self.path,
                                recursive = self.recursive
                                )
        self.observer.start()
        start_time = time.perf_counter()
        try:
            while not event_handler.created:
                if time.perf_counter() - start_time > float(self.watch_time):
                    logging.error("Taking too long to create {}. Aborting.".format(self.pattern))
                    break
        except Exception as err:
            self.observer.stop()
            logging.error("Something went wrong while watching filesystem: {}".err)
        finally:
            self.observer.stop()
        self.observer.join()


class Callisto:
    """Class `Callisto` controls the operation of spectrometer in manual
       mode via command line and tcp connection.
    """

    def __init__(self, IP=None, PORT=6789, fits_command="start",
                 ovs_command="overview", stop_command="stop",
                 quit_command="quit", daemon="callisto.service",
                 executable="callisto", cal_unit=None):
        self.IP = IP
        self.PORT = PORT
        self.fits_command = fits_command
        self.ovs_command = ovs_command
        self.stop_command = stop_command
        self.quit_command = quit_command
        self.daemon = daemon
        self.executable = executable
        self.cal_unit = cal_unit
        self.ovs_folder = "/opt/callisto/Ovs"
        self.data_folder = "/opt/callisto/data"

    def get_ip(self):
        """Retrieve local IP."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0)
        try:
            # doesn't even have to be reachable
            sock.connect(('10.255.255.255', 1))
            self.IP = sock.getsockname()[0]
        except socket.error:
            # No netword deafult to local host.
            self.IP = '127.0.0.1'
        finally:
            sock.close()
        return self

    def get_PID(self):
        """Determine PID of callisto process running as daemon and return a
        list with IPs of an empty list. Uses system `ps`.
        """

        try:
            command = "ps aux"
            process_name = "callisto"
            # Run in place, do not detach this.
            process = subprocess.run(shlex.split(command),
                                     check=True,
                                     capture_output=True
                                     )
            processNames = subprocess.run(shlex.split('grep ' + process_name),
                                          input=process.stdout,
                                          capture_output=True
                                          )
            if processNames.stdout.decode():
                # very roundabout way to get all hits in ps command into a dataframe for proper parsing.
                df_ps = pd.read_table(StringIO(processNames.stdout.decode()),
                                      header=None)[0].str.split(' +', expand=True)
                # PID is list.
                PID = df_ps[df_ps[10].str.contains(process_name)][1].values.tolist()
            else:
                PID = []
        except subprocess.CalledProcessError as err:
            print("Could not retrieve PID information for callisto: {}.".format(err))
        return PID

    def is_running(self):
        time_start = time.perf_counter()
        while self.get_PID():
            if time.perf_counter() - time_start > 10:
                logging.error("Taking too long ot die.")
                break
        return

    def run_daemon(self, manager="sudo /bin/systemctl", action="start"):
        """Start callisto daemon."""
        try:
            command = manager + " " + action + " " + self.daemon
            result = run_detached(command)
            return result
        except OSError as err:
            # Non fatal error - PASS
            logging.error("Something went wrong when starting the Daemon: {}".format(err))
            pass
        return

    def stop(self):
        """Stop every instance of callisto program running. First stops de systemd service, that aggresively kills all remaining processess. Needs sudoer rules inplace."""
        # Stop daemon
        self.run_daemon(action="stop")
        # Check any stray processes.
        PIDs = self.get_PID()
        try:
            #subprocess.run(shlex.split("sudo pkill " + self.executable.split("/")[-1]))
            thread = threading.Thread(target=self.is_running)
            thread.start()
            result = run_detached("pkill callisto")
            thread.join()
        except PermissionError as err:
            logging.error("Could not kill all callisto instances. Trying via tcp later and hoping for the best.")
            pass
        return

    def run(self, mode):
        """Run a manual measurement with callisto in the `mode` determined in the argument. Appropriate config files should be present."""
        # This is a manual run that load a config file, need to first stop all running processes.
        self.stop()
        try:
            command = self.executable + " --config /etc/callisto/callisto_" + str(mode) + ".cfg"
            #result = run_detached(command)
            result = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE)
        except OSError as err:
            logging.error("run_callisto Smothing went wrong when starting the Daemon: {}".format(err))
            return None
        return

    def connect(self, timeout=5):
        """Create socket for TCP connection with callisto software."""
        if not self.IP:
            self.get_ip()
        start_time = time.perf_counter()
        while True:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server_address = (self.IP, self.PORT)
                sock.settimeout(timeout)
                sock.connect(server_address)
                break
            except OSError as ex:
                time.sleep(1)
                if time.perf_counter() - start_time >= 10 * timeout:
                    raise TimeoutError('Waited too long for host')
        return sock

    def do(self, command=None):
        """Open tcp socket to control callisto program."""
        if self.get_PID():
            try:
                command = command + "\n"
                sock = self.connect()
                sock.sendall(command.encode())
                sock.shutdown(socket.SHUT_RDWR)
                sock.close()
            except socket.error as err:
                logging.error("do_callisto Caught exception {}".format(err))
                pass
        return

    def record_ovs(self, mode, time=180):
        """Run a single manual spectrum overview."""
        # Set control unit in correct mode.
        self.cal_unit.set_relay(mode)
        self.run(mode)
        self.do(self.stop_command)
        self.do(self.ovs_command)
        watch = WatchFolder(path=self.ovs_folder, pattern="*.PRN", watch_time=time)
        watch.run()
        self.do(self.stop_command)
        return

    def record_fits(self, mode, time=1200):
        """Run a single manual fits measurement."""
        # Set control unit in correct mode.
        self.cal_unit.set_relay(mode)
        self.run(mode)
        self.do(self.stop_command)
        self.do(self.fits_command)
        watch = WatchFolder(path=self.data_folder, pattern="*.fit", watch_time=time)
        watch.run()
        self.do(self.stop_command)
        return

    def _calibrate(self, mode):
        """Measure for calibration in single mode of operation."""
        # Run measurementes
        self.record_ovs(mode)
        self.record_fits(mode)
        # Always go back to sky mode.
        #self.cal_unit.set_relay("SKY")
        return

    def calibrate(self, timeout=1):
        """Calibrate all modes."""
        start_time = time.perf_counter()
        while True:
            try:
                arduino_ok = self.cal_unit.check()
                if arduino_ok:
                    break
            except OSError as ex:
                time.sleep(1)
                if time.perf_counter() - start_time >= 10 * timeout:
                    raise TimeoutError('Waited too long for arduino.')
        if arduino_ok:
            logging.info("Full calibration started")
            for mode in ["COLD", "WARM", "HOT"]:
                self._calibrate(mode)
            self.stop()
            self.run_daemon(action="start")
            self.cal_unit.set_relay("SKY")
            logging.info("Full calibration finished")
        else:
            logging.error("calibration unit did not responded.")
        return
# ----------------------------
# CLASS
# ----------------------------
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
        try:
            self.serial = serial.Serial(self.tty, self.baudrate, self.bytesize, self.parity, self.stopbits, timeout=5)
        except serial.SerialException as err:
            logging.error("Could not connect to arduino: {}".format(err))
            pass
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
            logging.error("Fail to connect to callibration unit: {}".format(err))
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
            time.sleep(1)
        except serial.SerialTimeoutException as err:
            logging.error("Mode {} not set - Timeout: {}".format(mode, err))
        finally:
            self.serial.close()
        return

# ----------------------------
# MAIN
# ----------------------------
def main():
    handler = logging.FileHandler("/opt/callisto/log/callisto.log")
    formatter = logging.Formatter(
        '%(asctime)s %(name)-12s %(levelname)-8s %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    cal_unit = CalibrationUnit(tty="/dev/ttyACM0")
    callisto = Callisto(PORT=6789, cal_unit=cal_unit)
    callisto.calibrate()

if __name__ == "__main__":
    main()
# ----------------------------
# ----------------------------
