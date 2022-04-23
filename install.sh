#!/bin/bash
# Set Callisto USER and PASSWORD
CALLISTO="callisto"
PASSWORD="callisto"
echo "Installing and Configuring environment to control callisto spectrometer"
echo "Make appropriate changes to all CFG files in this folder."
read -p "Press [Enter] key to start backup..."
# Check if is sudo
if [[ "$EUID" != 0 ]]; then
  echo "You do not have admin privileges."
else
  # Easy parto: Just install deb from whatever distribution you are in.
  echo "Installing deb file"
  sudo apt-get install -y callisto
  # Create a dedicated user to run callisto related programs. It should be able to access all the folder structure, scripts and service daemons.
  echo "Creating callisto user."
  if id -u $CALLISTO > /dev/null 2>&1; then
    echo "user callisto already exists. Continuing."
  else
    # quietly add a user without password
    adduser --quiet --disabled-password --shell /bin/bash --home /home/$CALLISTO --gecos "User" $CALLISTO
    # set password
    echo $CALLISTO:$PASSWORD | chpasswd
  fi
  # Folder structure: /etc for configurarion and /opt for data and log
  echo "Creating folders"
  sudo mkdir -p /opt/callisto/data
  sudo mkdir -p /opt/callisto/log
  sudo mkdir -p /opt/callisto/LC
  sudo mkdir -p /opt/callisto/Ovs
  sudo mkdir -p /etc/callisto
  # Read+write permissions for folder structure plus permissions to use serial port in order to handle calibration unit.
  echo "Setting Permissions."
  sudo chown -R callisto:callisto /opt/callisto/
  sudo chown -R :callisto /etc/callisto/
  sudo chmod g+s /opt/callisto/
  sudo usermod -a -G tty callisto
  sudo usermod -a -G dialout callisto
  sudo usermod -a -G callisto $USER
  # Configuring sudoers to allow start and stop callisto service only.
  # This is not much of a securuty concern.
  sudo touch /etc/sudoers.d/callisto
  sudo chmod 440 /etc/sudoers.d/callisto
  echo "$CALLISTO ALL=NOPASSWD:/bin/systemctl start callisto.service" | sudo tee /etc/sudoers.d/callisto
  echo "$CALLISTO ALL=NOPASSWD:/bin/systemctl stop callisto.service" | sudo tee /etc/sudoers.d/callisto
  echo "$CALLISTO ALL=NOPASSWD:/bin/systemctl restart callisto.service" | sudo tee /etc/sudoers.d/callisto
  echo "$CALLISTO ALL=NOPASSWD:/bin/systemctl is-activate --quiet  callisto.service || callisto.service restart" | sudo tee /etc/sudoers.d/callisto
  echo "$CALLISTO ALL=NOPASSWD:/usr/bin/pkill callisto" | sudo tee /etc/sudoers.d/callisto
  # Moving all files to its places. Be sure to make the necessary changes to CFG files. COM port should be set properly.
  echo "Copying files"
  sudo cp *.cfg /etc/callisto
  echo "Configurando serviço daemon."
  sudo cp callisto.service /etc/systemd/system/
  sudo systemctl daemon-reload
  echo "Copying python script to /usr/local/bin and setting permissions"
  sudo cp callisto.py /usr/local/bin
  sudo chown callisto:callisto /usr/local/bin/callisto.py
  sudo chmod u+x /usr/local/bin/callisto.py
  # Installing CRON job twice a day
  sudo /bin/bash -c 'echo "00 0 * * * callisto /usr/bin/python -m /usr/local/bin/callisto.py >> /opt/callisto/log/callisto.log 2>&1" >> /etc/crontab'
  sudo /bin/bash -c  'echo "00 12 * * * callisto /usr/bin/python -m /usr/local/bin/callisto.py >> /opt/callisto/log/callisto.log 2>&1" >> /etc/crontab'
  sudo /bin/bash -c  'echo "00 02 * * * callisto systemctl is-active --quiet callisto.service || callisto.service restart >> /opt/callisto/log/callisto.log 2>&1" >> /etc/crontab'
  # Start DAEMON service.
  echo "Iniciando serviço daemon"
  sudo systemctl daemon-reload
  sudo systemctl start callisto.service
fi
echo "leaving. Done!"
