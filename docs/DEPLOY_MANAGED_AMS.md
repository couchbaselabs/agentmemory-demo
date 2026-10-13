# Deploying the Hotel Demo with Managed Agent Memory

End-to-end checklist for deploying the hotel demo using the **Managed Agent Memory
Server** on Couchbase Capella.

---

## Part 1: Set up Managed Agent Memory (Capella UI)

1. **Deploy a Capella cluster** on sandbox — ensure nodes have **Data, Index,
   Query, Search** services (all four are required).

2. **While the cluster deploys**, set up an **OpenAI Integration** by pasting
   your OpenAI API key.

3. **Once the cluster is deployed**, create a **bucket** in that cluster.
   Default scope/collections are fine — AMS creates its own scope and
   collections during setup.

4. **Once the integration and bucket are ready**, go to **Agent Memory** and
   click **Deploy Agent Memory**.

5. **Choose your bucket** and **name your AMS** instance.

6. **Choose an embedding model and LLM** from your OpenAI integration.

7. **Advanced config** is prefilled with defaults (except health interval
   seconds — enter any value within bounds).

8. **Hit Deploy** and wait for the status to reach **Healthy**.

9. **Add Allowed IP** — from the AMS instance menu (⋮), click "Add Allowed IP"
   and add your server's public IP (e.g. `54.196.134.78/32`).

10. **Generate API Key** — click "Generate API Key", create a key, and
    **copy the secret token** (shown only once).

11. **Copy the AMS endpoint URL** from the instance details.

---

## Part 2: Deploy the Hotel Demo

### 2.1 Clone the demo repo

```bash
git clone https://github.com/couchbaselabs/agentmemory-demo.git
```

### 2.2 Install the SDK from the dev branch

The managed AMS runs v1.1.0; the PyPI SDK is v1.0.0 and has incompatible API
calls. Install from the `dev` branch of the SDK repo:

```bash
git clone https://github.com/couchbaselabs/agentmem-sdk.git
cd agentmem-sdk && git checkout dev
```

### 2.3 Create a Python venv and install dependencies

```bash
python3.12 -m venv agentmemory-demo/.venv
agentmemory-demo/.venv/bin/pip install --upgrade pip
agentmemory-demo/.venv/bin/pip install -r agentmemory-demo/requirements.txt
agentmemory-demo/.venv/bin/pip install ./agentmem-sdk
```

### 2.4 Create the `.env` file

Create `agentmemory-demo/.env`:

```env
OPENAI_API_KEY=<your key>
COUCHBASE_HOST=<your Capella host>
COUCHBASE_USER=<your Capella user>
COUCHBASE_PASSWORD=<your Capella password>
COUCHBASE_BUCKET=<your bucket>
AGENTMEM_BASE_URL=https://<your managed AMS endpoint>
AGENTMEMORY_JWT_TOKEN=<your AMS API key token>
MODEL=gpt-4o-mini
```

### 2.5 Seed the demo data

```bash
cd agentmemory-demo
.venv/bin/python couchbase_setup.py --data data/hotel_demo.json
```

### 2.6 Build the Next.js frontend

```bash
echo 'NEXT_PUBLIC_API_URL=http://localhost:8502' > agentmemory-demo/hotel_ui/.env.local
cd agentmemory-demo/hotel_ui && npm install && npm run build
```

### 2.7 Set up PM2 and start

Add to `ecosystem.config.js`:

```js
{
  name: "hotel-server",
  script: "agentmemory-demo/.venv/bin/uvicorn",
  args: "hotel_server:app --host 0.0.0.0 --port 8502",
  cwd: "agentmemory-demo",
  interpreter: "none",
  autorestart: true,
  max_restarts: 10,
  env: {
    PATH: "agentmemory-demo/.venv/bin:" + process.env.PATH,
    VIRTUAL_ENV: "agentmemory-demo/.venv",
  },
},
{
  name: "hotel-ui",
  script: "/usr/bin/npx",
  args: "next start -p 8501",
  cwd: "agentmemory-demo/hotel_ui",
  interpreter: "none",
  autorestart: true,
  max_restarts: 10,
},
```

```bash
pm2 start ecosystem.config.js --only hotel-server,hotel-ui
pm2 save
```

### 2.8 Verify

- **Hotel UI:** `http://<your-ip>:8501`
- **Hotel API docs:** `http://<your-ip>:8502/docs`

