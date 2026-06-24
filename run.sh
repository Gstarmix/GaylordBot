export LANG=en_US.UTF-8
cd /home/pi/Gaylord/
source /home/pi/Gaylord/.venv/bin/activate
python3 -u /home/pi/Gaylord/main.py 2>&1 | ts >> ".logs/logs.log"