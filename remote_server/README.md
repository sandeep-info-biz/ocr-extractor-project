# Remote OCR Server - Quick Deploy Guide

## What's This?
This folder contains everything you need to run the Python OCR service on a remote server.

## Quick Setup (Copy-Paste Ready)

### 1. Copy this entire `remote_server` folder to your remote server

```bash
# On your local machine
scp -r remote_server user@your-server-ip:/home/user/
```

### 2. SSH into your remote server

```bash
ssh user@your-server-ip
cd /home/user/remote_server
```

### 3. Run the setup script

```bash
chmod +x setup.sh
./setup.sh
```

### 4. Start the server

```bash
./start_server.sh
```

The server will run on `http://0.0.0.0:8000` (accessible from any device on the network)

### 5. Update your local Java app

On your local machine, set the environment variable:

```bash
export PYTHON_SERVICE_BASE_URL=http://YOUR_SERVER_IP:8000
mvn spring-boot:run
```

Replace `YOUR_SERVER_IP` with your actual server IP address.

## Management Commands

```bash
# Start server
./start_server.sh

# Stop server
./stop_server.sh

# Restart server
./restart_server.sh

# Check status
./status.sh

# View logs
tail -f logs/server.log
```

## Configuration

Edit `.env` file to customize:
- `HOST=0.0.0.0` (listen on all interfaces)
- `PORT=8000`
- `CORS_ALLOW_ORIGINS=*` (allow all origins, or specify your Java app URL)
- `SIMPLYPARSE_API_TOKEN=your-secure-token-here`

## Firewall Setup

Make sure port 8000 is open:

```bash
# Ubuntu/Debian
sudo ufw allow 8000

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

## Test Connection

From your local machine:

```bash
curl http://YOUR_SERVER_IP:8000/health
```

Should return: `{"status":"ok"}`

## Troubleshooting

1. **Can't connect?** Check firewall and ensure server is running on `0.0.0.0`
2. **Permission denied?** Run `chmod +x *.sh`
3. **Port already in use?** Change `PORT` in `.env` file
4. **View errors:** `cat logs/server.log`
