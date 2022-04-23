#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""Pacote de controle do espectrômetro Callisto e de sua unidade de calibração em sistemas tipo Linux. Depende do binário callisto da distribuição Linux e utiliza conexão TCP e conexão serial.

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
import os
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
I_AM_NOT_CALLISTO = "does not seem to be Callisto"
SCHEDULER_EMPTY = "Loaded schedule is empty"
I_AM_ARDUINO = "Version: ETHZ Arduino_PrototypeV85.ino; 2016-08-17/cm"
# ----------------------------
# Module functions
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def run_command(command: str) -> tuple[str, str]:
    """Executa comando shell passado como argumento utilizando biblioteca `subprocess`.

    Função reporta erro no arquivo de log se houver algum erro que não represente a informação do binário callisto de que não detectou o arquivo scheduler, uma vez que este não é um erro e apenas uma informação do status desejado.

    Args:
        command (str): string de comando escrita da mesma forma que se escreveria em linha de comando.

    Returns:
        tuple[str, str]: saída padrão e código de erro informado para o comando executado.
    """
    process = subprocess.Popen(
                                shlex.split(command),
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE
                                )
    out, err = process.communicate()
    if err:
        err = err.decode("utf-8")
        if SCHEDULER_EMPTY not in err:
            logging.error("Error running command {}:{}".format(command, err))
    return (out, err)

def run_detached(command: str) -> multiprocessing.Process:
    """Roda o comando indicado em modo background, liberando a execução do resto do programa.

    Args:
        command (str): string de comando escrita da mesma forma que se escreveria em linha de comando.

    Returns:
        multiprocessing.Process: processo em execução.

    """
    try:
        process = multiprocessing.Process(
                                          target=run_command,
                                          args=(command,),
                                          daemon=True
                                          )
        process.start()
    except OSError as error:
        logger.error("Detached program {} failed to execute: {}".format(command, error))
    return process


class Handler(watchdog.events.PatternMatchingEventHandler):
    """Implementa o gerenciador de eventos de arquivos utilizado em conjunto com o file watchdog.

    Para o módulo callisto só é necessário implementar o método que lida com a criação de arquivos, encarregada de acompanhar a execução das operações do binário callisto e permitir a verificação do sucesso das operações.

    Args:
        pattern (str): máscara para observar os arquivos `pattern`. Padrão é  None.

    Attributes:
        created (bool): determina se arquivo satisfazendo a máscara foi ou não criado.

    """
    def __init__(self, pattern: str=None):
        """Gerenciados para o observador de arquivos watchdog filesystem checker."""
        watchdog.events.PatternMatchingEventHandler.__init__(self,
        patterns=[pattern], ignore_directories=True, case_sensitive=False)
        self.created = False

    def on_created(self, event):
        """Chamada quando um arquivo satisfazendo a máscara é criado.

        Args:
            event (DirCreatedEvent or FileCreatedEvent): Evento representando a criação de arquivo ou diretório.
        """
        logger.info("File created: {}".format(event.src_path))
        self.created = True


class WatchFolder:
    """Monitoramento contínuo de eventos de arquivos e diretórios baseado no pacote `watchdog`.

    Args:
        path (str): caminho completo onde observar os arquivos. Defaults to None.
        recursive (bool): Defaults to False.
        pattern (str): máscara para vigiar arquivos. Defaults to None.
        timeout (float): `timeout` em segundos para manter vigiando o caminho indicado. Defaults to None.

    Attributes:
        observer (watchdog.observers): `observer`.
    """

    def __init__(self, path: str=None, recursive: bool=False, pattern: str=None, timeout: float=None):
        self.observer = Observer()
        self.path = path
        self.recursive= recursive
        self.pattern = pattern
        self.timeout = timeout

    def run(self):
        """Inicia observação do caminho indicado.

        Vigia a alteração (criação, modificação, deleção de arquivos ou diretórios) e manipula conforme o `handler` o evento que ocorreu.
        """
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
                if time.perf_counter() - start_time > float(self.timeout):
                    logger.error("Taking too long to create {}. Aborting.".format(self.pattern))
                    break
        except Exception as err:
            self.observer.stop()
            logger.error("Something went wrong while watching filesystem: {}".err)
        finally:
            self.observer.stop()
        self.observer.join()


