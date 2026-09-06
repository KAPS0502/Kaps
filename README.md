# BeatVault Pro

A professional producer portfolio/catalog built with Flask.

## Included
- Artist name, logo text and tagline settings
- Cover art per beat
- BPM, key and genre metadata
- Search + genre filtering
- Audio preview player
- Original-file downloads
- Private producer studio
- SQLite catalog
- Production Gunicorn config
- Render deployment blueprint with a persistent disk for uploads

## Local
`python -m venv .venv`
Activate the environment, then:
`pip install -r requirements.txt`
Set `ADMIN_PASSWORD` and `SECRET_KEY`, then run:
`python app.py`

## Deploy to Render
1. Create a GitHub repository and upload this project.
2. Create a Render account and choose **New > Blueprint**.
3. Connect the GitHub repository. Render reads `render.yaml`.
4. Set the secret `ADMIN_PASSWORD` when prompted.
5. Deploy.
6. Open your Render URL, go to **Studio**, and set your artist name/logo/tagline.
7. Upload beats and cover art.

### Storage note
The blueprint includes a 10 GB persistent disk mounted at `/opt/render/project/src/uploads`, so uploaded audio/cover files survive normal service restarts. For a larger catalog or multiple servers, migrate uploads to S3-compatible object storage and move the database to managed Postgres.

## Production security
Use a long random `SECRET_KEY` and a strong unique `ADMIN_PASSWORD`. Do not commit secrets to GitHub.
