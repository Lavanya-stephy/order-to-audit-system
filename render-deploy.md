## 7. Deploying to Render

The application is fully prepared for deployment as a Docker Web Service on [Render](https://render.com) using SQLite.

### Steps to Deploy

1. **Create a New Web Service:**
   * Select **Deploy an existing image** or connect your Git repository.
   * Choose **Docker** as the runtime environment.
2. **Configure Environment Variables:**
   Add the following variables in the Render dashboard (**Environment** tab):

| Variable | Required | Default / Example | Purpose |
| :--- | :--- | :--- | :--- |
| `DJANGO_SECRET_KEY` | **Yes** | *(e.g. random 50+ character string)* | Production secret key used for session cryptographic signing. |
| `DEBUG` | No | `False` | Disables debug mode in production (default is `False`). |
| `RENDER_EXTERNAL_HOSTNAME` | *Auto-set* | `your-service.onrender.com` | Automatically provided by Render; included in `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` (`https://...`). |
| `PORT` | *Auto-set* | `8000` (locally) | Automatically assigned by Render; Gunicorn binds to `0.0.0.0:$PORT`. |
| `ALLOWED_HOSTS` | No | *(Auto-includes Render hostname)* | Optional comma-separated additional hostnames. |
| `CSRF_TRUSTED_ORIGINS` | No | *(Auto-includes `https://$RENDER_EXTERNAL_HOSTNAME`)* | Optional comma-separated origins allowed to perform POST requests. |
| `SQLITE_PATH` | No | `/app/db.sqlite3` | Optional path to SQLite database. Set to `/data/db.sqlite3` if using a Render Persistent Disk. |

### Production Highlights
* **Web Server:** Runs with production **Gunicorn** WSGI server listening on `0.0.0.0:$PORT`.
* **Static Assets:** Handled by **WhiteNoise** with automatic compression and caching; `collectstatic` runs automatically during container startup.
* **Database & Seeding:** The container entrypoint automatically executes `python manage.py migrate` and idempotent `python manage.py seed_benchmark` on each boot, ensuring all test accounts, master data, and opening stocks are initialized without duplicating stock movements.
* **Reverse Proxy / SSL:** Configured with `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` so authentication forms and CSRF tokens work seamlessly behind Render's HTTPS edge proxy.
* **Document Exports:** DejaVu Sans font (`DejaVuSans.ttf`) is bundled directly in the image, guaranteeing crisp GST Tax Invoice PDFs with Indian Rupee (`₹`) glyphs alongside CSV/Excel exports.