class Callisto:
    """Representa um objeto Callisto espéctrôpmetro e implementa todos os métodos necessários para garantir sua operação.

    Args:
        IP (str): Endereço `IP` da máquina conectada ao Callisto. Defaults to None.
        PORT (int): Número da `PORT` para conexão TCP. Defaults to 6789.
        fits_command (str): descrição do comando utilizado pelo binário calllisto para modo de medida FIT. Defaults to "start".
        ovs_command (str): descrição do comando utilizado pelo binário para realizar medida em modo overview. Defaults to "overview".
        stop_command (str): descrição do comando utilizado pelo binário para parar a observação. Defaults to "stop".
        quit_command (str): descrição do comando utilizado pelo binário para desconectar da porta TCP. Defaults to "quit".
        daemon (str): nome do serviço `systemd`. Defaults to "callisto.service".
        executable (str): nome do binário controlador. Defaults to "callisto".
        cal_unit (CalibrationUnit): objeto callisto.CallibrationUnit representando a unidade de calibração e os métodos necessários para operá-la. Defaults to None.
    """

    def __init__(self, IP: str=None, PORT: int=6789, fits_command: str="start",
                 ovs_command: str="overview", stop_command: str="stop",
                 quit_command: str="quit", daemon: str="callisto.service",
                 executable: str="callisto", cal_unit: str=None):
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
        """Obtem IP da máquina local ao tentar realizar uma conexão com `socket`. Se resultado não é bem sucedido retorna o IP padrão do localhost 127.0.0.1."""
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
        return self.IP

    def get_PID(self):
        """Determina o número dos processos callisto rodando na máquina local, emulando o comportamento de `ps aux |grep callisto`.

        Returns:
            list: lista contendo números dos procesos ou lista vazia se nenhum processo encontrado.
        """
        command = "ps aux"
        process_name = "callisto"
        response, _ = run_command(command)
        # very roundabout way to get all hits in ps command into a dataframe for proper parsing.
        df_ps = pd.read_table(StringIO(response.decode("utf-8")),
                              header=None)[0].str.split(' +', expand=True)
        PID = df_ps[df_ps[10].str.contains(process_name)][1].values.tolist()
        return PID

    def is_running(self, timeout: float=5):
        """Cria loop bloqueando execução enquanto callisto estiver rodando.

        Args:
            timeout (float): tempo máximo em secundos para aguardar execução do programa. Defaults to 5.
        """
        time_start = time.perf_counter()
        while self.get_PID():
            result = True
            if time.perf_counter() - time_start > timeout:
                logger.error("Taking too long ot die.")
                return result
        result = False
        return


    def run_daemon(self, manager: str="sudo /bin/systemctl", action: str="start"):
        """Roda o serviço systemd com a ação especificada no argument.

        A execução do programa é realizada em thread separada e colocada em background, sobrevivendo a execução do script.

        Args:
            manager (str): caminho completo to controlador do daemon. Defaults to "sudo /bin/systemctl".
            action (str): Ação a ser executada, dentre as opções disponíveis em processos daemon: (start|stop|reload). Defaults to "start".
        """
        command = manager + " " + action + " " + self.daemon
        run_detached(command)
        return

    def stop(self):
        """Para o daemon callisto se este estiver rodando e envia SIGTERM para todas as instâncias do binário que estiverem rodando. Funciona apenas se regras sudoer adequadas tiverem sido implementadas para o comando `sudo pkill callisto`."""
        # Stop daemon
        self.run_daemon(action="stop")
        # Check any stray processes.
        PIDs = self.get_PID()
        try:
            # Try to kill and wait for killing to finish before proceed.
            job1 = multiprocessing.Process(target=self.is_running)
            job1.start()
            job2 = run_detached("pkill callisto")
            job1.join()
            job2.join()
        except PermissionError as err:
            logger.error("Could not kill all callisto instances. Trying via tcp later and hoping for the best.")
            pass
        return

    def run(self, mode: str):
        """Operação manual do espectrômetro callisto no modo epecificado no argumento.

        Para qualquer processo que estiver rodando, inicia novo processo com arquivo de configuração adequado ao modo (SKY|COLD|WARM|HOT) mas não executa nenhuma ação adicional, deixando sistema pronto para iniciar medida.

        Utiliza função `run_command` para executyar comando shell e retorna STDOUT, STDERR.
        """
        # This is a manual run that load a config file, need to first stop all running processes.
        self.stop()
        command = self.executable + " --config /etc/callisto/callisto_" + str(mode) + ".cfg"
        response, error = run_command(command)
        if I_AM_NOT_CALLISTO in error:
            logger.error("Could not communicate with Callisto in USB port."
                         "Trying again.")
            time.sleep(5)
            response, error = run_command(command)
            if error:
                logger.error("Device report that it is not Callisto. Aborting.")
        return response, error

    def connect(self, timeout:float=2) -> socket.socket:
        """Cria socket para conexão TCP com o binário callisto.

        Args:
            timeout (float): tempo padrão para aguardar resposta, em segundos. Defaults to 2.

        Returns:
            socket.socket: Socket para comunicação aberto.

        """
        if not self.IP:
            self.get_ip()
        start_time = time.perf_counter()
        try:
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
        except (ConnectionRefusedError, TimeoutError) as err:
            logger.error("Callisto took too lon to answer TCP.")
            pass
        return sock

    def do(self, command: str=None):
        """Envia comando via TCP para o binário callisto se este estiver rodando.

        Seve ser utilizado após o comando `run` que de fato inicia o binário e carrega arquivo de configuração apropriado.

        Args:
            command (str): comando TCP a ser enviado. Opções válidas: (start|stop|quit|overview).
        """
        if self.get_PID():
            try:
                command = command + "\n"
                sock = self.connect()
                sock.sendall(command.encode())
                sock.shutdown(socket.SHUT_RDWR)
                sock.close()
            except socket.error as err:
                logger.error("do_callisto Caught exception {}".format(err))
                pass
        return

    def record_ovs(self, mode: str, time: float=180):
        """Realiza medida manual única, tipo spectral overview no modo especificado e vigia sistema de arquivos para verificar sucesso.

        Args:
            mode (str): modo válido para os relays da unidade calibradora (SKY|COLD|WARM|HOT).
            time (float): tempo para esperar a criação de um arquivo PRN no caminho padrão da classe. Defaults to 180.
        """
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
        """Realiza medida manual única, tipo FIT no modo especificado e vigia sistema de arquivos para verificar sucesso.

        Args:
            mode (str): modo válido para os relays da unidade calibradora (SKY|COLD|WARM|HOT).
            time (float): tempo para esperar a criação de um arquivo PRN no caminho padrão da classe. Defaults to 1200.
        """
        # Set control unit in correct mode.
        self.cal_unit.set_relay(mode)
        self.run(mode)
        self.do(self.stop_command)
        self.do(self.fits_command)
        watch = WatchFolder(path=self.data_folder, pattern="*.fit", watch_time=time)
        watch.run()
        self.do(self.stop_command)
        return

    def _calibrate(self, mode: str):
        """Método privado realiza operações necessárias para calibração para cada módulo separadamente.

        Inicia binário, carrega configurações do modo, faz observação em modo overview e observação em modo FIT.

        Args:
            mode (str): (SKY|COLD|WARM|HOT).
        """
        # Run measurementes
        self.record_ovs(mode)
        self.record_fits(mode)
        # Always go back to sky mode.
        #self.cal_unit.set_relay("SKY")
        return

    def calibrate(self, timeout=1):
        """Realiza calibração completa com os modos de operação COLD, WARM e HOT, salvando PRN e FIT nos diretórios especificados nos atributos da classe.

        Ao terminar a calibração inicia o daemon de sistema."""
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
            logger.info("Full calibration started")
            for mode in ["COLD", "WARM", "HOT"]:
                self._calibrate(mode)
                self.stop()
            self.run_daemon(action="start")
            self.cal_unit.set_relay("SKY")
            logger.info("Full calibration finished")
        else:
            logger.error("calibration unit did not responded.")
        return
