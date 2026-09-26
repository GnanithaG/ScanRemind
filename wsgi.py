"""WSGI entry point.

Production:  gunicorn -c gunicorn.conf.py wsgi:app
Local dev:   python wsgi.py   (also runs the reminder scheduler)
"""

from scanremind import create_app

app = create_app()

if __name__ == "__main__":
    from scanremind.scheduler import start_scheduler

    start_scheduler(app)
    # The reloader would start a second process and a second scheduler.
    app.run(host="127.0.0.1", port=5000, use_reloader=False)
