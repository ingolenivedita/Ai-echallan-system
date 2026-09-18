# AI Driven Camera Detected RTO E-Challan System

Complete working web application for a college final-year project.

The system watches **multiple IP cameras at the same time**, detects traffic violations with AI / computer vision, reads number plates (ANPR), issues e-challans, sends SMS notices, and collects fines online.

This is **not a UI-only prototype**. It includes:

- React frontend (Vite + Tailwind)
- FastAPI backend (Uvicorn + OpenCV)
- MongoDB (Motor) with a local JSON fallback if MongoDB is not installed
- Independent camera capture threads (2–3 cameras, or more)
- Groq AI, Plate Recognizer ANPR, Fast2SMS, Razorpay Test Mode
- JWT authentication for **Administrator** and **Traffic Officer**

---

## Demo credentials

Use these on the login page. They are created automatically the first time the backend starts.

| Role | User ID | Password |
| --- | --- | --- |
| Administrator | `ADMIN001` | `Admin@123` |
| Traffic Officer | `OFFICER001` | `Officer@123` |
| Traffic Officer | `OFFICER002` | `Officer@123` |

Login options on the same page:

- **Login** (User ID + password)
- **OTP Login** (SMS if `SMS_API_KEY` is set, otherwise a demo OTP is shown)
- **Forgot Password**

After a successful login you land on the **Dashboard**.

---

## How to run

You need **Python 3.11+** and **Node.js 18+**.

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn app.main:app --reload --port 8000
```

API docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)  
Health: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

### 2. Frontend (second terminal)

```powershell
cd frontend
npm install
npm run dev
```

Open **[http://localhost:5173](http://localhost:5173)**

Windows shortcut: double-click `START.bat` in the project root (starts both servers).

---

## API keys — never hard-coded

All secrets live in `backend/.env` only. The React app **never** receives secret keys.

`backend/.env` (git-ignored) and `backend/.env.example`:

```
# AI API
GROQ_API_KEY=

# ANPR / NUMBER PLATE API
PLATE_RECOGNIZER_API_KEY=

# SMS API
SMS_API_KEY=
SMS_SENDER_ID=

# PAYMENT API
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=

# DATABASE
MONGO_URI=

