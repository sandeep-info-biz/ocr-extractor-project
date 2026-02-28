# 📋 Deployment Checklist

## ✅ Pre-Deployment (On Local Machine)

- [ ] Verify `remote_server` folder exists
- [ ] Check all files are present:
  - [ ] `setup.sh`
  - [ ] `start_server.sh`
  - [ ] `stop_server.sh`
  - [ ] `restart_server.sh`
  - [ ] `status.sh`
  - [ ] `main.py`
  - [ ] `requirements.txt`
  - [ ] `.env.example`
  - [ ] `app/` folder
  - [ ] `data/` folder
  - [ ] `models/` folder

## 🚀 Deployment Steps

### Method A: Automated Deployment
```bash
cd /Users/wipl/Documents/pdfextractorgpt/ocr-extractor-project/remote_server
chmod +x deploy_to_remote.sh
./deploy_to_remote.sh user@SERVER_IP
```

### Method B: Manual Deployment
```bash
# 1. Create archive
cd /Users/wipl/Documents/pdfextractorgpt/ocr-extractor-project
tar -czf ocr-server.tar.gz remote_server/

# 2. Copy to server
scp ocr-server.tar.gz user@SERVER_IP:/home/user/

# 3. SSH and extract
ssh user@SERVER_IP
cd /home/user
tar -xzf ocr-server.tar.gz
cd remote_server
```

## ⚙️ Server Setup (On Remote Server)

```bash
# 1. Make scripts executable
chmod +x *.sh

# 2. Run setup (installs dependencies)
./setup.sh

# 3. Configure (optional)
nano .env
# Change SIMPLYPARSE_API_TOKEN to a secure value
# Change PORT if needed

# 4. Open firewall
sudo ufw allow 8000

# 5. Start server
./start_server.sh

# 6. Verify it's running
./status.sh
```

## 🔗 Connect Java App (On Local Machine)

```bash
# 1. Set environment variable
export PYTHON_SERVICE_BASE_URL=http://SERVER_IP:8000

# 2. Start Java app
cd /Users/wipl/Documents/pdfextractorgpt/ocr-extractor-project
mvn spring-boot:run

# 3. Test connection
curl http://SERVER_IP:8000/health
```

## ✅ Post-Deployment Verification

- [ ] Server is running: `./status.sh` shows "RUNNING"
- [ ] Health check works: `curl http://SERVER_IP:8000/health`
- [ ] Swagger UI accessible: Open `http://SERVER_IP:8000/docs` in browser
- [ ] Java app can connect: Check Java app logs for successful connection
- [ ] Upload test: Try uploading a resume through Java UI

## 🔧 Troubleshooting

### Server won't start
```bash
# Check logs
cat logs/server.log

# Check if port is in use
sudo lsof -i :8000

# Try different port
nano .env  # Change PORT=8001
./restart_server.sh
```

### Can't connect from local machine
```bash
# On server: Check firewall
sudo ufw status
sudo ufw allow 8000

# On server: Verify listening on 0.0.0.0
netstat -tuln | grep 8000

# On local: Test connection
./test_connection.sh SERVER_IP
```

### Python dependencies fail
```bash
# Update pip
source .venv/bin/activate
pip install --upgrade pip

# Install one by one
pip install fastapi uvicorn
pip install -r requirements.txt
```

## 📊 Monitoring

```bash
# View live logs
tail -f logs/server.log

# Check server status
./status.sh

# Check system resources
htop  # or top
```

## 🔄 Updates

```bash
# On local machine: Re-deploy
./deploy_to_remote.sh user@SERVER_IP

# On server: Restart
./restart_server.sh
```

## 🛑 Shutdown

```bash
# On server
./stop_server.sh

# Verify stopped
./status.sh
```

## 📝 Notes

- Default port: 8000
- Default host: 0.0.0.0 (accessible from network)
- Logs location: `logs/server.log`
- PID file: `.server.pid`
- Config file: `.env`

## 🆘 Support

If you encounter issues:
1. Check `logs/server.log` for errors
2. Run `./status.sh` to see current state
3. Verify firewall settings: `sudo ufw status`
4. Test connection: `./test_connection.sh SERVER_IP`
