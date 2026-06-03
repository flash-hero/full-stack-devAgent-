# AI Development Office UI

This folder contains the complete Phase 3 UI in a single file: `index.html`.

## Open It

You can open `index.html` directly in a browser, or serve this folder locally:

```bash
python -m http.server 5173
```

Then open `http://localhost:5173`.

## Backend

The UI polls the backend at `http://localhost:8000/api/status` every 2 seconds and starts pipelines with `POST http://localhost:8000/api/run`.

If the backend is not running, the office still loads and shows `Backend offline`.

## Controls

- Click: enter first-person mode
- W or ArrowUp: move forward
- S or ArrowDown: move backward
- A or ArrowLeft: strafe left
- D or ArrowRight: strafe right
- Mouse: look around
- E: open the pipeline input panel while in the hallway
- Escape: release pointer lock or close the input panel