# ----------------------------
# CLASS
# ----------------------------
class CalibrationUnit():
    """Controla o arduino da unidade de calibração do callisto via porta serial. Os parâmetros são muito customizáveis.

    Args:
        tty (str):dispositivo serial do sistema. Defaults to "/dev/ttyACM0".
        baudrate (int): Defaults to 9600.
        bytesize (type): Defaults to serial.EIGHTBITS.
        parity (type): Defaults to serial.PARITY_NONE.
        stopbits (type): Defaults to serial.STOPBITS_ONE.
        timeout (int): tempo de resposta do arduino. Defaults to 1.
        version (str): string que representa versã do arduino para verificar se programa esta falando com arduino correro. Defaults to I_AM_ARDUINO.
    """

    def __init__(self, tty: str="/dev/ttyACM0", baudrate: int=9600, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout: int=1, version: str=I_AM_ARDUINO):
        """Construtor da classe de calibração. Todas as propriedades da porta serial podem ser configuradas. A única realmente fundamental é a port `tty`.

        Parameters
        ----------
        tty :
        baudrate :
        bytesize :
        parity :
        stopbits :
        timeout :
        version : str
            check arduino version to confirm it is callisto calibration unit `version`.
        """

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
        """Inicia conexão serial."""
        try:
            self.serial = serial.Serial(self.tty, self.baudrate, self.bytesize, self.parity, self.stopbits, timeout=1)
        except serial.SerialException as err:
            logger.error("Could not connect to arduino: {}".format(err))
            pass
        return self

    def listen(self):
        """Ouve resposta da porta serial."""
        response = self.serial.readlines()
        if isinstance(response, list):
            response = "".join([line.decode('UTF-8',errors='strict').strip() for line in response])
        elif isinstance(response, bytes):
            response = response.decode('UTF-8',errors='strict').strip()
        else:
            response = None
        return response

    def check(self):
        """Verifica se dispositivo responde a informação de sua versão corretamente."""
        try:
            response = self.send_command(b"V?\n")
            if self.version in response:
                result = True
            else:
                result = False
        except serial.SerialException as err:
            logger.error("Fail to connect to callibration unit: {}".format(err))
            result = False
            pass
        return result

    def send_command(self, command):
        """Envia comando para a porta serial e acompanha sua execução e código de resposta."""
        response = None
        try:
            self.connect()
            result = self.serial.write(command)
            time.sleep(0.05)
            response = self.listen()
            if "illegal" in response:
                logger.error("ARDUINO reported illegal command:{}".format(command))
                return False
            else:
                return response
        except serial.SerialTimeoutException as err:
            logger.error("Command {} dit not work - Timeout: {}".format(command, err))
            return False
        finally:
            self.serial.close()
        return


    def set_relay(self, mode):
        """Define estado do relay SKY|COLD|WARM|HOT"""
        response = None
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
            return False
        response = self.send_command(command)
        return response

