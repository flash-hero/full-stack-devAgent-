# AI Development Office UI - Phase 3

This folder contains the complete next-generation 3D office UI in a single file:

- `index.html`

It uses vanilla JavaScript and Three.js r128 from the CDN:

```text
https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js
```

## Open It

From the repository root, use the project launcher:

```powershell
powershell -ExecutionPolicy Bypass -File .\project.ps1 start
```

Then open:

```text
http://localhost:5173
```

You can also serve the UI folder directly:

```powershell
python -m http.server 5173 --directory ui
```

## Backend

The UI polls:

```text
GET http://localhost:8000/api/status
```

It launches pipelines with:

```text
POST http://localhost:8000/api/run
```

If the backend is offline, the UI automatically enters demo mode and cycles the four agents through the pipeline states so the office still feels alive.

## Controls

- Click: enter first-person pointer-lock mode
- W or ArrowUp: move forward
- S or ArrowDown: move backward
- A or ArrowLeft: strafe left
- D or ArrowRight: strafe right
- Mouse: look around
- F: open or close the nearest door
- E: open the pipeline input panel while in the hallway
- Escape: close the input panel or release pointer lock

## Experience

- Four glass-walled agent offices: Architect, Developer, Tester, Deployer
- Central meeting table for handoffs and completion
- Rest room with one bed per agent
- Agent state machines synced to backend status
- CanvasTexture log screens on agent monitors
- Door hints, room HUD, top progress dots, and pipeline log feed
- Celebration sequence when all four agents are done