# AUTHENTICATION
JWT_SECRET=
```

Leave a key empty to keep that feature in **DEMO MODE**. The backend will **not** fake a successful third-party response. It reports `API not configured` and continues the rest of the pipeline.

Admin → **API Configuration** shows, for Groq, Plate Recognizer, SMS and Razorpay:

- Connected / Not Connected
- Masked key preview
- Test Connection
- Setup instructions

---

## What the system does

### Cameras (2–3, independently)

Admin → **Cameras** stores each camera in the database:

- Camera Name, Camera ID, IP Address, RTSP URL, Username, Password, Location, Description
- Add / Edit / Delete / Enable / Disable / Test Connection
- Switch **DEMO MODE** ↔ **LIVE CAMERA MODE**

Example:

```
Camera 1   192.168.1.101   rtsp://username:password@192.168.1.101:554/stream
Camera 2   192.168.1.102   rtsp://username:password@192.168.1.102:554/stream
Camera 3   192.168.1.103   rtsp://username:password@192.168.1.103:554/stream
```

Each camera runs in **its own thread**. One camera going offline does **not** stop the others.

### DEMO CAMERA MODE (no hardware required)

The three seeded cameras start in DEMO MODE using a built-in synthetic traffic scene, so Live Monitoring works immediately.

You can also:

- Upload a traffic **video**
- Upload a still **image**
- Use the bundled sample image `backend/storage/demo/sample_traffic.jpg`

The UI shows a **DEMO MODE** badge. When a real RTSP camera is reachable, switch that camera to **LIVE CAMERA MODE**.

### Live Monitoring

A 2×2 wall of independent MJPEG streams:

```
+----------------------+----------------------+
| CAMERA 1  LIVE/DEMO  | CAMERA 2  LIVE/DEMO  |
+----------------------+----------------------+
| CAMERA 3  LIVE/DEMO  | SYSTEM STATUS  3/3   |
+----------------------+----------------------+
```

Each tile shows: name, location, Online/Offline, IP, FPS, last frame, violation count.

### Camera health and maintenance alerts

For every camera: **ONLINE / OFFLINE / LAST SEEN / LAST FRAME / CONNECTION ERROR**.

If a camera drops: *"Camera 2 is offline. Please check camera/network connection."* on **Maintenance Alerts**.

### AI violation detection

Modular detector (`backend/app/services/detection_service.py`):

1. **NO HELMET**
2. **TRIPLE RIDING**
3. **WRONG SIDE DRIVING**
4. **EXPLOSIVE / PROHIBITED CONTAINER**

Input: camera frame / uploaded image / video  
Output: violation type, confidence, timestamp, camera ID, evidence image.

Detector order:

1. **Groq vision** when `GROQ_API_KEY` is set
2. **OpenCV heuristics** (HOG + optical flow + HSV) for real footage without a key
3. **Demo simulator** only for synthetic cameras (clearly labelled, never presented as AI)

### ANPR, challans, SMS, payment

- Plate Recognizer Snapshot API, or a labelled demo plate if the key is missing
- Automatic e-challan from a detected plate (Motor Vehicles Act sections + fines)
- Fast2SMS notice to the vehicle owner
- Razorpay Test Mode checkout, plus **Record offline payment** for a key-less demo

### Other pages

Dashboard · Violations · Challans · Vehicles · Reports (CSV + optional Groq summary) · Network Status · Maintenance Alerts · Violation Rules · Users · Settings

**Network Status** reports camera TCP reachability, backend status, database, and outbound internet. It does **not** invent Wi-Fi SSID / signal strength.

---

## Project structure

```
project/
├── START.bat                  Windows: start backend + frontend
├── README.md
├── .gitignore                 includes .env
├── backend/
│   ├── .env                   YOUR keys (empty by default, git-ignored)
│   ├── .env.example
│   ├── requirements.txt
│   ├── seed.py                optional extra sample violations
│   ├── smoke_test.py          API walkthrough against a running backend
│   └── app/
│       ├── main.py            FastAPI entry
│       ├── config.py          reads .env only
│       ├── database.py        MongoDB or local JSON
│       ├── routers/           REST APIs
│       └── services/
│           ├── camera_manager.py
│           ├── detection_service.py
│           ├── ai_service.py          Groq
│           ├── anpr_service.py        Plate Recognizer
│           ├── sms_service.py         Fast2SMS
│           ├── payment_service.py     Razorpay
│           ├── challan_service.py
│           └── pipeline.py            multi-camera detection loop
└── frontend/
    ├── package.json
    └── src/pages/             Dashboard, Live, Cameras, Challans, ...
```

---

## Database

Set `MONGO_URI` in `backend/.env` to use MongoDB:

```
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=rto_echallan
```

If `MONGO_URI` is empty (default), the app uses `backend/storage/local_db/` so the project still runs on a student laptop with no MongoDB install.

---

## Optional: extra sample data

```powershell
cd backend
.\.venv\Scripts\python.exe seed.py --violations 20
```

## Optional: API smoke test (backend must be running)

```powershell
cd backend
.\.venv\Scripts\python.exe smoke_test.py
```

---

## College demonstration flow

1. Start both servers, open http://localhost:5173
2. Sign in as `ADMIN001` / `Admin@123`
3. **Live Monitoring** — three cameras streaming in DEMO MODE
4. Click **Detect now** on a camera (or wait for the automatic cycle)
5. **Violations** — evidence image, confidence, plate
6. **Challans** — issued fine, SMS status, offline payment
7. **API Configuration** — Test Connection on each service (will say not configured until you paste keys)
8. **Cameras** — switch one camera to LIVE and enter a real RTSP URL when hardware is available