# ----------------------------
# MAIN
# ----------------------------
def main():
    """Roda programa principal do módulo."""
    handler = logging.FileHandler("/opt/callisto/log/callisto.log")
    formatter = logging.Formatter(
        '%(asctime)s %(name)-12s %(levelname)-8s %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    mod_parser = argparse.ArgumentParser(
        description="Callisto.py controlador do espectrômetro Callisto."
        )
    mod_parser.add_argument(
        "-a", "--action", type=str,
        help="action to be taken: start|start-service|overview|stop"
        )
    mod_parser.add_argument(
        "-m", "--mode", type=str,
        help="mode: SKY|COLD|WARM|HOT"
    )
    valid_actions = ["start", "start-service", "overview", "stop"]
    valid_modes = ["SKY", "COLD", "HOT", "WARM"]

    args = mod_parser.parse_args()
    action = args.action
    mode = args.mode

    if not action:
        cal_unit = CalibrationUnit(tty="/dev/ttyACM0")
        callisto = Callisto(PORT=6789, cal_unit=cal_unit)
        callisto.calibrate()

    if mode in valid_modes:
        logger.info("Operação manual por linha de comando."
                    "action = {} - mode = {}".format(action, mode))
        print("Operação manual por linha de comando."
                    "action = {} - mode = {}".format(action, mode))
        Callisto.stop()
        callisto.cal_unit.set_relay(mode)
        if action == "start":
            callisto.record_fits(mode)
        elif action == "overview":
            callisto.record_ovs(mode)
        elif action == "start-service":
            callisto.run_daemon(action="start")


if __name__ == "__main__":
    main()
# ----------------------------
# ----------------------------
