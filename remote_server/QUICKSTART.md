# 🚀 QUICK START - Copy & Paste Commands

## Option 1: Deploy from Local Machine (Easiest)

```bash
# Make deployment script executable
chmod +x deploy_to_remote.sh

# Deploy to your server (replace with your server details)
./deploy_to_remote.sh user@192.168.1.100

# SSH into server
ssh user@192.168.1.100

# Go to deployed directory
cd ocr-remote-server

# Make scripts executable
chmod +x *.sh

# Run setup
./setup.sh

# Start server
./start_server.sh
```

## Option 2: Manual Copy to Server

### On Local Machine:
```bash
# Zip the folder
cd /Users/wipl/Documents/pdfextractorgpt/ocr-extractor-project
tar -czf ocr-remote-server.tar.gz remote_server/

# Copy to server
scp ocr-remote-server.tar.gz user@192.168.1.100:/home/user/
```

### On Remote Server:
```bash
# Extract
cd /home/user
tar -xzf ocr-remote-server.tar.gz
cd remote_server

# Make scripts executable
chmod +x *.sh

# Run setup
./setup.sh

# Start server
./start_server.sh
```

## Update Your Local Java App

```bash
# Set environment variable (replace IP with your server IP)
export PYTHON_SERVICE_BASE_URL=http://192.168.1.100:8000

# Start Java app
cd /Users/wipl/Documents/pdfextractorgpt/ocr-extractor-project
mvn spring-boot:run
```

## Test Connection

```bash
# From your local machine
curl http://192.168.1.100:8000/health

# Should return: {"status":"ok"}
```

## Common Server IPs to Try

- Same WiFi network: Usually `192.168.1.x` or `192.168.0.x`
- Find server IP: Run `ifconfig` (Mac/Linux) or `ipconfig` (Windows) on server

## Management Commands (on server)

```bash
./start_server.sh    # Start
./stop_server.sh     # Stop
./restart_server.sh  # Restart
./status.sh          # Check status
tail -f logs/server.log  # View logs
```

## Troubleshooting

**Can't connect?**
```bash
# On server, check if port 8000 is open
sudo ufw allow 8000

# Check if server is running
./status.sh
```

**Permission denied?**
```bash
chmod +x *.sh
```

**Port already in use?**
```bash
# Edit .env file and change PORT
nano .env
# Change: PORT=8001
./restart_server.sh
```
