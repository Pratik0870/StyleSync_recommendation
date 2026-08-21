# Deployment

The backend and frontend deploy separately. The backend serves the API and the
product images; the frontend is a static build that talks to it.

Nothing here is deployed yet. These are the steps to do it.

## 1. Backend on Render

The repository has a `render.yaml`, so Render can pick the settings up on its
own.

1. Go to <https://dashboard.render.com/blueprints> and choose **New Blueprint
   Instance**.
2. Connect the `StyleSync_recommendation` repository. Render reads `render.yaml`
   and proposes a web service called `stylesync-api`.
3. Set the environment variables it asks for:
   - `GEMINI_API_KEY` (optional). Without it the app runs on the fallback
     parser.
   - `CORS_ORIGINS` can be left empty for now. You will set it in step 3 once
     the frontend URL exists.
4. Deploy. The build runs `scripts/ingest_catalog.py`, which downloads the
   dataset and writes about 90 MB into `data/processed`. Expect several minutes.

When it finishes, check the health endpoint:

```
https://<your-service>.onrender.com/health
```

It should return `"status": "ok"` with `catalog_products: 43165`.

Two things to know about the free plan:

- The service sleeps after inactivity, so the first request after a pause takes
  30 seconds or so to wake it.
- The filesystem is not persistent. The catalog is rebuilt on each deploy, and
  high resolution images fetched at runtime are lost on restart. They are
  re-fetched on demand, so this affects speed rather than correctness.

## 2. Frontend on Vercel

1. Go to <https://vercel.com/new> and import the same repository.
2. Set **Root Directory** to `frontend`.
3. Vercel detects Vite. Build command `npm run build`, output directory `dist`.
4. Add an environment variable:

   ```
   VITE_API_BASE=https://<your-service>.onrender.com
   ```

5. Deploy.

Netlify works the same way: base directory `frontend`, build `npm run build`,
publish `frontend/dist`, same environment variable.

## 3. Connect the two

Go back to the Render service, set

```
CORS_ORIGINS=https://<your-frontend>.vercel.app
```

and redeploy. Without this the browser blocks the frontend's API calls, because
the backend only allows localhost origins by default.

## 4. Check it works

Open the frontend URL and try:

- `black formal shirt` should return black shirts first, then items that go with
  them.
- `office wear for men` should return a full outfit in four sections.
- Product images should load.
- The header badge should read **AI-assisted matching** if `GEMINI_API_KEY` is
  set and the quota is available, or **Standard matching** if not. Both are
  working states.

## 5. Update the README

Replace the Deployment section in `README.md` with the live URL, and add the
same URL to the repository's About panel on GitHub.

## Alternatives

Any host that runs a Python web service works. The requirements are a build step
that can run `scripts/ingest_catalog.py`, roughly 500 MB of disk during the
build, and about 1 GB of memory at runtime, since the catalog and the thumbnail
store are held in memory.

Railway and Fly.io both work. There is no Dockerfile in the repository; the
Render blueprint uses the native Python runtime instead.
