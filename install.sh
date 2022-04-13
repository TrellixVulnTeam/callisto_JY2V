#!/bin/bash
CALLISTO="callisto"
PASSWORD="callisto"
echo "Installing and Configuring environment to control callisto spectrometer"
echo "Make appropriate changes to all CFG files in this folder."
read -p "Press [Enter] key to start backup..."
# Check if is sudopytho
if [[ "$EUID" != 0 ]]; then
  echo "You do not have admin privileges."
else
  echo "Installing deb file"
  sudo apt-get install -y callisto
  echo "Creating callisto user."
  if id -u $CALLISTO > /dev/null 2>&1; then
    echo "user callisto already exists. Continuing."
  else
    # quietly add a user without password
    adduser --quiet --disabled-password --shell /bin/bash --home /home/$CALLISTO --gecos "User" $CALLISTO
    # set password
    echo $CALLISTO:$PASSWORD | chpasswd
  fi
  echo "Creating folders"
  sudo mkdir -p /opt/callisto/data
  sudo mkdir -p /opt/callisto/log
  sudo mkdir -p /opt/callisto/LC
  sudo mkdir -p /opt/callisto/Ovs
  sudo mkdir -p /etc/callisto
  echo "Setting Permissions."
  sudo chown -R callisto:callisto /opt/callisto/
  sudo chmod g+s /opt/callisto/
  sudo usermod -a -G tty callisto
  sudo usermod -a -G dialout callisto
  sudo usermod -a -G callisto $USER
  echo "Copying files"
  sudo cp *.cfg /etc/callisto
  echo "Configurando serviço daemon."
  sudo cp callisto.service /etc/systemd/system/
  sudo systemctl daemon-reload
  echo"Copying python script to /usr/local/lib and setting permissions"
  sudo cp callisto.py /usr/local/bin
  sudo chown callisto:callisto /usr/local/bin/callisto.py
  echo "Iniciando serviço daemon"
  sudo systemctl start callisto
fi
echo "leaving. Done!"
